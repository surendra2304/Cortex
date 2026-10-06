"""Self-healing primitives: health registry, circuit breakers, bounded self-repair.

What this adds to CORTEX:

* ``HealthRegistry`` — every subsystem reports observed outcomes. A subsystem that starts
  failing is *detected* (consecutive failures, or a rolling failure ratio over a minimum
  number of samples) rather than merely logged.
* ``SubsystemCircuit`` — a real breaker with CLOSED → OPEN → HALF_OPEN → CLOSED transitions,
  a single probe in HALF_OPEN, and an ``outage_for`` duration so callers can degrade
  gracefully instead of queueing behind a dead dependency.
* ``SelfHealingSupervisor`` — probes the registry and applies **bounded** repairs. A repair
  action is throttled (``repair_cooldown_seconds``), a subsystem that keeps failing after
  repairs escalates instead of looping, and no repair can silently become a "fix" that it
  cannot verify: repairs report ``repaired``, ``still_failing`` or ``escalated``.

Deliberate limits: repairs are local and idempotent (re-probe, reset breaker, drop cached
state, re-register a worker). Anything that cannot be proven from a post-repair probe is
escalated, never claimed as fixed.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger("cortex-core.resilience")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class SubsystemCircuit:
    """Circuit breaker for one subsystem (dependency, agent or tool)."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        recovery_timeout_seconds: float = 15.0,
        window: int = 20,
        min_samples: int = 5,
        failure_ratio_threshold: float = 0.6,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.window = window
        self.min_samples = min_samples
        self.failure_ratio_threshold = failure_ratio_threshold

        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.opened_at: float | None = None
        self._outcomes: deque[bool] = deque(maxlen=window)
        self._lock = asyncio.Lock()
        self.total_successes = 0
        self.total_failures = 0
        self.transitions: list[dict[str, Any]] = []

    # ── state ───────────────────────────────────────────────────────────────
    def _record_transition(self, to: CircuitState, reason: str) -> None:
        self.transitions.append(
            {"from": self.state.value, "to": to.value, "reason": reason, "at": _utcnow().isoformat()}
        )
        self.transitions = self.transitions[-20:]
        logger.warning("circuit[%s] %s -> %s (%s)", self.name, self.transitions[-1]["from"], to.value, reason)
        self.state = to

    @property
    def failure_ratio(self) -> float | None:
        if len(self._outcomes) < self.min_samples:
            return None
        return sum(1 for ok in self._outcomes if not ok) / len(self._outcomes)

    def outage_for(self) -> float:
        """Seconds the subsystem has been unavailable (0 when it is not)."""
        if self.state != CircuitState.OPEN or self.opened_at is None:
            return 0.0
        return round(time.monotonic() - self.opened_at, 3)

    def is_available(self) -> bool:
        """True when a call may be attempted now (HALF_OPEN allows exactly one probe)."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            return self._can_half_open()
        return True  # HALF_OPEN: the probe itself decides

    def _can_half_open(self) -> bool:
        return self.opened_at is not None and (time.monotonic() - self.opened_at) >= self.recovery_timeout_seconds

    # ── outcomes ────────────────────────────────────────────────────────────
    async def before(self) -> bool:
        """Returns False when the breaker refuses the call (fail fast)."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if self._can_half_open():
                    self._record_transition(CircuitState.HALF_OPEN, "recovery timeout elapsed")
                    return True
                return False
            return True

    async def record_success(self) -> None:
        async with self._lock:
            self._outcomes.append(True)
            self.total_successes += 1
            self.consecutive_failures = 0
            if self.state == CircuitState.HALF_OPEN:
                self._record_transition(CircuitState.CLOSED, "probe succeeded")
            self.opened_at = None

    async def record_failure(self, reason: str = "call failed") -> None:
        async with self._lock:
            self._outcomes.append(False)
            self.total_failures += 1
            self.consecutive_failures += 1
            if self.state == CircuitState.HALF_OPEN:
                self._open(reason=f"probe failed: {reason}")
                return
            if self.state == CircuitState.CLOSED:
                if self.consecutive_failures >= self.failure_threshold:
                    self._open(reason=f"{self.consecutive_failures} consecutive failures")
                elif self.failure_ratio is not None and self.failure_ratio >= self.failure_ratio_threshold:
                    self._open(reason=f"failure ratio {self.failure_ratio:.0%} over {len(self._outcomes)} samples")

    def _open(self, reason: str) -> None:
        self.opened_at = time.monotonic()
        self._record_transition(CircuitState.OPEN, reason)

    async def reset(self, reason: str = "manual reset") -> None:
        """Clear the failure state without erasing the observation history.

        ``samples`` is evidence ("we have looked N times"); wiping it on recovery made a
        subsystem that had just been verified read as never-observed in the self-model.
        """
        async with self._lock:
            self.consecutive_failures = 0
            self.opened_at = None
            if self.state != CircuitState.CLOSED:
                self._record_transition(CircuitState.CLOSED, reason)

    def snapshot(self) -> dict[str, Any]:
        return {
            "subsystem": self.name,
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "failure_ratio": round(self.failure_ratio, 4) if self.failure_ratio is not None else None,
            "samples": len(self._outcomes),
            "outage_for_seconds": self.outage_for(),
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "last_transitions": list(self.transitions[-3:]),
        }


@dataclass
class SubsystemStatus:
    name: str
    available: bool
    detail: dict[str, Any]
    outage_for_seconds: float = 0.0


class HealthRegistry:
    """Tracks every subsystem CORTEX depends on, with observed outcomes."""

    def __init__(self) -> None:
        self._circuits: dict[str, SubsystemCircuit] = {}
        self._probes: dict[str, Callable[[], Awaitable[bool]]] = {}
        self._last_probe: dict[str, dict[str, Any]] = {}

    def circuit(self, name: str, **kwargs: Any) -> SubsystemCircuit:
        if name not in self._circuits:
            self._circuits[name] = SubsystemCircuit(name, **kwargs)
        return self._circuits[name]

    def register_probe(self, name: str, probe: Callable[[], Awaitable[bool]]) -> None:
        """A probe returns True when the subsystem is healthy. Used by the supervisor."""
        self._probes[name] = probe
        self.circuit(name)

    async def run_probe(self, name: str) -> bool:
        probe = self._probes.get(name)
        circuit = self.circuit(name)
        if probe is None:
            self._last_probe[name] = {"checked_at": _utcnow().isoformat(), "healthy": None, "reason": "no probe"}
            return True
        try:
            healthy = bool(await probe())
        except Exception as exc:  # a probe that raises is a failed probe
            healthy = False
            self._last_probe[name] = {"checked_at": _utcnow().isoformat(), "healthy": False, "error": str(exc)[:200]}
        else:
            self._last_probe[name] = {"checked_at": _utcnow().isoformat(), "healthy": healthy}
        if healthy:
            await circuit.record_success()
        else:
            await circuit.record_failure("health probe failed")
        return healthy

    def status(self) -> list[SubsystemStatus]:
        return [
            SubsystemStatus(
                name=name,
                available=circuit.is_available(),
                detail=circuit.snapshot(),
                outage_for_seconds=circuit.outage_for(),
            )
            for name, circuit in self._circuits.items()
        ]

    def snapshot(self) -> dict[str, Any]:
        degraded = [s.name for s in self.status() if not s.available]
        return {
            "subsystems": {s.name: s.detail for s in self.status()},
            "degraded": degraded,
            "last_probes": dict(self._last_probe),
            "observed_at": _utcnow().isoformat(),
        }


@dataclass
class RepairOutcome:
    subsystem: str
    action: str
    repaired: bool
    escalated: bool
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "action": self.action,
            "repaired": self.repaired,
            "escalated": self.escalated,
            "detail": self.detail,
        }


@dataclass
class HealingRun:
    started_at: datetime
    checked: list[str] = field(default_factory=list)
    unhealthy: list[str] = field(default_factory=list)
    repairs: list[RepairOutcome] = field(default_factory=list)
    escalations_delivered: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: float = 0.0

    @property
    def repaired(self) -> list[str]:
        return [r.subsystem for r in self.repairs if r.repaired]

    @property
    def escalated(self) -> list[str]:
        return [r.subsystem for r in self.repairs if r.escalated]

    def as_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "checked": list(self.checked),
            "unhealthy": list(self.unhealthy),
            "repaired": self.repaired,
            "escalated": self.escalated,
            "repairs": [r.as_dict() for r in self.repairs],
            "escalations_delivered": list(self.escalations_delivered),
            "duration_ms": round(self.duration_ms, 3),
        }


class SelfHealingSupervisor:
    """Probes subsystems, applies bounded repairs, escalates what it cannot fix."""

    def __init__(
        self,
        registry: HealthRegistry,
        repair_cooldown_seconds: float = 30.0,
        max_repairs_per_subsystem: int = 3,
        notifier: EscalationNotifier | None = None,
    ) -> None:
        self.registry = registry
        self.repair_cooldown_seconds = repair_cooldown_seconds
        self.max_repairs_per_subsystem = max_repairs_per_subsystem
        self._repairs: dict[str, list[float]] = {}
        self._attempts: dict[str, int] = {}
        self._repair_fns: dict[str, Callable[[], Awaitable[bool]]] = {}
        self.escalations: list[dict[str, Any]] = []
        self.notifier = notifier or EscalationNotifier()

    def register_repair(self, subsystem: str, repair: Callable[[], Awaitable[bool]]) -> None:
        """A repair returns True when it *verified* the subsystem works again."""
        self._repair_fns[subsystem] = repair

    async def _notify(self, escalation: dict[str, Any], run: HealingRun) -> None:
        """Hand the escalation to the operator channel; never let delivery break healing."""
        try:
            delivery = await self.notifier.deliver(escalation)
        except Exception as exc:  # noqa: BLE001 - defensive: the notifier already guards itself
            delivery = {"delivered": False, "detail": f"{type(exc).__name__}: {exc}"}
        run.escalations_delivered.append(delivery)

    def _throttled(self, subsystem: str) -> bool:
        history = [t for t in self._repairs.get(subsystem, []) if time.monotonic() - t < self.repair_cooldown_seconds]
        return bool(history)

    async def run_cycle(self) -> HealingRun:
        run = HealingRun(started_at=_utcnow())
        started = time.perf_counter()

        for status in self.registry.status():
            run.checked.append(status.name)
            circuit = self.registry.circuit(status.name)

            # Always observe. The first version of this loop skipped CLOSED circuits, so a
            # breaker that had never opened was never probed either — no observation, no
            # samples, no way to ever open. Detection has to come from probing, not from
            # waiting for a failure to announce itself.
            healthy = await self.registry.run_probe(status.name)
            if healthy and circuit.state is CircuitState.CLOSED:
                continue
            run.unhealthy.append(status.name)

            # Something may have recovered on its own (self-healing without intervention).
            if healthy:
                if circuit.state is not CircuitState.CLOSED:
                    await circuit.reset("probe succeeded")
                run.repairs.append(RepairOutcome(status.name, "probe", True, False, "recovered without intervention"))
                continue

            if self._throttled(status.name):
                run.repairs.append(RepairOutcome(status.name, "repair", False, False, "repair throttled by cooldown"))
                continue

            attempts = self._attempts.get(status.name, 0)
            if attempts >= self.max_repairs_per_subsystem:
                escalation = {
                    "subsystem": status.name,
                    "reason": f"{attempts} repair attempts did not restore health",
                    "at": _utcnow().isoformat(),
                }
                self.escalations.append(escalation)
                self.escalations = self.escalations[-20:]
                await self._notify(escalation, run)
                run.repairs.append(RepairOutcome(status.name, "none", False, True, escalation["reason"]))
                continue

            repair = self._repair_fns.get(status.name)
            if repair is None:
                escalation = {
                    "subsystem": status.name,
                    "reason": "no repair action registered",
                    "at": _utcnow().isoformat(),
                }
                self.escalations.append(escalation)
                self.escalations = self.escalations[-20:]
                await self._notify(escalation, run)
                run.repairs.append(RepairOutcome(status.name, "none", False, True, "no repair action registered"))
                continue

            self._repairs.setdefault(status.name, []).append(time.monotonic())
            self._attempts[status.name] = attempts + 1
            try:
                repaired = bool(await repair())
            except Exception as exc:
                run.repairs.append(
                    RepairOutcome(status.name, "repair", False, False, f"repair raised {type(exc).__name__}: {exc}")
                )
                continue

            # A repair is only a repair if the subsystem is verifiably healthy afterwards.
            verified = repaired and await self.registry.run_probe(status.name)
            if verified:
                circuit = self.registry.circuit(status.name)
                await circuit.reset("self-healing repair verified")
                await circuit.record_success()  # the verifying probe is evidence of health
                self._attempts[status.name] = 0
                run.repairs.append(RepairOutcome(status.name, "repair+probe", True, False, "repair verified by probe"))
            else:
                run.repairs.append(
                    RepairOutcome(status.name, "repair+probe", False, False, "repair did not restore health")
                )

        run.duration_ms = (time.perf_counter() - started) * 1000
        return run


# Process-wide registry: subsystems report here, the supervisor heals from here.
global_health_registry = HealthRegistry()


class SelfHealingLoop:
    """Runs the supervisor on a cadence, forever, and never dies doing it.

    The on/off switch and the cadence are re-read on every tick, so a runtime knob change
    (including an operator-approved self-modification) takes effect on the next tick instead
    of requiring a restart. A failing cycle is counted and logged, not raised.
    """

    def __init__(
        self,
        supervisor: SelfHealingSupervisor,
        settings_provider: Callable[[], tuple[bool, float]] | None = None,
        min_interval_seconds: float = 1.0,
    ) -> None:
        self.supervisor = supervisor
        self._settings_provider = settings_provider or (lambda: (True, 30.0))
        self.min_interval_seconds = min_interval_seconds
        self.cycles = 0
        self.errors = 0
        self.skipped_disabled = 0
        self.last_run: HealingRun | None = None
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def tick(self) -> None:
        enabled, interval = self._settings_provider()
        if enabled:
            try:
                self.last_run = await self.supervisor.run_cycle()
                self.cycles += 1
                self.last_error = None
            except Exception as exc:  # noqa: BLE001 - the loop must outlive a bad cycle
                self.errors += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning("self-healing cycle failed: %s", exc)
        else:
            self.skipped_disabled += 1
        await asyncio.sleep(max(float(interval), self.min_interval_seconds))

    async def run_forever(self) -> None:
        while True:
            await self.tick()

    def start(self) -> asyncio.Task:
        if self.running:
            return self._task  # type: ignore[return-value]
        self._task = asyncio.create_task(self.run_forever())
        self._task.add_done_callback(self._on_done)
        return self._task

    @staticmethod
    def _on_done(task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:  # pragma: no cover - defensive
            logger.error("self-healing loop terminated unexpectedly: %s", exc)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "cycles": self.cycles,
            "errors": self.errors,
            "skipped_while_disabled": self.skipped_disabled,
            "last_error": self.last_error,
            "last_checked_at": self.last_run.started_at.isoformat() if self.last_run else None,
            "last_unhealthy": list(self.last_run.unhealthy) if self.last_run else [],
            "last_repairs": [
                r.as_dict() if hasattr(r, "as_dict") else r for r in (self.last_run.repairs if self.last_run else [])
            ],
            "escalation_channel": self.supervisor.notifier.status(),
        }


class EscalationNotifier:
    """Delivers escalations to an operator channel — or says plainly that it could not.

    Without a configured channel this does not pretend to notify anyone: it records
    ``delivered: False`` with the reason. Repeated escalations for the same subsystem and
    reason are collapsed inside ``dedupe_window_seconds`` and counted, so a permanently
    broken dependency cannot spam an operator into ignoring the channel.
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        timeout_seconds: float = 5.0,
        dedupe_window_seconds: float = 600.0,
    ) -> None:
        self.webhook_url = (webhook_url or "").strip() or None
        self.timeout_seconds = timeout_seconds
        self.dedupe_window_seconds = dedupe_window_seconds
        self.deliveries: list[dict[str, Any]] = []
        self.suppressed = 0
        self._last_sent: dict[tuple[str, str], float] = {}

    @property
    def channel(self) -> str:
        return self.webhook_url or "none"

    def _recently_sent(self, key: tuple[str, str]) -> bool:
        last = self._last_sent.get(key)
        return last is not None and (time.monotonic() - last) < self.dedupe_window_seconds

    async def deliver(self, escalation: dict[str, Any]) -> dict[str, Any]:
        key = (str(escalation.get("subsystem", "")), str(escalation.get("reason", "")))
        record = {
            "subsystem": escalation.get("subsystem"),
            "reason": escalation.get("reason"),
            "at": _utcnow().isoformat(),
            "channel": self.channel,
        }
        if self.webhook_url is None:
            record.update({"delivered": False, "detail": "no escalation channel configured"})
            self.deliveries.append(record)
            return record
        if self._recently_sent(key):
            self.suppressed += 1
            record.update({"delivered": False, "detail": "duplicate suppressed within dedupe window"})
            self.deliveries.append(record)
            return record

        import httpx

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.webhook_url, json=escalation)
            delivered = 200 <= response.status_code < 300
            record.update(
                {
                    "delivered": delivered,
                    "status_code": response.status_code,
                    "detail": "delivered" if delivered else f"channel returned {response.status_code}",
                }
            )
            if delivered:
                self._last_sent[key] = time.monotonic()
        except Exception as exc:  # noqa: BLE001 - a notification failure is not a healing failure
            record.update({"delivered": False, "detail": f"{type(exc).__name__}: {exc}"})
        self.deliveries.append(record)
        self.deliveries = self.deliveries[-50:]
        return record

    def status(self) -> dict[str, Any]:
        delivered = [d for d in self.deliveries if d.get("delivered")]
        return {
            "channel": self.channel,
            "channel_configured": self.webhook_url is not None,
            "attempts": len(self.deliveries),
            "delivered": len(delivered),
            "suppressed_duplicates": self.suppressed,
            "last_attempt": self.deliveries[-1] if self.deliveries else None,
        }
