import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from cortex_api.main import app
from cortex_core import (
    Account,
    Action,
    AgentRun,
    AuditRecord,
    Conversation,
    Customer,
    Event,
    Experiment,
    Incident,
    IntelligenceRequest,
    Lead,
    Memory,
    Opportunity,
    Profile,
    Session,
    Site,
    Tenant,
    Visitor,
    Workflow,
)
from cortex_event_schema import Actor, ActorType, EventSchema
from fastapi.testclient import TestClient


def test_core_models():
    t = Tenant(id="tenant_1", name="Test Org")
    site = Site(id="site_1", tenant_id=t.id, domain="example.com", name="Main Site")
    visitor = Visitor(id="vis_1", tenant_id=t.id, site_id=site.id)
    session = Session(id="sess_1", tenant_id=t.id, site_id=site.id, visitor_id=visitor.id)
    event = Event(id="evt_1", tenant_id=t.id, site_id=site.id, type="page_view", actor_id=visitor.id)
    profile = Profile(id="prof_1", tenant_id=t.id, primary_email="test@example.com")
    account = Account(id="acc_1", tenant_id=t.id, name="Acme Corp")
    conv = Conversation(id="conv_1", tenant_id=t.id, site_id=site.id)
    lead = Lead(id="lead_1", tenant_id=t.id, profile_id=profile.id, score=85.0)
    opp = Opportunity(id="opp_1", tenant_id=t.id, lead_id=lead.id, value=12000.0)
    cust = Customer(id="cust_1", tenant_id=t.id, profile_id=profile.id, plan="enterprise")
    wf = Workflow(id="wf_1", tenant_id=t.id, name="Lead Gen", trigger={"type": "event"})
    act = Action(id="act_1", tenant_id=t.id, action_type="send_email")
    exp = Experiment(id="exp_1", tenant_id=t.id, site_id=site.id, name="CTA Test")
    inc = Incident(id="inc_1", tenant_id=t.id, title="API latency spike")
    ar = AgentRun(id="run_1", tenant_id=t.id, agent_name="SupportAgent")
    ir = IntelligenceRequest(id="ir_1", tenant_id=t.id, query_type="intent_scoring")
    mem = Memory(id="mem_1", tenant_id=t.id, entity_type="visitor", entity_id=visitor.id, key="pref_lang", value="en")
    audit = AuditRecord(
        id="aud_1", tenant_id=t.id, actor_id="usr_1", action="create_tenant", target_resource="tenant/tenant_1"
    )

    # Every model must be constructible AND carry its identity and tenant binding.
    constructed = {
        "tenant": t,
        "site": site,
        "visitor": visitor,
        "session": session,
        "event": event,
        "profile": profile,
        "account": account,
        "conversation": conv,
        "lead": lead,
        "opportunity": opp,
        "customer": cust,
        "workflow": wf,
        "action": act,
        "experiment": exp,
        "incident": inc,
        "agent_run": ar,
        "intelligence_request": ir,
        "memory": mem,
        "audit": audit,
    }
    for name, model in constructed.items():
        assert model.id, f"{name} must carry an id"
        assert getattr(model, "tenant_id", t.id) == t.id, f"{name} must be tenant-scoped"
    assert t.id == "tenant_1"
    assert audit.target_resource == "tenant/tenant_1"


def test_event_schema_and_api():
    client = TestClient(app)
    res_health = client.get("/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"
    assert res_health.json()["evidence_class"] == "process_liveness"
    assert "observed_at" in res_health.json()

    evt_schema = EventSchema(
        event_id="evt_123",
        tenant_id="tenant_1",
        site_id="site_1",
        type="click",
        occurred_at=datetime.now(UTC),
        actor=Actor(type=ActorType.VISITOR, id="vis_123"),
        session_id="sess_123",
        source="web",
        data={"button": "signup_cta"},
        consent={"analytics": True},
        trace_id="trc_abc123",
    )
    # Ingestion is credential-bound: an anonymous post must be rejected (audit defect C1).
    res_event = client.post("/v1/events", json=evt_schema.model_dump(mode="json"))
    assert res_event.status_code == 401
    assert "X-Cortex-Public-Key" in res_event.json()["detail"]
