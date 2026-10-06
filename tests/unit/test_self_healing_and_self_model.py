"""Self-healing (detection, bounded repair, escalation) and the honest self-model.

The live Redis-outage proof is ``scripts/self_healing_live_test.py``; these tests pin the
decision logic deterministically, including the two bugs that live testing exposed:
probes never running on CLOSED circuits, and a reset erasing the evidence history.
"""

from __future__ import annotations

import asyncio

import pytest
from cortex_core.resilience import (
    CircuitState,
    EscalationNotifier,
    HealthRegistry,
    SelfHealingLoop,
    SelfHealingSupervisor,
    SubsystemCircuit,
)
from cortex_core.self_model import SelfModel, SelfModificationAlreadyApplied, SelfModificationEngine

from cortex_upgrade.runtime_knobs import RuntimeKnobs


def _run(coro):
    return asyncio.run(coro)


# ── circuit breaker ─────────────────────────────────────────────────────────


def test_breaker_opens_after_consecutive_failures_and_half_opens():
    circuit = SubsystemCircuit("redis", failure_threshold=3, recovery_timeout_seconds=0.05)

    async def scenario():
        for _ in range(3):
            assert await circuit.before() is True
            await circuit.record_failure("probe failed")
        assert circuit.state is CircuitState.OPEN
        # While OPEN (within the recovery window) calls are refused fast.
        assert await circuit.before() is False
        await asyncio.sleep(0.06)
        assert await circuit.before() is True
        assert circuit.state is CircuitState.HALF_OPEN
        await circuit.record_success()
        assert circuit.state is CircuitState.CLOSED
        assert await circuit.before() is True

    _run(scenario())


def test_breaker_opens_on_failure_ratio():
    circuit = SubsystemCircuit("db", failure_threshold=99, min_samples=5, failure_ratio_threshold=0.6)

    async def scenario():
        for ok in (True, True, False, False, False):
            await (circuit.record_success() if ok else circuit.record_failure("x"))
        assert circuit.failure_ratio == pytest.approx(0.6)
        assert circuit.state is CircuitState.OPEN

    _run(scenario())


def test_failed_probe_while_half_open_reopens_immediately():
    circuit = SubsystemCircuit("ai", failure_threshold=2, recovery_timeout_seconds=0.01)

    async def scenario():
        await circuit.record_failure("x")
        await circuit.record_failure("x")
        await asyncio.sleep(0.02)
        assert await circuit.before() is True  # HALF_OPEN probe admitted
        await circuit.record_failure("probe failed")
        assert circuit.state is CircuitState.OPEN

    _run(scenario())


def test_reset_preserves_observation_history():
    """A recovered subsystem must not read as never-observed (live-test regression)."""
    circuit = SubsystemCircuit("redis", failure_threshold=2)

    async def scenario():
        await circuit.record_failure("x")
        await circuit.record_failure("x")
        assert circuit.snapshot()["samples"] == 2
        await circuit.reset("repair verified")
        await circuit.record_success()
        assert circuit.state is CircuitState.CLOSED
        assert circuit.snapshot()["samples"] == 3

    _run(scenario())


# ── supervisor ──────────────────────────────────────────────────────────────


def test_cycle_probes_even_when_the_breaker_is_closed():
    """The original loop only probed OPEN circuits, so nothing could ever be detected."""
    registry = HealthRegistry()
    probes = {"count": 0}

    async def probe() -> bool:
        probes["count"] += 1
        return True

    registry.register_probe("redis", probe)
    supervisor = SelfHealingSupervisor(registry, repair_cooldown_seconds=0.0)
    run = _run(supervisor.run_cycle())

    assert probes["count"] == 1
    assert run.checked == ["redis"]
    assert run.unhealthy == []
    assert registry.circuit("redis").snapshot()["samples"] == 1


def test_failing_subsystem_is_detected_and_escalated_after_bounded_repairs():
    registry = HealthRegistry()
    healthy = {"ok": False}

    async def probe() -> bool:
        return healthy["ok"]

    repairs = {"attempts": 0}

    async def repair() -> bool:
        repairs["attempts"] += 1
        return False  # cannot fix it

    registry.register_probe("redis", probe)
    supervisor = SelfHealingSupervisor(registry, repair_cooldown_seconds=0.0, max_repairs_per_subsystem=2)
    supervisor.register_repair("redis", repair)

    _run(supervisor.run_cycle())  # probe fails -> repair attempt 1
    _run(supervisor.run_cycle())  # still failing -> repair attempt 2
    third = _run(supervisor.run_cycle())  # budget exhausted -> escalate

    assert repairs["attempts"] == 2
    assert registry.circuit("redis").state is CircuitState.OPEN
    assert third.escalated == ["redis"]
    assert supervisor.escalations[-1]["reason"].startswith("2 repair attempts")


def test_successful_repair_is_only_claimed_when_verified_by_probe():
    registry = HealthRegistry()
    healthy = {"ok": False}

    async def probe() -> bool:
        return healthy["ok"]

    async def repair() -> bool:
        healthy["ok"] = True
        return True

    registry.register_probe("redis", probe)
    supervisor = SelfHealingSupervisor(registry, repair_cooldown_seconds=0.0)
    supervisor.register_repair("redis", repair)

    for _ in range(3):
        _run(supervisor.run_cycle())  # failing probes trip the breaker
    healthy["ok"] = False
    run = _run(supervisor.run_cycle())  # repair flips health -> probe verifies it
    assert run.repairs and run.repairs[0].repaired is True
    circuit = registry.circuit("redis")
    assert circuit.state is CircuitState.CLOSED
    assert circuit.snapshot()["samples"] > 0, "a verified repair leaves evidence behind"


def test_repair_without_verification_is_not_reported_as_a_fix():
    registry = HealthRegistry()
    calls = {"n": 0}

    async def probe() -> bool:
        calls["n"] += 1
        return False  # never healthy

    async def repair() -> bool:
        return True  # claims success, but the probe disagrees

    registry.register_probe("redis", probe)
    supervisor = SelfHealingSupervisor(registry, repair_cooldown_seconds=0.0)
    supervisor.register_repair("redis", repair)
    for _ in range(3):
        run = _run(supervisor.run_cycle())
    assert run.repaired == []
    assert any("did not restore health" in r.detail for r in run.repairs)


def test_background_loop_runs_cycles_and_honours_the_switch():
    """The loop is the difference between "can self-heal" and "does self-heal"."""
    registry = HealthRegistry()
    probes = {"count": 0}

    async def probe() -> bool:
        probes["count"] += 1
        return True

    registry.register_probe("redis", probe)
    supervisor = SelfHealingSupervisor(registry, repair_cooldown_seconds=0.0)
    settings = {"enabled": True, "interval": 0.01}
    loop = SelfHealingLoop(
        supervisor,
        settings_provider=lambda: (settings["enabled"], settings["interval"]),
        min_interval_seconds=0.01,
    )

    async def scenario():
        loop.start()
        await asyncio.sleep(0.06)
        assert loop.running and loop.cycles >= 2, f"cycles={loop.cycles}"
        observed = probes["count"]

        settings["enabled"] = False
        await asyncio.sleep(0.06)
        assert loop.cycles <= observed + 1, "disabled loop must stop probing"
        assert loop.skipped_disabled >= 1

        settings["enabled"] = True
        await asyncio.sleep(0.06)
        assert loop.cycles > observed, "re-enabling must resume work"
        assert probes["count"] > observed

        await loop.stop()
        assert loop.running is False

    _run(scenario())
    status = loop.status()
    assert status["running"] is False
    assert status["cycles"] >= 3
    assert status["errors"] == 0
    assert status["last_checked_at"], "status must say when it last looked"


def test_background_loop_survives_a_failing_cycle():
    registry = HealthRegistry()

    async def probe() -> bool:
        return True

    registry.register_probe("redis", probe)

    class _Flaky(SelfHealingSupervisor):
        async def run_cycle(self):  # type: ignore[override]
            if not hasattr(self, "_failed_once"):
                self._failed_once = True
                raise RuntimeError("transient")
            return await super().run_cycle()

    loop = SelfHealingLoop(
        _Flaky(registry, repair_cooldown_seconds=0.0),
        settings_provider=lambda: (True, 0.01),
        min_interval_seconds=0.01,
    )

    async def scenario():
        loop.start()
        await asyncio.sleep(0.08)
        await loop.stop()

    _run(scenario())
    assert loop.errors == 1, f"errors={loop.errors}"
    assert loop.cycles >= 1, "a failed cycle must not stop the loop"
    assert loop.running is False


# ── escalation delivery ─────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _FakeClient:
    """Stands in for httpx.AsyncClient; records calls or raises on demand."""

    calls: list[dict] = []
    status_code = 204
    raise_on_post: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json=None):
        if _FakeClient.raise_on_post is not None:
            raise _FakeClient.raise_on_post
        _FakeClient.calls.append({"url": url, "json": json})
        return _FakeResponse(_FakeClient.status_code)


@pytest.fixture()
def fake_http(monkeypatch):
    import httpx

    _FakeClient.calls = []
    _FakeClient.status_code = 204
    _FakeClient.raise_on_post = None
    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)
    yield _FakeClient
    _FakeClient.calls = []
    _FakeClient.raise_on_post = None


def test_notifier_without_a_channel_says_so(fake_http):
    record = _run(EscalationNotifier(webhook_url="").deliver({"subsystem": "redis", "reason": "down"}))
    assert record["delivered"] is False
    assert record["detail"] == "no escalation channel configured"
    assert fake_http.calls == [], "a missing channel must not attempt an HTTP call"


def test_notifier_delivers_and_deduplicates(fake_http):
    notifier = EscalationNotifier(webhook_url="http://ops.local/alerts", dedupe_window_seconds=600)
    first = _run(notifier.deliver({"subsystem": "redis", "reason": "down"}))
    second = _run(notifier.deliver({"subsystem": "redis", "reason": "down"}))
    other = _run(notifier.deliver({"subsystem": "redis", "reason": "different problem"}))

    assert first["delivered"] is True and first["status_code"] == 204
    assert second["delivered"] is False and "duplicate suppressed" in second["detail"]
    assert other["delivered"] is True, "a different problem must still reach the operator"
    assert len(fake_http.calls) == 2
    assert notifier.status()["suppressed_duplicates"] == 1


def test_notifier_reports_a_failing_channel_and_a_transport_error(fake_http):
    notifier = EscalationNotifier(webhook_url="http://ops.local/alerts", dedupe_window_seconds=0)
    fake_http.status_code = 500
    failed = _run(notifier.deliver({"subsystem": "schema", "reason": "missing table"}))
    assert failed["delivered"] is False and failed["status_code"] == 500

    fake_http.raise_on_post = ConnectionError("channel unreachable")
    errored = _run(notifier.deliver({"subsystem": "schema", "reason": "missing table"}))
    assert errored["delivered"] is False
    assert "ConnectionError" in errored["detail"]


def test_supervisor_records_escalation_delivery_in_the_cycle(fake_http):
    registry = HealthRegistry()

    async def failing() -> bool:
        return False

    registry.register_probe("comms", failing)
    supervisor = SelfHealingSupervisor(
        registry,
        repair_cooldown_seconds=0.0,
        max_repairs_per_subsystem=1,
        notifier=EscalationNotifier(webhook_url="http://ops.local/alerts", dedupe_window_seconds=0),
    )
    run = _run(supervisor.run_cycle())
    assert run.escalated == ["comms"]
    assert len(run.escalations_delivered) == 1
    assert run.escalations_delivered[0]["delivered"] is True
    assert run.as_dict()["escalations_delivered"][0]["subsystem"] == "comms"


# ── self-model ──────────────────────────────────────────────────────────────


def test_self_model_reports_unverified_when_nothing_was_observed():
    registry = HealthRegistry()
    registry.circuit("redis")
    registry.circuit("database")
    model = SelfModel(health=registry)
    built = _run(model.build())

    assert built["capabilities"]["realtime_streaming"]["state"] == "unverified"
    assert built["capabilities"]["persistence"]["state"] == "unverified"
    assert any("never been observed" in gap for gap in built["gaps"])
    assert built["identity"]["evidence_basis"].startswith("registration + observed health")


def test_self_model_reports_degraded_when_a_circuit_is_open():
    registry = HealthRegistry()
    circuit = registry.circuit("redis", failure_threshold=1)
    _run(circuit.record_failure("outage"))
    model = SelfModel(health=registry)
    built = _run(model.build())

    assert built["capabilities"]["realtime_streaming"]["state"] == "degraded"
    assert any("circuit OPEN" in note for note in built["capabilities"]["realtime_streaming"]["notes"])
    diagnostics = _run(model.diagnose())
    assert diagnostics["summary"] == "attention_required"
    assert any(finding["severity"] == "HIGH" for finding in diagnostics["findings"])


def test_self_model_counts_registered_agents_without_claiming_health():
    from cortex_agents import AgentRegistry

    registry = HealthRegistry()
    registry.register_probe("agents", lambda: _async_true())
    _run(registry.run_probe("agents"))
    model = SelfModel(registry=AgentRegistry(), health=registry)
    built = _run(model.build())

    collaboration = built["capabilities"]["multi_agent_collaboration"]
    assert len(collaboration["registered_agents"]) == len(set(collaboration["registered_agents"]))
    assert "agent_growth" in collaboration["registered_agents"]
    assert collaboration["state"] == "operational"


async def _async_true() -> bool:
    return True


# ── self-modification ───────────────────────────────────────────────────────


def test_self_modification_refuses_anything_not_on_the_allow_list():
    engine = SelfModificationEngine(RuntimeKnobs())
    accepted, refused = engine.evaluate(
        [
            {"knob": "database_url", "value": "postgres://evil"},
            {"knob": "max_collaboration_rounds", "value": 99},
            {"knob": "max_collaboration_rounds", "value": "three"},
            {"knob": "max_collaboration_rounds", "value": 4, "rationale": "deeper deliberation"},
        ]
    )

    assert len(accepted) == 1
    assert accepted[0].knob == "max_collaboration_rounds"
    reasons = [entry["reason"] for entry in refused]
    assert "not on the self-modification allow-list" in reasons
    assert "out of range 1..5" in reasons  # 99 is rejected by range, not by type
    assert "expected int" in reasons  # "three" is rejected by type


def test_self_modification_is_reversible_and_double_apply_is_refused():
    knobs = RuntimeKnobs()
    engine = SelfModificationEngine(knobs)
    accepted, _refused = engine.evaluate([{"knob": "self_healing_interval_seconds", "value": 5}])
    engine.apply(accepted)

    assert knobs.get("self_healing_interval_seconds") == 5
    assert knobs.diff_from_defaults(), "a change must be visible as a diff from defaults"

    with pytest.raises(SelfModificationAlreadyApplied):
        engine.apply(accepted)

    rolled_back = engine.rollback("self_healing_interval_seconds")
    assert rolled_back["restored"] == 30
    assert knobs.get("self_healing_interval_seconds") == 30


def test_rollback_can_walk_back_through_several_changes():
    """Regression: a rollback record in the history made a second rollback crash (KeyError)."""
    knobs = RuntimeKnobs()
    engine = SelfModificationEngine(knobs)
    for value in (45, 50):
        accepted, refused = engine.evaluate([{"knob": "self_healing_interval_seconds", "value": value}])
        assert accepted and not refused, f"{value} refused: {refused}"
        engine.apply(accepted)

    assert engine.rollback("self_healing_interval_seconds")["restored"] == 45
    assert engine.rollback("self_healing_interval_seconds")["restored"] == 30
    assert knobs.get("self_healing_interval_seconds") == 30
    with pytest.raises(KeyError):
        engine.rollback("self_healing_interval_seconds")  # nothing left to undo


def test_self_modification_rejects_a_no_op():
    engine = SelfModificationEngine(RuntimeKnobs())
    accepted, refused = engine.evaluate([{"knob": "max_collaboration_rounds", "value": 3}])
    assert accepted == []
    assert refused[0]["reason"] == "already at the requested value"
