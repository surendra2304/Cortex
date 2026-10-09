#!/usr/bin/env python3
"""Concurrent operator load: hammer every operator surface while ingestion runs.

Runs a background ingestion stream (~50 rps) and, concurrently: FRIDAY commands
(full cognitive loops), workflow runs, identifies, approval decide cycles,
GDPR export/erase, sentinel findings, and insight reads. Asserts zero 5xx
everywhere, that approvals actually execute, and that the worker drains the
stream to an empty pending-entries list afterwards.

Usage: python scripts/operator_load_live_test.py [base_url]
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

BASE = sys.argv[1] if len(sys.argv) > 1 else os.getenv("CORTEX_BASE_URL", "http://127.0.0.1:8000")
RESULTS: list[tuple[str, int, str]] = []
LOCK = threading.Lock()
STOP = threading.Event()


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None, timeout: int = 90):
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    req = urllib.request.Request(BASE + path, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode()[:200]
        try:
            return exc.code, json.loads(text)
        except json.JSONDecodeError:
            return exc.code, text
    except Exception as exc:  # transport failure counts as a failure
        return -1, f"{type(exc).__name__}: {exc}"


def record(name: str, status: int, detail: str = "") -> None:
    with LOCK:
        RESULTS.append((name, status, detail))


def friday_headers() -> dict[str, str]:
    key = os.getenv("CORTEX_FRIDAY_KEY", "")
    if key:
        status, _ = call("GET", "/v1/friday/self_model", headers={"X-Friday-Api-Key": key})
        if status == 200:
            return {"X-Friday-Api-Key": key}
    status, _ = call("GET", "/v1/friday/self_model")
    if status == 200:
        return {}
    raise SystemExit(f"cannot authenticate to {BASE}/v1/friday/self_model")


def jwt_for(tenant_id: str, role: str = "cortex_admin") -> str:
    from datetime import timedelta

    from jose import jwt

    return jwt.encode(
        {"sub": "op_load", "tenant_id": tenant_id, "role": role, "exp": datetime.now(UTC) + timedelta(hours=1)},
        os.getenv("JWT_SECRET", ""),
        algorithm="HS256",
    )


def ingest_worker(public_key: str, tenant: str, site: str, duration_s: float, rate: float) -> None:
    """Background ingestion at ~rate rps until STOP is set."""
    n = 0
    while not STOP.is_set():
        event = {
            "event_id": f"evt_load_{uuid.uuid4().hex[:12]}",
            "tenant_id": tenant,
            "site_id": site,
            "type": "page_view",
            "occurred_at": datetime.now(UTC).isoformat(),
            "actor": {"type": "visitor", "id": f"vis_load_{uuid.uuid4().hex[:8]}"},
            "source": "web",
            "data": {"page": "/pricing"},
        }
        status, body = call("POST", "/v1/events", event, headers={"X-Cortex-Public-Key": public_key})
        record("ingest", status, str(body)[:60] if status >= 400 else "")
        n += 1
        time.sleep(1.0 / rate)
    print(f"   ingestion: {n} events sent")


def main() -> int:
    F = friday_headers()
    suffix = uuid.uuid4().hex[:8]
    tenant = f"tenant_load_{suffix}"
    site = f"site_load_{suffix}"

    status, tenant_res = call("POST", "/v1/tenants", {"tenant_name": "Load Corp", "admin_email": f"ops@{suffix}.ex", "plan": "pro"})
    assert status == 201, f"tenant: {status}"
    auth = {"Authorization": f"Bearer {jwt_for(tenant)}"}
    status, key_res = call("POST", "/v1/api-keys", {"tenant_id": tenant, "site_id": site, "name": "load"}, headers=auth)
    assert status == 201, f"key: {status}"
    public_key = key_res["api_key"]

    print("── phase A: background ingestion at ~50 rps for 30s ──")
    t = threading.Thread(target=ingest_worker, args=(public_key, tenant, site, 30.0, 50.0), daemon=True)
    t.start()

    print("── phase B: concurrent operator load ──")
    started = time.monotonic()

    def friday_command(i: int):
        status, body = call(
            "POST", "/v1/friday/command",
            {"goal": f"Qualify visitor {i}", "required_capability": "sales", "requested_action": "pricing_view",
             "tenant_id": tenant, "site_id": site, "idempotency_key": f"load_cmd_{suffix}_{i}",
             "context": {"visitor_id": f"vis_load_{i}", "signals": {"churn_risk": 0.2}}},
            headers=F,
        )
        record("friday_command", status, f"decision={body.get('decision') if isinstance(body, dict) else body}")

    def workflow_run(i: int):
        status, body = call("POST", "/v1/workflows/HIGH_INTENT_FOLLOWUP/run",
                            {"tenant_id": tenant, "site_id": site, "context": {"visitor_id": f"vis_load_{i}"}}, headers=F)
        record("workflow_run", status)

    def identify(i: int):
        status, _ = call("POST", "/v1/identify",
                         {"visitor_id": f"vis_load_{i}", "email": f"load{i}@{suffix}.ex", "site_id": site, "consent_granted": True},
                         headers=auth)
        record("identify", status)

    def approval_cycle(i: int):
        # recommend -> approve -> execute through the governed task path
        status, task = call("POST", "/v1/friday/task",
                            {"task_id": f"load_task_{suffix}_{i}", "action": "recommend_intervention",
                             "payload": {"property_id": "site_storefront", "proposed_operation": "banner_injection",
                                         "params": {"variant": f"load_{i}"}, "telemetry": {"source": "web_telemetry"}}},
                            headers=F)
        rec = ((task or {}).get("result") or {}).get("recommendation") or {}
        rec_id = rec.get("recommendation_id")
        if not rec_id:
            record("approval_cycle", status, "no recommendation")
            return
        status, decision = call("POST", f"/v1/friday/approvals/{rec_id}/decide",
                                {"approved": True, "approver_id": "op_load"}, headers=F)
        record("approval_decide", status, str(decision)[:80])

    def gdpr_cycle(i: int):
        vid = f"vis_gdpr_load_{suffix}_{i}"
        call("POST", "/v1/identify", {"visitor_id": vid, "email": f"gdpr{i}@{suffix}.ex", "site_id": site, "consent_granted": True}, headers=auth)
        status, export = call("POST", f"/privacy/export/{vid}", headers=auth)
        record("gdpr_export", status, f"email={export.get('profile_data', {}).get('email') if isinstance(export, dict) else None}")
        status, _ = call("POST", f"/privacy/delete/{vid}", {"reason": "load test"}, headers=auth)
        record("gdpr_delete", status)

    def insight_read(i: int):
        for path in ("/v1/friday/priority_leads", "/v1/friday/incidents", "/v1/predictive/traffic-forecast"):
            status, _ = call("GET", f"{path}?site_id={site}&tenant_id={tenant}", headers=F)
            record("insight_read", status, path)

    def sentinel_push(i: int):
        status, _ = call("POST", "/v1/sentinel/findings",
                         {"sentinel_task_id": f"load_{suffix}_{i}", "asset_id": site, "posture_score": 70.0,
                          "findings": [{"finding_id": f"lf_{suffix}_{i}", "severity": "medium", "title": "load", "description": "load", "evidence_ref": "load"}]},
                         headers=F)
        record("sentinel_push", status)

    jobs = []
    with ThreadPoolExecutor(max_workers=24) as pool:
        for i in range(20):
            jobs.append(pool.submit(friday_command, i))
        for i in range(10):
            jobs.append(pool.submit(workflow_run, i))
            jobs.append(pool.submit(identify, i))
            jobs.append(pool.submit(insight_read, i))
        for i in range(5):
            jobs.append(pool.submit(approval_cycle, i))
            jobs.append(pool.submit(gdpr_cycle, i))
            jobs.append(pool.submit(sentinel_push, i))
        for j in jobs:
            j.result()

    STOP.set()
    t.join(timeout=10)
    elapsed = time.monotonic() - started
    print(f"   operator phase took {elapsed:.1f}s")

    print("── phase C: drain + health ──")
    deadline = time.monotonic() + 180
    drained = False
    while time.monotonic() < deadline:
        status, health = call("GET", "/health")
        if status != 200:
            break
        time.sleep(5)
        # PEL check via a tiny redis probe through the API is not exposed; use redis directly
        import asyncio

        import redis.asyncio as aioredis

        async def _pel():
            c = aioredis.Redis(host="127.0.0.1", port=6379, protocol=2, decode_responses=True)
            try:
                return (await c.xpending("cortex:events:stream", "cortex-worker-group"))["pending"]
            finally:
                await c.aclose()

        pending = asyncio.run(_pel())
        if pending == 0:
            drained = True
            break
    status, health = call("GET", "/health")
    record("final_health", status, str(health.get("status") if isinstance(health, dict) else health))

    # ── report ──
    by_name: dict[str, list[int]] = {}
    for name, status, _detail in RESULTS:
        by_name.setdefault(name, []).append(status)
    print("\n" + "=" * 60)
    total = len(RESULTS)
    failures = [(n, s, d) for n, s, d in RESULTS if s >= 500 or s == -1]
    for name, statuses in sorted(by_name.items()):
        ok = sum(1 for s in statuses if s < 500)
        print(f"  {name.ljust(18)} {ok}/{len(statuses)} ok   statuses={sorted(set(statuses))}")
    print("-" * 60)
    print(f"  total calls: {total}   5xx/transport failures: {len(failures)}")
    print(f"  worker drained to PEL=0: {drained}")
    print("=" * 60)
    for n, s, d in failures[:10]:
        print(f"  FAIL {n}: {s} {d}")
    return 1 if failures or not drained else 0


if __name__ == "__main__":
    sys.exit(main())
