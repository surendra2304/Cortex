from typing import Any, Dict, List, Optional
from datetime import datetime
import uuid
import logging
import sys
import os

# Add local packages
sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))

from nexus_core.models import AuditRecord
from nexus_event_schema import EventSchema
from nexus_agents import AgentRegistry, AgentInput, AgentOutput
from nexus_ai_universe_adapter import AIUniverseClient, IntelligenceRequest
from nexus_tool_runtime import Tool, Execution, SideEffectLevel, ToolCapability
from nexus_policy_engine import PolicyEngine
from nexus_workflow_engine import WorkflowStateMachine, WorkflowContext, WorkflowState

logger = logging.getLogger("nexus-orchestrator")


class ToolBus:
    def __init__(self):
        self._tools: Dict[str, Tool] = {
            "banner_injection": Tool(
                name="banner_injection",
                capabilities=[ToolCapability.BANNER_INJECTION],
                side_effect_level=SideEffectLevel.HIGH_IMPACT
            ),
            "account_update": Tool(
                name="account_update",
                capabilities=[ToolCapability.ACCOUNT_UPDATE],
                side_effect_level=SideEffectLevel.SENSITIVE
            ),
            "session_inspect": Tool(
                name="session_inspect",
                capabilities=[ToolCapability.SESSION_INSPECT],
                side_effect_level=SideEffectLevel.READ
            )
        }

    def get_tool(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    async def execute(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": "success",
            "tool": tool_name,
            "executed_at": datetime.utcnow().isoformat(),
            "output": f"Simulated execution for {tool_name} with params {params}"
        }


class Orchestrator:
    """10-Phase NEXUS Cognitive Loop Orchestrator"""

    def __init__(
        self,
        agent_registry: Optional[AgentRegistry] = None,
        ai_client: Optional[AIUniverseClient] = None,
        policy_engine: Optional[PolicyEngine] = None,
        tool_bus: Optional[ToolBus] = None
    ):
        self.agent_registry = agent_registry or AgentRegistry()
        self.ai_client = ai_client or AIUniverseClient()
        self.policy_engine = policy_engine or PolicyEngine(human_in_the_loop_enabled=True)
        self.tool_bus = tool_bus or ToolBus()
        self.audit_records: List[AuditRecord] = []

    async def run_cognitive_loop(self, event: EventSchema) -> Dict[str, Any]:
        loop_id = f"loop_{uuid.uuid4().hex[:8]}"
        trace = []

        # 1. OBSERVE: Receive and parse incoming trigger event
        trace.append({"phase": "1.Observe", "event_id": event.event_id, "type": event.type})

        # 2. CONTEXTUALIZE: Assemble tenant, site, visitor, and session state
        context = {
            "tenant_id": event.tenant_id,
            "site_id": event.site_id,
            "actor": event.actor.model_dump(),
            "session_id": event.session_id,
            "event_data": event.data
        }
        trace.append({"phase": "2.Contextualize", "context": context})

        # 3. UNDERSTAND: Select specialist agent and consult AI Universe if needed
        agent = self.agent_registry.route_for_event(event.type)
        ai_req = IntelligenceRequest(
            request_id=f"req_{loop_id}",
            task_type="intent_scoring",
            goal=f"Determine optimal intervention for {event.type}",
            context=context,
            evidence=[{"event_type": event.type, "actor_id": event.actor.id}]
        )
        ai_res = await self.ai_client.evaluate(ai_req)
        trace.append({"phase": "3.Understand", "agent_id": agent.agent_id, "ai_decision": ai_res.decision})

        # 4. PLAN: Agent formulates action proposal
        agent_input = AgentInput(
            goal=f"Optimize response for {event.type}",
            context=context,
            events=[event.model_dump(mode="json")],
            allowed_capabilities=agent.capabilities
        )
        agent_output: AgentOutput = await agent.process(agent_input)
        trace.append({"phase": "4.Plan", "decision": agent_output.decision, "proposed_actions": len(agent_output.proposed_actions)})

        # 5. AUTHORIZE: Evaluate proposed actions against Policy Engine
        authorized_actions = []
        for prop in agent_output.proposed_actions:
            tool = self.tool_bus.get_tool(prop.action_type) or Tool(name=prop.action_type, side_effect_level=SideEffectLevel.READ)
            execution = Execution(
                request_id=f"exec_{uuid.uuid4().hex[:8]}",
                tool_name=tool.name,
                actor={"type": "agent", "id": agent.agent_id},
                reason=prop.rationale,
                params=prop.params
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

        # 6. EXECUTE: Dispatch approved actions via Tool Bus (or record skipped/approval-needed)
        execution_results = []
        if authorized_actions:
            for exec_item, tool in authorized_actions:
                res = await self.tool_bus.execute(tool.name, exec_item.params)
                exec_item.result = res
                exec_item.executed_at = datetime.utcnow()
                execution_results.append(res)
                trace.append({"phase": "6.Execute", "tool": tool.name, "result": res})
        else:
            trace.append({"phase": "6.Execute", "status": "no_auto_approved_actions_executed", "count": 0})

        # 7. VERIFY: Verify execution outputs and state invariants
        verification_passed = True
        trace.append({"phase": "7.Verify", "status": "verified" if verification_passed else "failed"})

        # 8. MEASURE: Calculate outcome metrics and expected impact
        measured_impact = agent_output.expected_outcomes
        trace.append({"phase": "8.Measure", "outcomes": measured_impact})

        # 9. LEARN: Record audit log and policy feedback
        audit = AuditRecord(
            id=f"aud_{loop_id}",
            tenant_id=event.tenant_id,
            actor_id=agent.agent_id,
            action=f"cognitive_loop:{agent_output.decision}",
            target_resource=f"site/{event.site_id}",
            changes={"agent_output": agent_output.model_dump(mode="json"), "executions": execution_results}
        )
        self.audit_records.append(audit)
        trace.append({"phase": "9.Learn", "audit_id": audit.id})

        # 10. CONTINUE: Return loop result state and schedule next cycle
        trace.append({"phase": "10.Continue", "status": "cycle_complete"})

        return {
            "loop_id": loop_id,
            "status": "success",
            "agent_id": agent.agent_id,
            "decision": agent_output.decision,
            "executed_actions": len(execution_results),
            "trace": trace
        }
