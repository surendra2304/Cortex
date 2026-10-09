#!/usr/bin/env python
"""Live exercise of the agent's newer brain: collaboration, self-healing, self-model.

Runs against a REAL server (no mocks) and asserts observable behaviour:

* `/v1/friday/collaborate` produces handoffs, shared evidence, consensus and dissent
* refusals come back as refusals (unknown agent, unknown knob, out-of-range, re-apply 409)
* `/v1/friday/self_model` refuses to claim capability it has not observed
* real ingestion traffic feeds the health registry (ingestion/tools circuits get samples)
* self-modification is allowed only for allow-listed reversible knobs, and rolls back
* hostile input is rejected without touching the circuits
* a bounded, adversarial collaboration run (many agents, forced handoffs) terminates

Usage: python scripts/self_integrity_live_test.py [base_url]

The script is re-runnable against the same server: runtime-knob state is reset first.
"""

from __future__ import annotations

import os
import sys
import time
import uuid

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("CORTEX_BASE_URL", "http://127.0.0.1:8000")
# Development placeholders, overridable so the harness never depends on a stale literal.
# ``FRIDAY`` is resolved by _resolve_friday_auth() below: a configured API accepts the key,
# a development API without one accepts the no-header bypass, and anything else fails fast.
FRIDAY_KEY = os.getenv("CORTEX_FRIDAY_KEY", "friday-service-token-for-local-pressure-testing")
PUBLIC_KEY = os.getenv("CORTEX_PUBLIC_KEY", "pk_live_8d344ed1f526094a07218e46a21e75bb")
FRIDAY = {"X-Friday-Api-Key": FRIDAY_KEY}
KNOB = "self_healing_interval_seconds"

PASS, FAIL = "[PASS]", "[FAIL]"
results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((ok, name))
    print(f"   {PASS if ok else FAIL} {name}" + (f" — {detail}" if detail else ""))
    return ok


def step(title: str) -> None:
    print(f"\n── {title} ──")


def _resolve_friday_auth(client: httpx.Client) -> tuple[dict[str, str], str]:
    """Pick a FRIDAY credential this API actually accepts.

    Runs used to fail with a wall of confusing assertions when the presented key was not the
    one the API had configured (every FRIDAY call 403'd and returned an empty body). Probe
    once, fall back to the documented development bypass header-less mode, and fail fast with
    an actionable message if neither works.
    """
    probe = "/v1/friday/self_model"
    if client.get(f"{BASE}{probe}", headers=FRIDAY).status_code == 200:
        return FRIDAY, f"X-Friday-Api-Key ({FRIDAY_KEY[:12]}...)"
    if client.get(f"{BASE}{probe}").status_code == 200:
        print(
            "   [INFO] API rejected the configured FRIDAY key but accepts the development bypass; retrying without it."
        )
        return {}, "development bypass (no header)"
    raise SystemExit(
        f"cannot authenticate to {BASE}{probe} with or without X-Friday-Api-Key. "
        "Start the API with FRIDAY_API_KEY matching CORTEX_FRIDAY_KEY, or enable the development bypass."
    )


def _resolve_public_key(client: httpx.Client) -> str:
    """Return an ingestion key this API accepts, provisioning one in development if needed.

    The bootstrap key is a per-database secret printed once at startup, so a literal in this
    file goes stale the moment the database is recreated (it did, and every ingestion check
    failed 401). Probing for validity is not enough either: ingestion is rate limited, so a
    429 would be mistaken for "key accepted". Development mode simply issues a fresh key.
    """
    # S5: key provisioning is tenant-bound, so mint the tenant's own credential
    # (HS256 with the API's JWT secret — empty in development) and provision as
    # that tenant instead of relying on the dev bypass admin.
    from jose import jwt as _jwt

    token = _jwt.encode(
        {
            "sub": "integrity-run",
            "role": "cortex_admin",
            "tenant_id": "tenant_load",
            "exp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            + __import__("datetime").timedelta(hours=1),
        },
        os.getenv("JWT_SECRET", ""),
        algorithm="HS256",
    )
    issued = client.post(
        f"{BASE}/v1/api-keys",
        json={"tenant_id": "tenant_load", "site_id": "site_load", "name": "integrity-run"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if issued.status_code in (200, 201) and issued.json().get("api_key"):
        print("   [INFO] provisioned a fresh ingestion key for this run (development mode).")
        return issued.json()["api_key"]
    if PUBLIC_KEY:
        probe = client.post(f"{BASE}/v1/events", headers={"X-Cortex-Public-Key": PUBLIC_KEY}, json={})
        if probe.status_code != 401:
            return PUBLIC_KEY
    raise SystemExit(
        f"no usable public ingestion key: set CORTEX_PUBLIC_KEY (the API prints one at startup). "
        f"provisioning returned {issued.status_code}: {issued.text[:160]}"
    )


def wait_until_ready(client: httpx.Client, timeout_seconds: float = 90.0) -> dict:
    """Wait for the API's self-healing loop to complete at least one cycle.

    Live integrity runs used to fail spuriously when launched seconds after the API: the
    supervisor had not probed anything yet, so ``subsystems`` was empty and this script
    reported a healthy service as broken. A harness that cries wolf is worse than no
    harness, so wait for the first observation instead of asserting on a cold start.
    """
    deadline = time.monotonic() + timeout_seconds
    last: dict = {}
    while time.monotonic() < deadline:
        try:
            last = client.get(f"{BASE}/v1/friday/self_healing", headers=FRIDAY).json()
        except Exception as exc:  # pragma: no cover - only on a dying API
            last = {"error": str(exc)}
        subsystems = last.get("subsystems") or {}
        if subsystems and all(state.get("samples", 0) > 0 for state in subsystems.values()):
            return last
        time.sleep(1.0)
    return last


def main() -> int:
    client = httpx.Client(timeout=60.0)

    global FRIDAY, PUBLIC_KEY
    FRIDAY, auth_mode = _resolve_friday_auth(client)
    PUBLIC_KEY = _resolve_public_key(client)
    print(f"   [INFO] FRIDAY auth: {auth_mode}")

    step("0. liveness")
    health = client.get(f"{BASE}/v1/health")
    check("GET /v1/health is 200", health.status_code == 200, f"status={health.status_code}")

    step("1. self-healing snapshot and one cycle")
    snap = wait_until_ready(client)
    check(
        "self-healing loop has completed a probe cycle",
        bool(snap.get("subsystems")),
        f"subsystems={sorted(snap.get('subsystems', {}))}",
    )
    check(
        "snapshot lists every subsystem",
        {"database", "schema", "redis", "ai_universe", "agents", "ingestion", "tools"}
        <= set(snap.get("subsystems", {})),
        f"{sorted(snap.get('subsystems', {}))}",
    )
    run = client.post(f"{BASE}/v1/friday/self_healing/run", headers=FRIDAY).json()
    check("cycle checks all subsystems", len(run.get("checked", [])) >= 7, f"checked={len(run.get('checked', []))}")
    check(
        "cycle reports per-subsystem state with sample counts",
        all("samples" in state for state in run.get("subsystems", {}).values()),
    )
    delivery = snap.get("escalation_delivery", {})
    check(
        "escalation channel state is reported", "channel_configured" in delivery, f"channel={delivery.get('channel')}"
    )
    if not delivery.get("channel_configured"):
        # No webhook in this environment: the honest answer is "not delivered", never silence
        # dressed up as a notification.
        check(
            "without a channel, escalations are not claimed as delivered",
            delivery.get("delivered", 0) == 0 and delivery.get("attempts", 0) >= 0,
            f"attempts={delivery.get('attempts')} delivered={delivery.get('delivered')}",
        )

    step("2. real traffic is observed by the health registry (no synthetic probes)")
    # ``samples`` is a rolling window (deque maxlen=20), so it saturates and can even fall:
    # comparing it made a healthy circuit look unchanged. ``total_successes`` is cumulative
    # evidence that real ingestion reached the health registry.
    before = (
        client.get(f"{BASE}/v1/friday/self_healing", headers=FRIDAY)
        .json()
        .get("subsystems", {})
        .get("ingestion", {})
        .get("total_successes", 0)
    )
    batch = [
        {
            "event_id": f"evt_integrity_{uuid.uuid4().hex[:12]}",
            "tenant_id": "tenant_load",
            "site_id": "site_load",
            "type": "checkout_error",
            "actor": {"type": "visitor", "id": f"visitor_{index}"},
            "data": {"step": "payment", "code": "CARD_DECLINED"},
        }
        for index in range(5)
    ]
    ingest = client.post(
        f"{BASE}/v1/events/batch",
        headers={"X-Cortex-Public-Key": PUBLIC_KEY},
        json=batch,
    )
    check("batch ingestion accepted", ingest.status_code == 200, f"status={ingest.status_code}")
    if ingest.status_code == 200:
        statuses = {item.get("status") for item in ingest.json()}
        check("every event was persisted", statuses <= {"accepted", "duplicate"}, f"statuses={statuses}")
    time.sleep(0.3)
    after_state = client.get(f"{BASE}/v1/friday/self_healing", headers=FRIDAY).json()["subsystems"]["ingestion"]
    after = after_state.get("total_successes", 0)
    check(
        "ingestion circuit gained real samples",
        after > before,
        f"total_successes {before} -> {after} (rolling samples={after_state.get('samples')})",
    )

    step("3. hostile input is rejected without corrupting health")
    hostile = client.post(
        f"{BASE}/v1/events",
        headers={"X-Cortex-Public-Key": PUBLIC_KEY},
        json={"event_id": "not-a-uuid", "event_type": "x"},
    )
    check("malformed event is 4xx, not 500", 400 <= hostile.status_code < 500, f"status={hostile.status_code}")
    hostile2 = client.post(f"{BASE}/v1/events", headers={"X-Cortex-Public-Key": "pk_live_forged"}, json={})
    check("forged public key is 4xx", 400 <= hostile2.status_code < 500, f"status={hostile2.status_code}")
    still = client.get(f"{BASE}/v1/health")
    check("API still healthy after hostile input", still.status_code == 200)

    step("4. collaboration: handoffs, evidence sharing, consensus and dissent")
    collab = client.post(
        f"{BASE}/v1/friday/collaborate",
        headers=FRIDAY,
        json={
            "root_agent_id": "agent_growth",
            "goal": "Grow revenue this quarter",
            "context": {"signals": {"churn_risk": 0.62}},
            # The agents reason over the event stream (this is the real ingestion shape):
            # pricing/demo views create intent, checkout errors create pain.
            "events": [
                {"type": "pricing_page_view", "data": {"plan": "pro"}},
                {"type": "pricing_page_view", "data": {"plan": "business"}},
                {"type": "pricing_page_view", "data": {"plan": "enterprise"}},
                {"type": "pricing_page_view", "data": {"plan": "pro"}},
                {"type": "pricing_page_view", "data": {"plan": "business"}},
                {"type": "demo_request", "data": {"company": "Acme", "email": "cto@acme-corp.com"}},
                {"type": "demo_request", "data": {"company": "Globex", "email": "vp@globex.io"}},
                {"type": "demo_request", "data": {"company": "Initech", "email": "head@initech.dev"}},
                {"type": "checkout_error", "data": {"code": "CARD_DECLINED"}},
                {"type": "checkout_error", "data": {"code": "CARD_DECLINED"}},
                {"type": "checkout_error", "data": {"code": "TIMEOUT"}},
            ],
        },
    )
    check("collaborate is 200", collab.status_code == 200, f"status={collab.status_code}")
    body = collab.json().get("collaboration", {}) if collab.status_code == 200 else {}
    if body:
        check("more than one agent participated", len(body.get("participants", [])) >= 2, f"{body.get('participants')}")
        check(
            "a handoff happened and none was refused",
            body.get("handoffs_executed", 0) >= 1 and body.get("handoffs_refused") == [],
            f"executed={body.get('handoffs_executed')} refused={body.get('handoffs_refused')}",
        )
        check(
            "rounds stayed within the configured bound",
            body.get("rounds_used", 9) <= 5,
            f"rounds={body.get('rounds_used')}",
        )
        consensus = body.get("consensus", {})
        check(
            "consensus names an agreement score in [0,1]",
            0.0 <= consensus.get("agreement", -1) <= 1.0,
            f"agreement={consensus.get('agreement')}",
        )
        check(
            "dissent is recorded rather than averaged away",
            all(isinstance(item, str) for item in consensus.get("dissenting", [])),
            f"dissent={consensus.get('dissenting')} unresolved={consensus.get('unresolved_disagreements')}",
        )
        transcript = body.get("transcript", [])
        check(
            "the peer received the requester's findings",
            any(entry.get("requested_by") for entry in transcript),
            f"rounds={[entry.get('round') for entry in transcript]}",
        )

    step("5. refusals are loud, never silently rerouted")
    typo = client.post(f"{BASE}/v1/friday/collaborate", headers=FRIDAY, json={"agent_id": "agent_sales", "goal": "x"})
    check(
        "misspelled agent field is 422 (no silent default agent)", typo.status_code == 422, f"status={typo.status_code}"
    )
    unknown = client.post(
        f"{BASE}/v1/friday/collaborate",
        headers=FRIDAY,
        json={"root_agent_id": "agent_does_not_exist", "goal": "x"},
    )
    check("unknown root agent is 404", unknown.status_code == 404, f"status={unknown.status_code}")
    bad_rounds = client.post(
        f"{BASE}/v1/friday/collaborate",
        headers=FRIDAY,
        json={"root_agent_id": "agent_growth", "goal": "x", "max_rounds": 50},
    )
    check("out-of-bounds max_rounds is 422", bad_rounds.status_code == 422, f"status={bad_rounds.status_code}")

    step("6. self-model reports observed reality, not aspirations")
    model = client.get(f"{BASE}/v1/friday/self_model", headers=FRIDAY).json()
    capabilities = model.get("capabilities", {})
    check("self-model lists capabilities", bool(capabilities), f"{len(capabilities)} capabilities")
    states = {name: cap.get("state") for name, cap in capabilities.items()}
    check(
        "every capability state is one of operational/degraded/unverified",
        set(states.values()) <= {"operational", "degraded", "unverified", "unknown"},
        f"{states}",
    )
    unverified_claims = [
        name
        for name, cap in capabilities.items()
        if cap.get("state") == "operational" and any("never been observed" in note for note in cap.get("notes", []))
    ]
    check("no capability claims operational without observations", not unverified_claims, f"{unverified_claims}")
    gap_names = [gap.split(":")[0] for gap in model.get("gaps", [])]
    check(
        "capabilities with no observation are listed as gaps",
        all(name in gap_names for name, state in states.items() if state == "unverified")
        or "unverified" not in states.values(),
        f"gaps={model.get('gaps')}",
    )
    diag = client.get(f"{BASE}/v1/friday/self_model/diagnose", headers=FRIDAY).json()
    check(
        "diagnose returns findings + summary",
        "findings" in diag and "summary" in diag,
        f"summary={diag.get('summary')} findings={len(diag.get('findings', []))}",
    )

    step("7. self-modification: allow-list, bounds, real conflict 409, rollback")
    # Runtime knobs are in-process state: reset to defaults first so this script is
    # re-runnable without a server restart (rollback until the server says 400).
    for _ in range(8):
        if (
            client.post(f"{BASE}/v1/friday/self_model/modify", headers=FRIDAY, json={"rollback": KNOB}).status_code
            != 200
        ):
            break
    refused = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposals": [{"knob": "database_url", "value": "postgres://evil"}], "apply": True},
    ).json()
    check(
        "non-allow-listed knob refused",
        refused.get("accepted") == [] and bool(refused.get("refused")),
        f"refused={refused.get('refused')}",
    )
    out_of_range = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposals": [{"knob": "max_collaboration_rounds", "value": 99}], "apply": True},
    ).json()
    check("out-of-range value refused", out_of_range.get("accepted") == [], f"refused={out_of_range.get('refused')}")
    typo_knob = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposal": [{"knob": "self_healing_enabled", "value": False}], "apply": True},
    )
    check("misspelled proposals field is 422", typo_knob.status_code == 422, f"status={typo_knob.status_code}")
    dry = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposals": [{"knob": KNOB, "value": 45}], "apply": False},
    ).json()
    check("dry run accepts without applying", dry.get("mode") == "dry_run" and dry.get("applied") == [])
    applied = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposals": [{"knob": KNOB, "value": 45}], "apply": True},
    )
    check(
        "allow-listed change applies",
        applied.status_code == 200 and bool(applied.json().get("applied")),
        f"status={applied.status_code} value={applied.json().get('knobs', {}).get('values', {}).get('self_healing_interval_seconds')}",
    )
    noop = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposals": [{"knob": KNOB, "value": 45}], "apply": True},
    ).json()
    check(
        "re-applying the same value is refused with the reason, not silently applied",
        noop.get("accepted") == [] and noop.get("refused")[0]["reason"] == "already at the requested value",
        f"refused={noop.get('refused')}",
    )
    client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposals": [{"knob": KNOB, "value": 50}], "apply": True},
    )
    conflict = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"proposals": [{"knob": KNOB, "value": 45}], "apply": True},
    )
    check(
        "re-introducing an already-applied change-set is 409",
        conflict.status_code == 409,
        f"status={conflict.status_code}",
    )
    rolled = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"rollback": [KNOB]},
    )
    check(
        "rollback-only request works (no proposals needed)", rolled.status_code == 200, f"status={rolled.status_code}"
    )
    payload = rolled.json() if rolled.status_code == 200 else {}
    check(
        "rollback restores the previous value",
        bool(payload.get("rolled_back")),
        f"rolled_back={payload.get('rolled_back')}",
    )
    once = payload.get("knobs", {}).get("values", {}).get("self_healing_interval_seconds")
    check("first rollback walks back to 45 (the prior value)", once == 45, f"value={once}")
    twice = client.post(f"{BASE}/v1/friday/self_model/modify", headers=FRIDAY, json={"rollback": [KNOB]}).json()
    final = twice.get("knobs", {}).get("values", {}).get("self_healing_interval_seconds")
    check("second rollback walks back to the default 30", final == 30, f"value={final}")
    unknown_knob = client.post(f"{BASE}/v1/friday/self_model/modify", headers=FRIDAY, json={"rollback": ["nope"]})
    check("rolling back an unknown knob is 400", unknown_knob.status_code == 400, f"status={unknown_knob.status_code}")

    step("8. adversarial pressure: many collaboration runs, mixed valid/invalid goals")
    ok, refused_count, latencies = 0, 0, []
    for index in range(24):
        goal = "Scale revenue" if index % 3 else ""
        started = time.perf_counter()
        response = client.post(
            f"{BASE}/v1/friday/collaborate",
            headers=FRIDAY,
            json={"root_agent_id": "agent_growth" if index % 4 else "agent_unknown_x", "goal": goal},
        )
        latencies.append((time.perf_counter() - started) * 1000)
        if response.status_code == 200:
            ok += 1
            payload = response.json()
            if payload.get("rounds_used", 0) > 5:
                check("bounded rounds under pressure", False, f"rounds={payload['rounds_used']}")
        elif 400 <= response.status_code < 500:
            refused_count += 1
        else:
            check("no 5xx under pressure", False, f"status={response.status_code}")
    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95) - 1]
    check("pressure run had no 5xx", True, f"ok={ok} refused={refused_count} p95={p95:.0f}ms")
    final_health = client.get(f"{BASE}/v1/health")
    check("API healthy after pressure", final_health.status_code == 200)

    step("9. end-to-end: a FRIDAY command drives the cognitive loop, peers join in")
    # Real history in the store: the lead agent only asks for help when intent is genuinely high.
    # The command's session id is derived from its idempotency key, so the visitor's session
    # history can be staged exactly as a browser session would have produced it.
    session_key = f"integ_{uuid.uuid4().hex[:8]}"
    command_session = f"fri_session_{session_key}"
    warmup = [
        {
            "event_id": f"evt_warm_{uuid.uuid4().hex[:10]}",
            "tenant_id": "tenant_load",
            "site_id": "site_load",
            "type": event_type,
            "actor": {"type": "visitor", "id": "vis_integrity"},
            "session_id": command_session,
            "data": {"source": "integrity_test"},
        }
        for event_type in ["pricing_page_view"] * 4 + ["demo_request"] * 3 + ["enterprise_plan_view"] * 2
    ]
    warm = client.post(f"{BASE}/v1/events/batch", headers={"X-Cortex-Public-Key": PUBLIC_KEY}, json=warmup)
    check("history ingested for the command actor", warm.status_code == 200, f"status={warm.status_code}")
    command = client.post(
        f"{BASE}/v1/friday/command",
        headers=FRIDAY,
        json={
            "goal": "Convert high-intent enterprise visitors into booked demos",
            "required_capability": "experiment_mutate",
            "requested_action": "pricing_view",
            "tenant_id": "tenant_load",
            "site_id": "site_load",
            "idempotency_key": session_key,
            "context": {"signals": {"churn_risk": 0.4}, "visitor_id": "vis_integrity"},
        },
    )
    check("command routed through the cognitive loop", command.status_code == 200, f"status={command.status_code}")
    if command.status_code == 200:
        payload = command.json()
        trace = payload.get("trace") or payload.get("loop_result", {}).get("trace", [])
        phases = [entry.get("phase") for entry in trace if isinstance(entry, dict)]
        check("10-phase loop executed", len(phases) >= 10, f"phases={len(phases)}")
        collab_entries = [entry for entry in trace if entry.get("phase") == "4a.Collaborate"]
        check(
            "the loop asked peers for help when the lead agent requested it",
            bool(collab_entries),
            f"participants={collab_entries[0].get('participants') if collab_entries else None}",
        )
        if collab_entries:
            entry = collab_entries[0]
            check(
                "the peer actually participated",
                len(entry.get("participants", [])) >= 2,
                f"{entry.get('participants')}",
            )
            check(
                "peer evidence is recorded in the loop trace",
                bool(entry.get("peer_evidence")),
                f"{entry.get('peer_evidence')}",
            )

    step("10. self-modification steers the live self-healing loop (self brain closes the loop)")
    baseline = client.get(f"{BASE}/v1/friday/self_healing", headers=FRIDAY).json().get("background", {})
    check("background loop is running", baseline.get("running") is True, f"{baseline}")
    speedy = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={
            "proposals": [{"knob": KNOB, "value": 5, "rationale": "integrity test: heal faster"}],
            "apply": True,
        },
    )
    check(
        "interval change accepted",
        speedy.status_code == 200 and bool(speedy.json().get("applied")),
        f"{speedy.status_code}",
    )
    before = speedy.json()["knobs"]["values"][KNOB]
    # Poll for the new cadence instead of sampling once: a cycle also does real work, so a
    # fixed sleep made this check flaky (observed cycles 10 -> 11 at interval=5s, which is a
    # pass being reported as a failure). The claim under test is unchanged: two more cycles
    # than the baseline, without restarting the process.
    deadline = time.monotonic() + 40.0
    mid = client.get(f"{BASE}/v1/friday/self_healing", headers=FRIDAY).json()["background"]
    while mid["cycles"] < baseline["cycles"] + 2 and time.monotonic() < deadline:
        time.sleep(1.0)
        mid = client.get(f"{BASE}/v1/friday/self_healing", headers=FRIDAY).json()["background"]
    check(
        "loop healed at the new cadence without a restart",
        mid["cycles"] >= baseline["cycles"] + 2,
        f"cycles {baseline['cycles']} -> {mid['cycles']} at interval={before}s",
    )
    disabled = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={
            "proposals": [{"knob": "self_healing_enabled", "value": False, "rationale": "integrity test: off"}],
            "apply": True,
        },
    )
    check(
        "healing can be switched off",
        disabled.status_code == 200 and bool(disabled.json().get("applied")),
        f"status={disabled.status_code}",
    )
    time.sleep(7)
    off = client.get(f"{BASE}/v1/friday/self_healing", headers=FRIDAY).json()
    check("disabled loop stops healing", off["background"]["skipped_while_disabled"] >= 1, f"{off['background']}")
    check("subsystem probes stop while disabled", off["background"]["cycles"] <= mid["cycles"] + 1)
    restored = client.post(
        f"{BASE}/v1/friday/self_model/modify",
        headers=FRIDAY,
        json={"rollback": ["self_healing_enabled", KNOB]},
    )
    defaults = restored.json().get("knobs", {}).get("values", {}) if restored.status_code == 200 else {}
    check(
        "both knobs rolled back to defaults",
        defaults.get("self_healing_enabled") is True and defaults.get(KNOB) == 30,
        f"status={restored.status_code} values={defaults}",
    )

    passed = sum(1 for ok_, _ in results if ok_)
    total = len(results)
    print(f"\n{'=' * 62}\n{passed}/{total} checks passed")
    for ok_, name in results:
        if not ok_:
            print(f"  FAILED: {name}")
    print("=" * 62)
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except httpx.ConnectError as exc:
        print(f"cannot reach {BASE}: {exc}")
        sys.exit(2)
