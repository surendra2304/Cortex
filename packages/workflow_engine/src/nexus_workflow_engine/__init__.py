from typing import Any, Dict, List, Optional, Callable
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field
import asyncio
import logging

logger = logging.getLogger("nexus-workflow-engine")


class WorkflowState(str, Enum):
    TRIGGER = "trigger"
    CONTEXT_ASSEMBLY = "context_assembly"
    AGENT_RUN = "agent_run"
    POLICY_CHECK = "policy_check"
    TOOL_EXECUTION = "tool_execution"
    VERIFICATION = "verification"
    OUTCOME_MEASUREMENT = "outcome_measurement"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class WorkflowContext(BaseModel):
    workflow_id: str
    tenant_id: str
    site_id: str
    current_state: WorkflowState = WorkflowState.TRIGGER
    trigger_data: Dict[str, Any] = Field(default_factory=dict)
    assembled_context: Dict[str, Any] = Field(default_factory=dict)
    agent_output: Optional[Dict[str, Any]] = None
    policy_decision: Optional[Dict[str, Any]] = None
    execution_result: Optional[Dict[str, Any]] = None
    verification_result: Optional[Dict[str, Any]] = None
    outcomes: Dict[str, Any] = Field(default_factory=dict)
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowStateMachine:
    def __init__(self, context: WorkflowContext):
        self.context = context
        self.dead_letter_queue: List[WorkflowContext] = []

    def transition(self, next_state: WorkflowState, details: Optional[Dict[str, Any]] = None) -> None:
        self.context.history.append({
            "from_state": self.context.current_state,
            "to_state": next_state,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details or {}
        })
        self.context.current_state = next_state

    async def step_with_retry(self, step_func: Callable[[], Any], next_success_state: WorkflowState) -> bool:
        try:
            await step_func()
            self.transition(next_success_state)
            return True
        except Exception as exc:
            self.context.retry_count += 1
            logger.warning(f"Workflow {self.context.workflow_id} step failed: {exc}. Retry {self.context.retry_count}/{self.context.max_retries}")
            if self.context.retry_count >= self.context.max_retries:
                self.context.error = str(exc)
                self.transition(WorkflowState.DEAD_LETTER, {"error": str(exc)})
                self.dead_letter_queue.append(self.context)
                return False
            return False
