import contextvars
import logging
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_upgrade.audit import redact
from cortex_upgrade.context_firewall import Context as FirewallContext
from cortex_upgrade.context_firewall import ContextFirewall, Trust

# Add local packages to sys.path
sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))
sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("packages/analytics/src"))
sys.path.insert(0, os.path.abspath("packages/intelligence/src"))
sys.path.insert(0, os.path.abspath("packages/memory/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from cortex_agents import AgentInput, AgentOutput, AgentRegistry
from cortex_ai_universe_adapter import (
    AIUniverseClient,
    IntelligenceRequest,
    RequestClassifier,
)
from cortex_analytics import ScoringEngine
from cortex_api.db_models import (
    ApprovalQueueModel,
    AuditRecordModel,
    EventModel,
    LeadModel,
    ProfileModel,
    VisitorModel,
)
from cortex_event_schema import EventSchema
from cortex_identity import IdentityResolver
from cortex_integrations import (
    CRMToolExecutor,
    EmailToolExecutor,
    PaymentsToolExecutor,
    SMSToolExecutor,
    TicketingToolExecutor,
    VoiceToolExecutor,
    WebhookToolExecutor,
    create_crm_tool,
    create_email_tool,
    create_payments_tool,
    create_sms_tool,
    create_ticketing_tool,
    create_voice_tool,
    create_webhook_tool,
)
from cortex_intelligence import ContextBuilder
from cortex_memory import MemoryScope, MemoryStore
from cortex_policy_engine import PolicyEngine
from cortex_tool_runtime import Execution, SideEffectLevel, Tool, ToolBus, ToolCapability

from cortex_core.models import AuditRecord

logger = logging.getLogger("cortex-orchestrator")
trace_id_ctx = contextvars.ContextVar("trace_id_ctx", default=None)


def build_default_tool_bus(redis_client: Any | None = None) -> ToolBus:
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
        side_effect_level=SideEffectLevel.HIGH_IMPACT,
    )
    bus.register_tool(banner_tool, lambda p, ctx: {"injected": True, "variant": p.get("variant")})

    inspect_tool = Tool(
        name="session_inspect", capabilities=[ToolCapability.SESSION_INSPECT], side_effect_level=SideEffectLevel.READ
    )
    bus.register_tool(inspect_tool, lambda p, ctx: {"inspected": True, "depth": p.get("inspect_depth", "summary")})

    account_tool = Tool(
        name="account_update", capabilities=[ToolCapability.ACCOUNT_UPDATE], side_effect_level=SideEffectLevel.SENSITIVE
    )
    bus.register_tool(account_tool, lambda p, ctx: {"updated": True, "account_params": p})

    return bus


class Orchestrator:
    """10-Phase CORTEX Autonomous Cognitive Loop Orchestrator with ContextBuilder, ScoringEngine, and MemoryStore."""

    def __init__(
        self,
        agent_registry: AgentRegistry | None = None,
        ai_client: AIUniverseClient | None = None,
        policy_engine: PolicyEngine | None = None,
        tool_bus: ToolBus | None = None,
        classifier: RequestClassifier | None = None,
        identity_resolver: IdentityResolver | None = None,
        scoring_engine: ScoringEngine | None = None,
        context_builder: ContextBuilder | None = None,
        memory_store: MemoryStore | None = None,
    ):
        self.agent_registry = agent_registry or AgentRegistry()
        self.ai_client = ai_client or AIUniverseClient()
        self.policy_engine = policy_engine or PolicyEngine(human_in_the_loop_enabled=True)
        self.tool_bus = tool_bus or build_default_tool_bus()
        self.classifier = classifier or RequestClassifier()
        self.identity_resolver = identity_resolver or IdentityResolver()
        self.scoring_engine = scoring_engine or ScoringEngine()
        self.context_builder = context_builder or ContextBuilder()
        self.memory_store = memory_store or MemoryStore()
        self.context_firewall = ContextFirewall()
        self.audit_records: list[AuditRecord] = []

    async def _collaborate_from_output(
        self,
        agent: Any,
        agent_output: AgentOutput,
        event: EventSchema,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Let peers answer the handoffs the lead agent requested; bounded and non-fatal.

        Returns ``None`` when collaboration is disabled by the runtime knob or the peer set
        cannot be resolved. A collaboration failure must never take down the cognitive loop —
        the lead agent's own decision still stands.
        """
        from cortex_agents import CollaborationSession

        max_rounds = 3
        try:
            from cortex_upgrade.runtime_knobs import global_runtime_knobs

            max_rounds = int(global_runtime_knobs.get("max_collaboration_rounds", 3))
        except Exception:  # pragma: no cover - knobs are optional wiring in bare installs
            logger.debug("runtime knobs unavailable; using default collaboration budget")
        if max_rounds < 1:
            return None

        try:
            session = CollaborationSession(self.agent_registry, max_rounds=max_rounds)
            result = await session.run(
                root_agent_id=agent.agent_id,
                goal=f"Determine optimal operational intervention for {event.type}",
                context=context,
                events=[],
                root_output=agent_output,
            )
        except Exception as exc:  # noqa: BLE001 - collaboration is additive, never fatal
            logger.warning("collaboration for %s failed: %s", agent.agent_id, exc)
            return None

        return {
            "session_id": result.session_id,
            "participants": result.participants,
            "rounds_used": result.rounds_used,
            "handoffs_executed": result.handoffs_executed,
            "handoffs_refused": result.handoffs_refused,
            "challenges": result.challenges,
            "challenges_refused": result.challenges_refused,
            "verifications": [v.as_dict() for v in result.verifications],
            "verification_refusals": result.verification_refusals,
            "consensus": result.consensus.as_dict(),
            "peer_findings": [
                {
                    "agent_id": output.get("agent_id", agent_id) if isinstance(output, dict) else output.agent_id,
                    "decision": output.get("decision") if isinstance(output, dict) else output.decision,
                    "confidence": output.get("confidence") if isinstance(output, dict) else output.confidence,
                    "reasoning": (
                        output.get("reasoning_summary") if isinstance(output, dict) else output.reasoning_summary
                    ),
                }
                for agent_id, output in result.outputs.items()
            ],
        }

    async def run_cognitive_loop(self, event: EventSchema, db_session: AsyncSession | None = None) -> dict[str, Any]:
        loop_id = f"loop_{uuid.uuid4().hex[:8]}"
        trace_id = event.trace_id or f"trc_{uuid.uuid4().hex[:10]}"
        token = trace_id_ctx.set(trace_id)

        try:
            trace = []

            # 1. OBSERVE
            trace.append(
                {
                    "phase": "1.Observe",
                    "event_id": event.event_id,
                    "type": event.type,
                    "occurred_at": event.occurred_at.isoformat(),
                    "trace_id": trace_id,
                }
            )

            # 2. CONTEXTUALIZE (ContextBuilder + Identity + Historical Memory)
            visitor_attributes = {}
            profile_traits = {}
            profile_email = None
            lead_info: dict[str, Any] = {}
            session_events: list[dict[str, Any]] = []
            actor_history_events: list[dict[str, Any]] = []
            relevant_memories: list[dict[str, Any]] = []

            if db_session:
                try:
                    # Query Visitor & Profile — tenant-scoped, and resolving the
                    # identity graph when the actor is an identified user: their
                    # events carry the user_id/email as actor id, which never equals
                    # the anonymous visitor id, so without link resolution identified
                    # visitors were invisible to every agent.
                    stmt = select(VisitorModel).where(
                        VisitorModel.id == event.actor.id, VisitorModel.tenant_id == event.tenant_id
                    )
                    res = await db_session.execute(stmt)
                    v_record = res.scalar_one_or_none()
                    if v_record:
                        visitor_attributes = dict(v_record.attributes or {})

                    profile_id: str | None = v_record.profile_id if v_record else None
                    if not profile_id:
                        resolved = await self.identity_resolver.resolve_actor_profile(
                            db=db_session, actor_id=event.actor.id, tenant_id=event.tenant_id
                        )
                        profile_id = resolved.get("profile_id")
                        if resolved.get("visitor_attributes"):
                            visitor_attributes = resolved["visitor_attributes"]
                        if resolved.get("profile_traits"):
                            profile_traits = resolved["profile_traits"]
                        if resolved.get("primary_email"):
                            profile_email = resolved["primary_email"]
                        if resolved.get("lead"):
                            lead_info = resolved["lead"]

                    if profile_id:
                        p_stmt = select(ProfileModel).where(
                            ProfileModel.id == profile_id, ProfileModel.tenant_id == event.tenant_id
                        )
                        p_res = await db_session.execute(p_stmt)
                        p_record = p_res.scalar_one_or_none()
                        if p_record:
                            profile_traits = dict(p_record.traits or {})
                            profile_email = p_record.primary_email

                        # Query Lead if linked
                        l_stmt = select(LeadModel).where(
                            LeadModel.tenant_id == event.tenant_id, LeadModel.profile_id == profile_id
                        )
                        l_res = await db_session.execute(l_stmt)
                        l_record = l_res.scalar_one_or_none()
                        if l_record:
                            lead_info = {
                                "lead_id": l_record.id,
                                "score": l_record.score,
                                "status": l_record.status,
                                "lifecycle_stage": "customer" if l_record.status == "customer" else "lead",
                            }

                    # Query last 20 events in session (tenant-scoped)
                    if event.session_id:
                        s_stmt = (
                            select(EventModel)
                            .where(
                                EventModel.tenant_id == event.tenant_id,
                                EventModel.session_id == event.session_id,
                            )
                            .order_by(desc(EventModel.occurred_at))
                            .limit(20)
                        )
                        s_res = await db_session.execute(s_stmt)
                        session_events = [
                            {
                                "event_id": r.id,  # EventModel PK is the event id (db_models.EventModel.id)
                                "type": r.type,
                                "data": r.data,
                                "occurred_at": r.occurred_at.isoformat(),
                            }
                            for r in s_res.scalars().all()
                        ]

                    # Query last 50 events for actor (tenant-scoped)
                    a_stmt = (
                        select(EventModel)
                        .where(
                            EventModel.tenant_id == event.tenant_id,
                            EventModel.actor_id == event.actor.id,
                        )
                        .order_by(desc(EventModel.occurred_at))
                        .limit(50)
                    )
                    a_res = await db_session.execute(a_stmt)
                    actor_history_events = [
                        {
                            "event_id": r.id,  # EventModel PK is the event id (db_models.EventModel.id)
                            "type": r.type,
                            "data": r.data,
                            "occurred_at": r.occurred_at.isoformat(),
                        }
                        for r in a_res.scalars().all()
                    ]

                    # Query strategy/visitor memory
                    mem_entries = await self.memory_store.get(
                        db=db_session,
                        scope=MemoryScope.VISITOR.value,
                        scope_id=event.actor.id,
                        tenant_id=event.tenant_id,
                    )
                    relevant_memories = [m.model_dump(mode="json") for m in mem_entries]

                except Exception as exc:
                    logger.warning(f"DB contextualize lookup warning: {exc}")

            # Assemble typed ContextPackage using ContextBuilder
            context_package = self.context_builder.build_context(
                event=event.model_dump(mode="json"),
                session_events=session_events,
                actor_events=actor_history_events,
                visitor_attributes=visitor_attributes,
                profile_traits=profile_traits,
                lead_info=lead_info,
            )

            # Agents see the actor's full recent history (current event + session
            # window + cross-session history, deduplicated) — a single event must
            # not be the whole picture for intent and recency scoring.
            all_recent_events = [event.model_dump(mode="json"), *session_events, *actor_history_events]
            seen_event_ids: set[str] = set()
            deduped_recent: list[dict[str, Any]] = []
            for e in all_recent_events:
                event_id = e.get("event_id")
                if event_id:
                    if event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event_id)
                deduped_recent.append(e)
            all_recent_events = deduped_recent

            context = {
                "tenant_id": event.tenant_id,
                "site_id": event.site_id,
                "actor": event.actor.model_dump(),
                "session_id": event.session_id,
                "event_data": event.data,
                "visitor_attributes": visitor_attributes,
                "profile_traits": profile_traits,
                "profile_email": profile_email,
                "session_summary": context_package.session_context,
                "intent_level": context_package.intent_level,
                "intent_score": context_package.intent_score,
                "anomaly_flags": context_package.anomaly_flags,
                "memories": relevant_memories,
            }

            trust_labels = {
                "tenant_id": "system_fact",
                "site_id": "system_fact",
                "actor": "verified_telemetry",
                "session_summary": "verified_telemetry",
                "event_data": "untrusted_user_input" if "input" in event.type else "verified_telemetry",
                "visitor_attributes": "verified_telemetry",
                "profile_traits": "inferred_profile",
            }
            provenance = {
                "origin_site": event.site_id,
                "tenant_id": event.tenant_id,
                "trace_id": trace_id,
                "occurred_at": event.occurred_at.isoformat(),
            }
            trace.append(
                {
                    "phase": "2.Contextualize",
                    "intent_level": context_package.intent_level,
                    "intent_score": context_package.intent_score,
                    "anomaly_flags": context_package.anomaly_flags,
                    "session_summary": context_package.session_context,
                }
            )

            # 3. UNDERSTAND
            agent = self.agent_registry.route_for_event(event.type)
            trace.append(
                {
                    "phase": "3.Understand",
                    "selected_agent": agent.agent_id,
                    "domain": agent.domain,
                    "intent_level": context_package.intent_level,
                }
            )

            # 4. PLAN (Deterministic First -> Intelligence Classification -> Conditional AI Universe)
            agent_input = AgentInput(
                goal=f"Determine optimal operational intervention for {event.type}",
                context=context,
                events=all_recent_events,
                allowed_capabilities=agent.capabilities,
            )
            agent_output: AgentOutput = await agent.process(agent_input)

            # 4a. COLLABORATE — peers help the lead agent when it asks for them.
            # Only the handoffs the lead requested run; the session cannot widen its own
            # authority, and execution still happens under the lead agent's capabilities below.
            collaboration_summary: dict[str, Any] | None = None
            if getattr(agent_output, "handoffs", None):
                collaboration_summary = await self._collaborate_from_output(agent, agent_output, event, context)
                if collaboration_summary:
                    peer_evidence = [
                        f"peer:{finding['agent_id']}:{finding['decision']}"
                        for finding in collaboration_summary.get("peer_findings", [])
                        if finding.get("agent_id") != agent.agent_id
                    ]
                    if peer_evidence:
                        agent_output.evidence_refs = list(dict.fromkeys([*agent_output.evidence_refs, *peer_evidence]))
                    trace.append(
                        {
                            "phase": "4a.Collaborate",
                            "participants": collaboration_summary["participants"],
                            "consensus": collaboration_summary["consensus"]["decision"],
                            "agreement": collaboration_summary["consensus"]["agreement"],
                            "dissent": collaboration_summary["consensus"]["dissenting"],
                            "peer_evidence": peer_evidence,
                        }
                    )

            # Classify event for intelligence routing
            classification, ai_mode = self.classifier.classify(event.type, context, agent_output)
            should_call_ai = self.classifier.should_call_ai(classification)

            ai_decision = "DETERMINISTIC_PASSTHROUGH"
            ai_confidence = agent_output.confidence
            ai_unresolved_disagreements: list[str] = []
            ai_provenance: dict[str, Any] = {"mode": "deterministic"}

            if should_call_ai:
                # Context firewall sanitization for untrusted/external context
                firewall_inputs = []
                for k, v in context.items():
                    if isinstance(v, str):
                        firewall_inputs.append(FirewallContext(text=v, trust=Trust.EXTERNAL, source=f"context.{k}"))
                sanitized_items, fw_warnings = self.context_firewall.sanitize(firewall_inputs)
                sanitized_context = dict(context)
                for s_item in sanitized_items:
                    sk = s_item.source.replace("context.", "")
                    sanitized_context[sk] = s_item.text
                if fw_warnings:
                    trace.append({"phase": "4.Plan.Firewall", "warnings": fw_warnings})

                ai_req = IntelligenceRequest(
                    request_id=f"req_{loop_id}",
                    task_type="intervention_planning",
                    goal=f"Refine strategy for {event.type} in {ai_mode.value if ai_mode else 'fast'} mode",
                    context=sanitized_context,
                    evidence=[
                        {"key": "agent_decision", "value": agent_output.decision},
                        {"key": "evidence_refs", "value": agent_output.evidence_refs},
                        {"key": "intent_score", "value": context_package.intent_score},
                        {"key": "anomaly_flags", "value": context_package.anomaly_flags},
                    ],
                    trust_labels=trust_labels,
                    provenance=provenance,
                )
                ai_res = await self.ai_client.evaluate(ai_req)
                ai_decision = ai_res.decision
                ai_confidence = ai_res.confidence
                ai_unresolved_disagreements = ai_res.unresolved_disagreements
                ai_provenance = {
                    "source": ai_res.provenance.get("source", "ai_universe"),
                    "mode": ai_mode.value if ai_mode else "fast",
                    "fallback_applied": ai_res.fallback_applied,
                }

            trace.append(
                {
                    "phase": "4.Plan",
                    "decision": agent_output.decision,
                    "confidence": agent_output.confidence,
                    "proposed_actions_count": len(agent_output.proposed_actions),
                    "ai_used": should_call_ai,
                    "classification": classification.value,
                    "ai_mode": ai_mode.value if ai_mode else None,
                    "ai_decision": ai_decision,
                }
            )

            # 5. AUTHORIZE
            authorized_actions = []
            pending_approvals: list[dict[str, Any]] = []
            if agent_output.proposed_actions:
                for prop in agent_output.proposed_actions:
                    tool = self.tool_bus.get_tool(prop.action_type) or Tool(
                        name=prop.action_type, side_effect_level=SideEffectLevel.READ
                    )
                    execution = Execution(
                        request_id=f"exec_{uuid.uuid4().hex[:8]}",
                        tool_name=tool.name,
                        actor={"type": "agent", "id": agent.agent_id},
                        reason=prop.rationale,
                        params=prop.params,
                        idempotency_key=f"idemp_{loop_id}_{prop.action_type}",
                    )
                    decision = self.policy_engine.evaluate(execution, tool)
                    execution.policy_decision = decision
                    if decision.approved:
                        authorized_actions.append((execution, tool))
                    elif decision.requires_human_approval:
                        # Close the loop: a gated proposal becomes an approval request
                        # the operator can decide. Before this, a gated proposal
                        # vanished — no request, no notification, no execution path.
                        approval_id = f"appr_{loop_id}_{prop.action_type}"
                        if db_session is not None:
                            try:
                                existing = await db_session.execute(
                                    select(ApprovalQueueModel).where(ApprovalQueueModel.id == approval_id)
                                )
                                if existing.scalar_one_or_none() is None:
                                    db_session.add(
                                        ApprovalQueueModel(
                                            id=approval_id,
                                            tenant_id=event.tenant_id,
                                            action_type=tool.name,
                                            target=prop.target,
                                            params=prop.params,
                                            rationale=prop.rationale,
                                            evidence_refs=agent_output.evidence_refs,
                                            risk_score=decision.risk_score,
                                            status="pending",
                                            expires_at=datetime.now(UTC) + timedelta(hours=24),
                                        )
                                    )
                                    await db_session.commit()
                                    pending_approvals.append(
                                        {
                                            "id": approval_id,
                                            "action_type": tool.name,
                                            "target": prop.target,
                                            "risk_score": decision.risk_score,
                                        }
                                    )
                            except Exception as exc:
                                logger.warning(f"Could not persist approval request: {exc}")
                                await db_session.rollback()
                    trace.append(
                        {
                            "phase": "5.Authorize",
                            "tool": tool.name,
                            "approved": decision.approved,
                            "requires_human": decision.requires_human_approval,
                            "reason": decision.reason,
                            "approval_id": pending_approvals[-1]["id"] if pending_approvals else None,
                        }
                    )
            else:
                trace.append({"phase": "5.Authorize", "status": "no_actions_to_authorize", "count": 0})

            # 6. EXECUTE
            execution_results = []
            if authorized_actions:
                from cortex_core.resilience import global_health_registry

                tools_circuit = global_health_registry.circuit("tools")
                for exec_item, tool in authorized_actions:
                    try:
                        res = await self.tool_bus.execute(tool.name, exec_item.params, exec_item)
                        await tools_circuit.record_success()
                    except Exception as exc:
                        await tools_circuit.record_failure(f"{tool.name}:{type(exc).__name__}")
                        raise
                    execution_results.append(res)
                    trace.append({"phase": "6.Execute", "tool": tool.name, "result": res})
            else:
                trace.append({"phase": "6.Execute", "status": "no_auto_approved_actions_executed", "count": 0})

            # 7. VERIFY
            verification_passed = (
                all(
                    exec_item.verification.get("status") == "verified"
                    for exec_item, _ in authorized_actions
                    if exec_item.verification
                )
                if authorized_actions
                else True
            )
            trace.append({"phase": "7.Verify", "status": "verified" if verification_passed else "failed"})

            # 8. MEASURE
            measured_impact = agent_output.expected_outcomes
            trace.append({"phase": "8.Measure", "outcomes": measured_impact})

            # 9. LEARN (Update Memory + Refresh Lead Score)
            audit = AuditRecord(
                id=f"aud_{loop_id}",
                tenant_id=event.tenant_id,
                actor_id=agent.agent_id,
                action=f"cognitive_loop:{agent_output.decision}",
                target_resource=f"site/{event.site_id}",
                changes={
                    "agent_output": agent_output.model_dump(mode="json"),
                    "executions": execution_results,
                    "pending_approvals": pending_approvals,
                    "verification": "passed" if verification_passed else "failed",
                    "ai_used": should_call_ai,
                    "classification": classification.value,
                    "ai_decision": ai_decision,
                    "ai_confidence": ai_confidence,
                    "ai_dissent": ai_unresolved_disagreements,
                    "ai_provenance": ai_provenance,
                    "trust_labels": trust_labels,
                    "session_summary": context_package.session_context,
                    "measured_impact": measured_impact,
                    "trace_id": trace_id,
                },
            )
            self.audit_records.append(audit)

            # Record outcome learning in Strategy Memory
            if authorized_actions:
                for _exec_item, tool in authorized_actions:
                    await self.memory_store.record_strategy_outcome(
                        db=db_session,
                        strategy_name=f"{agent.agent_id}:{tool.name}",
                        context_features={
                            "intent_score": context_package.intent_score,
                            "decision": agent_output.decision,
                        },
                        action_taken=tool.name,
                        outcome_lift_pct=measured_impact.get("conversion_lift_pct", 10.0),
                    )

            if db_session:
                try:
                    db_audit = AuditRecordModel(
                        id=audit.id,
                        tenant_id=audit.tenant_id,
                        actor_id=audit.actor_id,
                        action=audit.action,
                        target_resource=audit.target_resource,
                        changes=redact(audit.changes),
                        verification_status="verified" if verification_passed else "failed",
                        trace_id=trace_id,
                        timestamp=datetime.now(UTC),
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
                "trace": trace,
            }

        finally:
            trace_id_ctx.reset(token)
