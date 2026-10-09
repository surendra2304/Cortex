#!/usr/bin/env python3
"""Operator gauntlet: drive CORTEX like its owner does, against the LIVE API.

Gives the agent real tasks the way an operator would — register a web property,
hand FRIDAY governed tasks (recommend → approve → execute), walk the approval
queue, run workflows, and push every dead end (unknown agents, invalid
payloads, re-decides, cross-tenant reads, unknown knobs) — asserting the
observable behaviour at each step.

Usage: python scripts/operator_gauntlet_live_test.py [base_url]
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta

BASE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("CORTEX_BASE_URL", "http://127.0.0.1:8000")

PASS = 0
FAIL = 0


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None, raw: bytes | None = None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return response.status, json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:300]
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"   [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"   [FAIL] {name} — {detail}")


def step(label: str) -> None:
    print(f"\n── {label} ──")


def friday_headers() -> dict[str, str]:
    """Resolve a FRIDAY credential this API accepts (configured key, else dev bypass)."""
    key = os.getenv("CORTEX_FRIDAY_KEY", "")
    if key:
        status, _ = call("GET", "/v1/friday/self_model", headers={"X-Friday-Api-Key": key})
        if status == 200:
            return {"X-Friday-Api-Key": key}
    status, _ = call("GET", "/v1/friday/self_model")
    if status == 200:
        return {}
    raise SystemExit(f"cannot authenticate to {BASE}/v1/friday/self_model (FRIDAY key or dev bypass required)")


def jwt_for(tenant_id: str, role: str = "cortex_admin") -> str:
    """Mint an HS256 operator JWT the way the API verifies it (dev: empty secret)."""
    from jose import jwt

    return jwt.encode(
        {
            "sub": "op_gauntlet",
            "tenant_id": tenant_id,
            "role": role,
            "exp": datetime.now(UTC) + timedelta(hours=1),
        },
        os.getenv("JWT_SECRET", ""),
        algorithm="HS256",
    )


def main() -> int:
    F = friday_headers()
    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_gauntlet_{suffix}"
    site = f"site_gauntlet_{suffix}"
    prop = f"prop_{suffix}"
    visitor = f"vis_gauntlet_{suffix}"
    task_id = f"gauntlet_task_{suffix}"
    exec_task_id = f"gauntlet_exec_{suffix}"

    step("0. the agent is alive")
    status, health = call("GET", "/health")
    check("API liveness", status == 200 and health.get("status") == "UP", f"{status}")
    status, ready = call("GET", "/health/ready")
    check("readiness probe", status == 200, f"{status}")

    step("1. provision a tenant + ingestion key like an operator would")
    status, tenant_res = call("POST", "/v1/tenants", {"tenant_name": "Gauntlet Corp", "admin_email": f"ops@{suffix}.example", "plan": "pro"})
    check("tenant onboarding", status == 201 and "ten_" in tenant_res.get("tenant_id", ""), f"{status}")
    # S5: key provisioning is tenant-bound — mint the tenant's own credential.
    status, key_res = call(
        "POST", "/v1/api-keys", {"tenant_id": tenant, "site_id": site, "name": "gauntlet"},
        headers={"Authorization": f"Bearer {jwt_for(tenant)}"},
    )
    check("ingestion key provisioned", status == 201 and key_res.get("api_key", "").startswith("pk_live_"), f"{status}")
    public_key = key_res["api_key"]

    step("2. register a web property under governance")
    status, prop_res = call(
        "POST",
        "/v1/friday/properties/register",
        {
            "property_id": prop,
            "name": "Gauntlet Storefront",
            "allowed_domains": [f"store-{suffix}.example"],
            "allowed_operations": ["banner_injection", "email_dispatch"],
            "target_environment": "staging",
        },
        headers=F,
    )
    check("property registered", status == 200, f"{status} {str(prop_res)[:120]}")
    status, props = call("GET", "/v1/friday/properties", headers=F)
    listed = props.get("properties", props if isinstance(props, list) else [])
    check("property listed", status == 200 and any(p.get("property_id") == prop for p in listed), f"{status}")

    step("3. give the agent a governed task (recommend a high-impact intervention)")
    status, task = call(
        "POST",
        "/v1/friday/task",
        {
            "task_id": task_id,
            "action": "recommend_intervention",
            "payload": {
                "property_id": prop,
                "environment": "staging",
                "proposed_operation": "banner_injection",
                "params": {"variant": "gauntlet_cta", "discount_pct": 10},
                "rationale": "Gauntlet: high-intent visitor saw pricing twice",
                "telemetry": {"source": "web_telemetry", "timestamp": datetime.now(UTC).isoformat()},
            },
        },
        headers=F,
    )
    rec = ((task or {}).get("result") or {}).get("recommendation") or {}
    recommendation_id = rec.get("recommendation_id")
    check(
        "recommendation created, gated for approval",
        status == 200 and rec.get("requires_approval") is True and bool(recommendation_id),
        f"{status} state={task.get('state')} requires_approval={rec.get('requires_approval')}",
    )
    check("recommendation is not authorization", "not authorization" in str(task.get("summary", "")).lower(), str(task.get("summary", ""))[:100])

    step("4. approve the recommendation — then execute it explicitly")
    status, decision = call(
        "POST", f"/v1/friday/approvals/{recommendation_id}/decide", {"approved": True, "approver_id": "op_gauntlet", "reason": "go"}, headers=F
    )
    check("approval decided", status == 200 and decision.get("approved") is True, f"{status} {str(decision)[:150]}")
    status, again = call("POST", f"/v1/friday/approvals/{recommendation_id}/decide", {"approved": True}, headers=F)
    check("re-decide refused (409)", status == 409, f"{status}")

    status, exec_res = call(
        "POST",
        "/v1/friday/task",
        {
            "task_id": exec_task_id,
            "action": "execute_operation",
            "payload": {
                "property_id": prop,
                "environment": "staging",
                "operation": "banner_injection",
                "params": {"variant": "gauntlet_cta", "discount_pct": 10},
                "approved": True,
                "approver_id": "op_gauntlet",
            },
        },
        headers=F,
    )
    classification = str(exec_res.get("classification") or "")
    check(
        "approved execution completes (REAL, not simulated/unclassified)",
        status == 200 and exec_res.get("state") == "COMPLETED" and classification.startswith("REAL"),
        f"{status} state={exec_res.get('state')} classification={classification}",
    )
    status, task_status = call("GET", f"/v1/friday/task/{exec_task_id}/status", headers=F)
    check("task status readable", status == 200 and task_status.get("state") == "COMPLETED", f"{status}")

    step("5. reject path: a second recommendation, rejected")
    status, task2 = call(
        "POST",
        "/v1/friday/task",
        {
            "task_id": f"gauntlet_reject_{suffix}",
            "action": "recommend_intervention",
            "payload": {
                "property_id": prop,
                "environment": "staging",
                "proposed_operation": "email_dispatch",
                "params": {"template": "blast"},
                "rationale": "gauntlet reject-path test",
                "telemetry": {"source": "web_telemetry", "timestamp": datetime.now(UTC).isoformat()},
            },
        },
        headers=F,
    )
    rec2 = ((task2 or {}).get("result") or {}).get("recommendation") or {}
    status, rej = call(
        "POST", f"/v1/friday/approvals/{rec2.get('recommendation_id')}/decide",
        {"approved": False, "approver_id": "op_gauntlet", "reason": "too aggressive"}, headers=F,
    )
    check("rejection recorded", status == 200 and rej.get("approved") is False, f"{status}")

    step("6. task cancel + rollback")
    status, cancel = call("POST", f"/v1/friday/tasks/{task_id}/cancel", {"reason": "gauntlet cancel"}, headers=F)
    check("cancel transitions state", status == 200 and cancel.get("state") == "CANCELLED", f"{status} {str(cancel)[:120]}")
    status, rollback = call("POST", f"/v1/friday/tasks/{exec_task_id}/rollback", headers=F)
    check("rollback handled", status in (200, 400, 404), f"{status} {str(rollback)[:120]}")

    step("7. fail-closed on bad actions")
    status, _ = call(
        "POST", "/v1/friday/task",
        {"task_id": f"gauntlet_bad_{suffix}", "action": "banner_injection", "payload": {"property_id": prop, "environment": "staging"}},
        headers=F,
    )
    check("unsupported top-level action → 422", status == 422, f"{status}")
    status, _ = call(
        "POST", "/v1/friday/task",
        {"task_id": f"gauntlet_bad2_{suffix}", "action": "recommend_intervention", "payload": {"property_id": prop, "environment": "staging", "proposed_operation": "self_destruct"}},
        headers=F,
    )
    check("disallowed operation → 403", status == 403, f"{status}")
    status, _ = call(
        "POST", "/v1/friday/task",
        {"task_id": f"gauntlet_bad3_{suffix}", "action": "execute_operation", "payload": {"property_id": prop, "environment": "staging", "operation": "banner_injection"}},
        headers=F,
    )
    check("unapproved high-impact execution → 403", status == 403, f"{status}")

    step("8. universal task protocol")
    status, ute = call(
        "POST", "/v1/task/execute",
        {"action": "health_summary", "payload": {"property_id": prop, "environment": "staging"}},
        headers=F,
    )
    check("task protocol responds", status in (200, 201, 202) and ute.get("status") == "SUCCESS", f"{status} {str(ute)[:120]}")

    step("9. workflows: run one and read it back")
    status, run = call("POST", "/v1/workflows/HIGH_INTENT_FOLLOWUP/run", {"tenant_id": tenant, "site_id": site, "context": {"visitor_id": visitor}}, headers=F)
    check("workflow run accepted", status in (200, 201, 202), f"{status} {str(run)[:150]}")
    run_id = (run or {}).get("run_id") or (run or {}).get("id")
    if run_id:
        status, run_read = call("GET", f"/v1/workflows/runs/{run_id}")
        check("workflow run readable", status == 200, f"{status}")
    status, catalog = call("GET", "/v1/workflows")
    check("workflow catalog is the real one", status == 200 and isinstance(catalog, list) and any("HIGH_INTENT_FOLLOWUP" in str(w) for w in catalog), f"{status}")

    step("10. collaboration: peers join, nonsense refused")
    status, collab = call(
        "POST", "/v1/friday/collaborate",
        {
            "goal": "Qualify this high-intent visitor and pick the outreach channel",
            "root_agent_id": "agent_growth",
            "context": {"intent_score": 0.9, "pricing_views": 3, "tenant_id": tenant, "site_id": site},
            "events": [{"type": "pricing_page_view", "data": {}}],
        },
        headers=F,
    )
    collab_body = (collab or {}).get("collaboration") or collab or {}
    participants = collab_body.get("participants") or []
    check(
        "collaboration runs with consensus",
        status == 200 and bool(collab_body.get("consensus")) and bool(participants),
        f"{status} participants={participants}",
    )
    status, bad_collab = call(
        "POST", "/v1/friday/collaborate",
        {"goal": "x", "root_agent_id": "agent_nonexistent", "context": {}},
        headers=F,
    )
    check("unknown agent refused", status in (400, 404, 422), f"{status}")

    step("11. self-modification: allow-listed knob, refusals, rollback")
    call("POST", "/v1/friday/self_model/modify", {"rollback": ["max_collaboration_rounds"]}, headers=F)
    status, mod = call("POST", "/v1/friday/self_model/modify", {"proposals": [{"knob": "max_collaboration_rounds", "value": 4, "rationale": "gauntlet"}], "apply": True}, headers=F)
    check("allow-listed knob applied", status == 200 and bool(mod.get("applied")), f"{status}")
    status, bad_knob = call("POST", "/v1/friday/self_model/modify", {"proposals": [{"knob": "delete_everything", "value": True}], "apply": True}, headers=F)
    check("unknown knob refused", status == 200 and bool(bad_knob.get("refused")), f"{status}")
    status, oob = call("POST", "/v1/friday/self_model/modify", {"proposals": [{"knob": "max_collaboration_rounds", "value": 99}], "apply": True}, headers=F)
    check("out-of-range refused", status == 200 and bool(oob.get("refused")), f"{status}")
    status, rb = call("POST", "/v1/friday/self_model/modify", {"rollback": ["max_collaboration_rounds"]}, headers=F)
    check("rollback works", status == 200 and bool(rb.get("rolled_back")), f"{status} {str(rb)[:120]}")

    step("12. intelligence & predictive surfaces")
    for path in [
        "/v1/friday/priority_leads",
        "/v1/friday/incidents",
        "/v1/friday/market_trends",
        "/v1/friday/competitive_summary",
        "/v1/friday/health_summary",
        "/v1/predictive/traffic-forecast",
        "/v1/predictive/churn-risk",
        "/v1/predictive/conversion-trends",
    ]:
        status, body = call("GET", f"{path}?site_id={site}" + (f"&tenant_id={tenant}" if "friday" in path else ""), headers=F)
        check(f"GET {path}", status == 200, f"{status} {str(body)[:80]}")

    step("13. sentinel: push a finding, read posture, gate a deployment")
    status, finding = call(
        "POST", "/v1/sentinel/findings",
        {"sentinel_task_id": f"task_{suffix}", "asset_id": site, "posture_score": 62.5,
         "findings": [{"finding_id": f"f_{suffix}", "severity": "high", "title": "gauntlet test finding", "description": "test", "evidence_ref": "gauntlet"}]},
        headers=F,
    )
    check("finding ingested", status in (200, 201, 202), f"{status} {str(finding)[:120]}")
    status, findings = call("GET", f"/v1/sentinel/findings?asset_id={site}")
    check("findings readable", status == 200, f"{status}")
    status, gate = call("POST", "/v1/security/deployment-gate/evaluate", {"deployment_id": f"dep_{suffix}", "asset_id": site, "endpoints": ["/api/checkout"], "simulated_findings": [{"severity": "critical", "title": "test"}]}, headers=F)
    check("deployment gate blocks critical", status == 200 and "BLOCK" in str(gate.get("verdict", gate)).upper(), f"{status} {str(gate)[:120]}")

    step("14. GDPR round trip on a real visitor")
    status, ident = call("POST", "/v1/identify", {"visitor_id": visitor, "email": f"gdpr@{suffix}.example", "site_id": site, "consent_granted": True, "traits": {"company": "Gauntlet"}})
    check("visitor identified", status == 200, f"{status}")
    status, export = call("POST", f"/privacy/export/{visitor}")
    check(
        "Art. 15 export returns the subject's own email",
        status == 200 and export.get("profile_data", {}).get("email") == f"gdpr@{suffix}.example",
        f"{status} {str(export)[:150]}",
    )
    status, erased = call("POST", f"/privacy/delete/{visitor}", {"reason": "gauntlet test"})
    check("Art. 17 erasure executes", status == 200 and erased.get("status") in ("ERASED", "NO_RECORDS_FOUND"), f"{status} {str(erased)[:120]}")
    status, gone = call("POST", f"/privacy/export/{visitor}")
    check("erased data is gone (404)", status == 404, f"{status}")

    step("15. dead ends: hostile and malformed input")
    status, _ = call("POST", "/v1/events", {"not": "an event"}, headers={"X-Cortex-Public-Key": public_key})
    check("malformed event → 422", status == 422, f"{status}")
    big_event = {
        "event_id": f"evt_big_{suffix}",
        "tenant_id": tenant,
        "site_id": site,
        "type": "page_view",
        "occurred_at": datetime.now(UTC).isoformat(),
        "actor": {"type": "visitor", "id": visitor},
        "source": "web",
        "data": {"blob": "A" * 300000},
    }
    status, _ = call("POST", "/v1/events", raw=json.dumps(big_event).encode(), headers={"X-Cortex-Public-Key": public_key})
    check("oversized payload → 413", status == 413, f"{status}")
    status, _ = call("GET", f"/v1/visitors/{visitor}")
    check("unknown visitor → 404 (no PII leak)", status == 404, f"{status}")
    status, _ = call("POST", "/v1/friday/approvals/does_not_exist/decide", {"approved": True}, headers=F)
    check("unknown approval → 404", status == 404, f"{status}")
    status, _ = call("POST", "/v1/friday/task", {"task_id": f"gauntlet_bad4_{suffix}", "action": "health_summary", "payload": {"property_id": "no_such_prop"}}, headers=F)
    check("unknown property handled (4xx)", status in (400, 404), f"{status}")

    step("16. ingestion → worker → loop (the real pipeline)")
    event = {
        "event_id": f"evt_gauntlet_{suffix}",
        "tenant_id": tenant,
        "site_id": site,
        "type": "checkout.completed",
        "occurred_at": datetime.now(UTC).isoformat(),
        "actor": {"type": "visitor", "id": visitor},
        "source": "web",
        "data": {"amount": 42.0},
        "trace_id": f"trc_gauntlet_{suffix}",
    }
    status, ingested = call("POST", "/v1/events", event, headers={"X-Cortex-Public-Key": public_key})
    check("event accepted", status in (200, 202) and ingested.get("status") == "accepted", f"{status}")
    status, events = call("GET", "/v1/events?limit=10", headers={"Authorization": f"Bearer {jwt_for(tenant)}"})
    check("event readable back in its own tenant", status == 200 and any(e.get("event_id") == f"evt_gauntlet_{suffix}" for e in events), f"{status}")
    status, other = call("GET", "/v1/events?limit=10", headers={"Authorization": f"Bearer {jwt_for('tenant_someone_else')}"})
    check("other tenants cannot read it", status == 200 and all(e.get("event_id") != f"evt_gauntlet_{suffix}" for e in other), f"{status}")

    print("\n" + "=" * 60)
    print(f"operator gauntlet: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
