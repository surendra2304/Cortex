import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from cortex_core import (
    Tenant, Site, Visitor, Session, Event, Profile, Account,
    Conversation, Lead, Opportunity, Customer, Workflow, Action,
    Experiment, Incident, AgentRun, IntelligenceRequest, Memory, AuditRecord
)
from cortex_event_schema import EventSchema, Actor, ActorType
from fastapi.testclient import TestClient
from cortex_api.main import app


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
    audit = AuditRecord(id="aud_1", tenant_id=t.id, actor_id="usr_1", action="create_tenant", target_resource="tenant/tenant_1")
    assert t.id == "tenant_1"
    assert audit.target_resource == "tenant/tenant_1"


def test_event_schema_and_api():
    client = TestClient(app)
    res_health = client.get("/v1/health")
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    evt_schema = EventSchema(
        event_id="evt_123",
        tenant_id="tenant_1",
        site_id="site_1",
        type="click",
        occurred_at=datetime.utcnow(),
        actor=Actor(type=ActorType.VISITOR, id="vis_123"),
        session_id="sess_123",
        source="web",
        data={"button": "signup_cta"},
        consent={"analytics": True},
        trace_id="trc_abc123"
    )
    res_event = client.post("/v1/events", json=evt_schema.model_dump(mode="json"))
    assert res_event.status_code == 200
    assert res_event.json()["status"] == "accepted"
