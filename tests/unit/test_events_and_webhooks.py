import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from fastapi.testclient import TestClient
from nexus_api.main import app
from nexus_api.events_router import EVENT_STORE, EVENT_QUEUE, RATE_LIMIT_BUCKET

client = TestClient(app)


def test_health():
    res = client.get("/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "healthy"


def test_events_gateway_ingest():
    payload = {
        "event_id": "evt_test_1",
        "tenant_id": "tenant_xyz",
        "site_id": "site_123",
        "type": "pricing_view",
        "occurred_at": datetime.utcnow().isoformat(),
        "actor": {"type": "visitor", "id": "vis_999"},
        "session_id": "ses_888",
        "source": "web-sdk",
        "data": {"plan": "enterprise"},
        "consent": {"analytics": True},
        "trace_id": "trc_111"
    }

    res = client.post("/v1/events", json=payload, headers={"X-Nexus-Public-Key": "pub_live_abc"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "accepted"
    assert data["event_id"] == "evt_test_1"

    # Verify server-side enrichment in event store
    stored = next(e for e in EVENT_STORE if e["event_id"] == "evt_test_1")
    assert "_server" in stored["data"]
    assert stored["data"]["_server"]["public_key_present"] is True


def test_webhooks_ingest():
    webhook_payload = {
        "event": "checkout.completed",
        "customer_id": "usr_cust_777",
        "amount": 4900,
        "currency": "usd"
    }

    res = client.post(
        "/v1/webhooks/stripe",
        json=webhook_payload,
        headers={"X-Nexus-Signature": "sig_test_123", "X-Tenant-ID": "tenant_xyz", "X-Site-ID": "store_1"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "received"
    assert body["provider"] == "stripe"
    assert body["event_type"] == "checkout.completed"
