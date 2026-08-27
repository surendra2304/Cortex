from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
import logging
import sys
import os
import contextvars
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

# Add local packages to sys.path
sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from nexus_core.models import AuditRecord
from nexus_event_schema import EventSchema
from nexus_agents import AgentRegistry, AgentInput, AgentOutput
from nexus_ai_universe_adapter import (
    AIUniverseClient, IntelligenceRequest, RequestClassifier, RequestClassification, AIMode
)
from nexus_tool_runtime import Tool, Execution, SideEffectLevel, ToolBus, ToolCapability
from nexus_integrations import (
    EmailToolExecutor, create_email_tool,
    CRMToolExecutor, create_crm_tool,
    SMSToolExecutor, create_sms_tool,
    VoiceToolExecutor, create_voice_tool,
    WebhookToolExecutor, create_webhook_tool,
    PaymentsToolExecutor, create_payments_tool,
    TicketingToolExecutor, create_ticketing_tool,
)
from nexus_policy_engine import PolicyEngine
from nexus_workflow_engine import WorkflowStateMachine, WorkflowContext, WorkflowState
from nexus_api.db_models import VisitorModel, ProfileModel, AuditRecordModel, EventModel

logger = logging.getLogger("nexus-orchestrator")
trace_id_ctx = contextvars.ContextVar("trace_id_ctx", default=None)


def build_default_tool_bus(redis_client: Optional[Any] = None) -> ToolBus:
    bus = ToolBus(redis_client=redis_client)
    
    bus.register_tool(create_email_tool(), EmailToolExecutor())
    bus.register_tool(create_crm_tool(), CRMToolExecutor())
    bus.register_tool(create_sms_tool(), SMSToolExecutor())
    bus.register_tool(create_voice_tool(), VoiceToolExecutor())
    bus.register_tool(create_webhook_tool(), WebhookToolExecutor())
    bus.register_tool(create_payments_tool(), PaymentsToolExecutor())
    bus.register_tool(create_ticketing_tool(), TicketingToolExecutor())

    banner_tool = Tool(
        name="banner_injection",
        capabilities=[ToolCapability.BANNER_INJECTION],
        side_effect_level=SideEffectLevel.HIGH_IMPACT
    )
    bus.register_tool(banner_tool, lambda p, ctx: {"injected": True, "variant": p.get("variant")})

    inspect_tool = Tool(
        name="session_inspect",
        capabilities=[ToolCapability.SESSION_INSPECT],
        side_effect_level=SideEffectLevel.READ
    )
    bus.register_tool(inspect_tool, lambda p, ctx: {"inspected": True, "depth": p.get("inspect_depth", "summary")})

    account_tool = Tool(
        name="account_update",
        capabilities=[ToolCapability.ACCOUNT_UPDATE],
        side_effect_level=SideEffectLevel.SENSITIVE
    )
    bus.register_tool(account_tool, lambda p, ctx: {"updated": True, "account_params": p})

    return bus


class Orchestrator:
    """10-Phase NEXUS Autonomous Cognitive Loop Orchestrator with Intelligent Context & Request Classification."""

    def __init__(
        self,
        agent_registry: Optional[AgentRegistry] = None,
        ai_client: Optional[AIUniverseClient] = None,
        policy_engine: Optional[PolicyEngine] = None,
        tool_bus: Optional[ToolBus] = None,
        classifier: Optional[RequestClassifier] = None
    ):
        self.agent_registry = agent_registry or AgentRegistry()
        self.ai_client = ai_client or AIUniverseClient()
        self.policy_engine = policy_engine or PolicyEngine(human_in_the_loop_enabled=True)
        self.tool_bus = tool_bus or build_default_tool_bus()
        self.classifier = classifier or RequestClassifier()
        self.audit_records: List[AuditRecord] = []

    async def run_cognitive_loop(
        self,
        event: EventSchema,
        db_session: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        loop_id = f"loop_{uuid.uuid4().hex[:8]}"
        trace_id = event.trace_id or f"trc_{uuid.uuid4().hex[:10]}"
        token = trace_id_ctx.set(trace_id)

        try:
            trace = []

            # 1. OBSERVE
            trace.append({
                "phase": "1.Observe",
                "event_id": event.event_id,
                "type": event.type,
                "occurred_at": event.occurred_at.isoformat(),
                "trace_id": trace_id
            })

            # 2. CONTEXTUALIZE (Deep session & historical actor queries)
            visitor_attributes = {}
            profile_traits = {}
            profile_email = None
            session_events: List[Dict[str, Any]] = []
            actor_history_events: List[Dict[str, Any]] = []

            if db_session:
                try:
                    # Query Visitor & Profile
                    stmt = select(VisitorModel).where(VisitorModel.id == event.actor.id)
                    res = await db_session.execute(stmt)
                    v_record = res.scalar_one_or_none()
                    if v_record:
                        visitor_attributes = dict(v_record.attributes or {})
                        if v_record.profile_id:
                            p_stmt = select(ProfileModel).where(ProfileModel.id == v_record.profile_id)
                            p_res = await db_session.execute(p_stmt)
                            p_record = p_res.scalar_one_or_none()
                            if p_record:
                                profile_traits = dict(p_record.traits or {})
                                profile_email = p_record.primary_email

                    # Query last 20 events in this session
                    if event.session_id:
                        s_stmt = select(EventModel).where(
                            EventModel.session_id == event.session_id
                        ).order_by(desc(EventModel.occurred_at)).limit(20)
                        s_res = await db_session.execute(s_stmt)
                        session_events = [
                            {"type": r.type, "data": r.data, "occurred_at": r.occurred_at.isoformat()}
                            for r in s_res.scalars().all()
                        ]

                    # Query last 50 events for this actor (cross-session behavior)
                    a_stmt = select(EventModel).where(
                        EventModel.actor_id == event.actor.id
                    ).order_by(desc(EventModel.occurred_at)).limit(50)
                    a_res = await db_session.execute(a_stmt)
                    actor_history_events = [
                        {"type": r.type, "data": r.data, "occurred_at": r.occurred_at.isoformat()}
                        for r in a_res.scalars().all()
                    ]
                except Exception as exc:
                    logger.warning(f"DB contextualize lookup warning: {exc}")

            # Include current event in session analysis
            all_recent_events = [event.model_dump(mode="json")] + session_events

            # Compute rich session metrics for agents
            pages_viewed = len([e for e in all_recent_events if "page_view" in e.get("type", "").lower()])
            pricing_views = sum(1 for e in all_recent_events if "pricing" in e.get("type", "").lower())
            demo_views = sum(1 for e in all_recent_events if "demo" in e.get("type", "").lower())
            enterprise_views = sum(1 for e in all_recent_events if any(k in e.get("type", "").lower() for k in ["enterprise", "security"]))
            error_count = sum(1 for e in all_recent_events if "error" in e.get("type", "").lower())
            exit_intent = any("exit" in e.get("type", "").lower() for e in all_recent_events)

            session_summary = {
                "pages_viewed": pages_viewed,
                "pricing_view_count": pricing_views,
                "demo_view_count": demo_views,
                "enterprise_view_count": enterprise_views,
                "error_count": error_count,
                "exit_intent_detected": exit_intent,
                "total_session_events": len(all_recent_events),
                "actor_cross_session_event_count": len(actor_history_events)
            }

            context = {
                "tenant_id": event.tenant_id,
                "site_id": event.site_id,
                "actor": event.actor.model_dump(),
                "session_id": event.session_id,
                "event_data": event.data,
                "visitor_attributes": visitor_attributes,
                "profile_traits": profile_traits,
                "profile_email": profile_email,
                "session_summary": session_summary,
                "recent_session_events_count": len(session_events)
            }

            trust_labels = {
                "tenant_id": "system_fact",
                "site_id": "system_fact",
                "actor": "verified_telemetry",
                "session_summary": "verified_telemetry",
                "event_data": "untrusted_user_input" if "input" in event.type else "verified_telemetry",
                "visitor_attributes": "verified_telemetry",
                "profile_traits": "inferred_profile"
            }
            provenance = {
                "origin_site": event.site_id,
                "tenant_id": event.tenant_id,
                "trace_id": trace_id,
                "occurred_at": event.occurred_at.isoformat()
            }
            trace.append({
                "phase": "2.Contextualize",
                "session_summary": session_summary,
                "context_keys": list(context.keys())
            })

            # 3. UNDERSTAND
            agent = self.agent_registry.route_for_event(event.type)
            trace.append({"phase": "3.Understand", "selected_agent": agent.agent_id, "domain": agent.domain})

            # 4. PLAN (Deterministic First -> Intelligence Classification -> Conditional AI Universe)
            agent_input = AgentInput(
                goal=f"Determine optimal operational intervention for {event.type}",
                context=context,
                events=all_recent_events,
                allowed_capabilities=agent.capabilities
            )
            agent_output: AgentOutput = await agent.process(agent_input)

            # Classify event for intelligence routing
            classification, ai_mode = self.classifier.classify(event.type, context, agent_output)
            should_call_ai = self.classifier.should_call_ai(classification)

            ai_decision = "DETERMINISTIC_PASSTHROUGH"
            ai_confidence = agent_output.confidence
            ai_unresolved_disagreements: List[str] = []
            ai_provenance: Dict[str, Any] = {"mode": "deterministic"}

            if should_call_ai:
                ai_req = IntelligenceRequest(
                    request_id=f"req_{loop_id}",
                    task_type="intervention_planning",
                    goal=f"Refine strategy for {event.type} in {ai_mode.value if ai_mode else 'fast'} mode",
                    context=context,
                    evidence=[
                        {"key": "agent_decision", "value": agent_output.decision},
                        {"key": "evidence_refs", "value": agent_output.evidence_refs},
                        {"key": "session_summary", "value": session_summary}
                    ],
                    trust_labels=trust_labels,
                    provenance=provenance
                )
                ai_res = await self.ai_client.evaluate(ai_req)
                ai_decision = ai_res.decision
                ai_confidence = ai_res.confidence
                ai_unresolved_disagreements = ai_res.unresolved_disagreements
                ai_provenance = {
                    "source": ai_res.provenance.get("source", "ai_universe"),
                    "mode": ai_mode.value if ai_mode else "fast",
                    "fallback_applied": ai_res.fallback_applied
                }

            trace.append({
                "phase": "4.Plan",
                "decision": agent_output.decision,
                "confidence": agent_output.confidence,
                "proposed_actions_count": len(agent_output.proposed_actions),
                "ai_used": should_call_ai,
                "classification": classification.value,
                "ai_mode": ai_mode.value if ai_mode else None,
                "ai_decision": ai_decision
            })

            # 5. AUTHORIZE
            authorized_actions = []
            if agent_output.proposed_actions:
                for prop in agent_output.proposed_actions:
                    tool = self.tool_bus.get_tool(prop.action_type) or Tool(name=prop.action_type, side_effect_level=SideEffectLevel.READ)
                    execution = Execution(
                        request_id=f"exec_{uuid.uuid4().hex[:8]}",
                        tool_name=tool.name,
                        actor={"type": "agent", "id": agent.agent_id},
                        reason=prop.rationale,
                        params=prop.params,
                        idempotency_key=f"idemp_{loop_id}_{prop.action_type}"
                    )
                    decision = self.policy_engine.evaluate(execution, tool)
                    execution.policy_decision = decision
                    if decision.approved:
                        authorized_actions.append((execution, tool))
                    trace.append({
                        "phase": "5.Authorize",
                        "tool": tool.name,
                        "approved": decision.approved,
                        "requires_human": decision.requires_human_approval,
                        "reason": decision.reason
                    })
            else:
                trace.append({"phase": "5.Authorize", "status": "no_actions_to_authorize", "count": 0})

            # 6. EXECUTE
            execution_results = []
            if authorized_actions:
                for exec_item, tool in authorized_actions:
                    res = await self.tool_bus.execute(tool.name, exec_item.params, exec_item)
                    execution_results.append(res)
                    trace.append({"phase": "6.Execute", "tool": tool.name, "result": res})
            else:
                trace.append({"phase": "6.Execute", "status": "no_auto_approved_actions_executed", "count": 0})

            # 7. VERIFY
            verification_passed = all(
                exec_item.verification.get("status") == "verified"
                for exec_item, _ in authorized_actions
                if exec_item.verification
            ) if authorized_actions else True
            trace.append({"phase": "7.Verify", "status": "verified" if verification_passed else "failed"})

            # 8. MEASURE
            measured_impact = agent_output.expected_outcomes
            trace.append({"phase": "8.Measure", "outcomes": measured_impact})

            # 9. LEARN
            audit = AuditRecord(
                id=f"aud_{loop_id}",
                tenant_id=event.tenant_id,
                actor_id=agent.agent_id,
                action=f"cognitive_loop:{agent_output.decision}",
                target_resource=f"site/{event.site_id}",
                changes={
                    "agent_output": agent_output.model_dump(mode="json"),
                    "executions": execution_results,
                    "verification": "passed" if verification_passed else "failed",
                    "ai_used": should_call_ai,
                    "classification": classification.value,
                    "ai_decision": ai_decision,
                    "ai_confidence": ai_confidence,
                    "ai_dissent": ai_unresolved_disagreements,
                    "ai_provenance": ai_provenance,
                    "trust_labels": trust_labels,
                    "session_summary": session_summary,
                    "measured_impact": measured_impact,
                    "trace_id": trace_id
                }
            )
            self.audit_records.append(audit)

            if db_session:
                try:
                    db_audit = AuditRecordModel(
                        id=audit.id,
                        tenant_id=audit.tenant_id,
                        actor_id=audit.actor_id,
                        action=audit.action,
                        target_resource=audit.target_resource,
                        changes=audit.changes,
                        verification_status="verified" if verification_passed else "failed",
                        trace_id=trace_id,
                        timestamp=datetime.utcnow()
                    )
                    db_session.add(db_audit)
                    await db_session.commit()
                except Exception as exc:
                    logger.warning(f"Error persisting AuditRecordModel to DB: {exc}")
                    await db_session.rollback()

            trace.append({"phase": "9.Learn", "audit_id": audit.id, "strategy_logged": True})

            # 10. CONTINUE
            trace.append({"phase": "10.Continue", "status": "cycle_complete"})

            return {
                "loop_id": loop_id,
                "status": "success",
                "trace_id": trace_id,
                "agent_id": agent.agent_id,
                "decision": agent_output.decision,
                "ai_used": should_call_ai,
                "classification": classification.value,
                "executed_actions": len(execution_results),
                "trace": trace
            }

        finally:
            trace_id_ctx.reset(token)
