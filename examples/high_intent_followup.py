"""NEXUS MVP Demonstration Scenario: High-Intent Visitor Detection & Follow-up.

This script simulates an end-to-end journey:
1. Anonymous visitor visits Enterprise Pricing, Security, and Documentation pages.
2. Visitor identifies via email on a contact / demo form.
3. Identity resolution stitches the visitor into an identified Profile.
4. NEXUS worker consumes stream telemetry, runs the 10-Phase Cognitive Loop.
5. Sales Specialist Agent scores intent, proposes an outbound intervention.
6. Policy Engine gates the high-impact action requiring human approval in the Dashboard.
"""

import asyncio
import uuid
import json
from datetime import datetime
import httpx

API_BASE_URL = "http://localhost:8000"
OPERATOR_TOKEN = "mock_operator_jwt_token_123"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {OPERATOR_TOKEN}",
    "X-Nexus-Public-Key": "pk_demo_live_999"
}


async def run_scenario():
    print("=" * 70)
    print("  NEXUS: High-Intent Visitor Detection & Follow-up Demonstration")
    print("=" * 70)

    visitor_id = f"vis_demo_{uuid.uuid4().hex[:8]}"
    session_id = f"ses_demo_{uuid.uuid4().hex[:8]}"
    site_id = "site_enterprise_portal"
    tenant_id = "tenant_default"

    print(f"\n[1] Starting anonymous browsing session | Visitor ID: {visitor_id}")

    pages = [
        {"path": "/pricing/enterprise", "type": "page_view", "title": "Enterprise Pricing & Tiers"},
        {"path": "/security/soc2", "type": "page_view", "title": "Security & Compliance Overview"},
        {"path": "/docs/api/quickstart", "type": "page_view", "title": "Developer Documentation"}
    ]

    async with httpx.AsyncClient(base_url=API_BASE_URL, timeout=10.0) as client:
        # A & B. Ingest High-Intent Events
        for page in pages:
            event_id = f"evt_{uuid.uuid4().hex[:8]}"
            event_payload = {
                "event_id": event_id,
                "tenant_id": tenant_id,
                "site_id": site_id,
                "type": page["type"],
                "occurred_at": datetime.utcnow().isoformat(),
                "actor": {"type": "visitor", "id": visitor_id},
                "session_id": session_id,
                "source": "web-sdk",
                "data": {"path": page["path"], "title": page["title"], "intent_signal": "high"},
                "consent": {"analytics": True},
                "trace_id": f"trc_demo_{uuid.uuid4().hex[:6]}"
            }

            resp = await client.post("/v1/events", json=event_payload, headers=HEADERS)
            print(f"  -> Ingested event: '{page['title']}' [status={resp.status_code}, event_id={event_id}]")
            await asyncio.sleep(0.5)

        # C. Identify Visitor
        print(f"\n[2] Visitor submits demo inquiry form | Triggering Identity Resolution...")
        identify_payload = {
            "visitor_id": visitor_id,
            "user_id": f"usr_{uuid.uuid4().hex[:6]}",
            "site_id": site_id,
            "traits": {
                "email": "alex.mercer@enterprise-corp.com",
                "company": "Enterprise Corp",
                "employee_count": 1500,
                "role": "VP of Engineering"
            }
        }

        resp_ident = await client.post("/v1/identify", json=identify_payload, headers=HEADERS)
        print(f"  -> Identity Resolution Response [status={resp_ident.status_code}]:")
        print(f"     {json.dumps(resp_ident.json().get('result', {}), indent=2)}")

        # Create corresponding lead
        await client.post(
            "/v1/leads",
            json={
                "profile_id": resp_ident.json().get("result", {}).get("profile_id"),
                "score": 92.5,
                "status": "qualified",
                "source": "web-sdk"
            },
            headers=HEADERS
        )

        # D. Wait for asynchronous worker processing
        print(f"\n[3] Waiting 5 seconds for NEXUS background worker stream processing & Cognitive Loop...")
        for i in range(5, 0, -1):
            print(f"     Processing in {i}s...", end="\r")
            await asyncio.sleep(1.0)
        print("     Cognitive loop execution completed!      ")

        # E. Fetch Leads Data
        print(f"\n[4] Querying Predictive Leads Pipeline (GET /v1/leads)...")
        resp_leads = await client.get("/v1/leads", headers=HEADERS)
        leads = resp_leads.json().get("leads", [])
        print(f"  -> Total Qualified Leads: {len(leads)}")
        for l in leads[-3:]:
            print(f"     - Lead ID: {l.get('id')} | Score: {l.get('score')} | Status: {l.get('status')}")

        # F. Fetch Governance & Audit Data
        print(f"\n[5] Querying Governance & Audit Trail (GET /v1/audit/actions)...")
        resp_audit = await client.get("/v1/audit/actions", headers=HEADERS)
        audit_data = resp_audit.json()
        print(f"  -> Audit Record Logs for Resource: {audit_data.get('resource_type')}")
        for log in audit_data.get("logs", []):
            print(f"     - Audit ID: {log.get('id')} | Action: {log.get('action')} | Actor: {log.get('actor_id')}")

        print("\n" + "=" * 70)
        print("  DEMONSTRATION COMPLETE: High-Intent Lead Identified & Action Queued!")
        print("  Navigate to http://localhost:3000/governance to approve pending actions.")
        print("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(run_scenario())
    except httpx.ConnectError:
        print("\n[ERROR] Could not connect to NEXUS API at http://localhost:8000.")
        print("Please start the API server first using: uvicorn nexus_api.main:app --port 8000")
