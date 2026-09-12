from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import copy
import logging

from cortex_core.web_property import PropertyRegistry, global_property_registry

logger = logging.getLogger("cortex-task-manager")


class TaskState(str, Enum):
    RECEIVED = "RECEIVED"
    OBSERVING = "OBSERVING"
    RECOMMENDING = "RECOMMENDING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    MEASURING = "MEASURING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"  # Rule 14 invariant
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass
class CortexTask:
    task_id: str
    property_id: str
    action: str
    state: TaskState = TaskState.RECEIVED
    progress: float = 0.0  # 0.0 to 1.0
    stage: str = "Task initialized"
    observations: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[Dict[str, Any]] = field(default_factory=list)
    approvals: List[Dict[str, Any]] = field(default_factory=list)
    executions: List[Dict[str, Any]] = field(default_factory=list)
    measurements: List[Dict[str, Any]] = field(default_factory=list)
    snapshots: Dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    classification: str = "REAL"  # REAL vs SIMULATED
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update_progress(self, state: TaskState, progress: float, stage: str) -> None:
        self.state = state
        self.progress = min(1.0, max(0.0, progress))
        self.stage = stage
        self.updated_at = datetime.now(timezone.utc)
        logger.info(f"Task '{self.task_id}' state -> {state.value} ({progress*100:.0f}%): {stage}")


class TaskManager:
    """
    Manages asynchronous task lifecycle, state transitions, progress reporting,
    cancellation, partial failure classification (Rule 14), and rollback.
    """
    def __init__(self, property_registry: Optional[PropertyRegistry] = None):
        self.registry = property_registry or global_property_registry
        self._tasks: Dict[str, CortexTask] = {}

    def create_task(
        self,
        task_id: str,
        property_id: str,
        action: str,
        dry_run: bool = False
    ) -> CortexTask:
        task = CortexTask(
            task_id=task_id,
            property_id=property_id,
            action=action,
            state=TaskState.RECEIVED,
            progress=0.1,
            stage="Task envelope received and validated",
            dry_run=dry_run,
            classification="SIMULATED" if dry_run else "REAL",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        self._tasks[task_id] = task
        logger.info(f"Created Cortex task '{task_id}' for property '{property_id}' with action '{action}'")
        return task

    def get_task(self, task_id: str) -> Optional[CortexTask]:
        return self._tasks.get(task_id)

    def cancel_task(self, task_id: str, reason: str = "Cancelled by supervisor") -> CortexTask:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        # Tasks already completed, failed, or rolled back cannot be cancelled
        if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.ROLLED_BACK):
            raise ValueError(f"Cannot cancel task '{task_id}' in state '{task.state.value}'.")

        task.state = TaskState.CANCELLED
        task.stage = f"Task cancelled: {reason}"
        task.error = reason
        task.updated_at = datetime.now(timezone.utc)
        logger.info(f"Cancelled task '{task_id}': {reason}")
        return task

    def rollback_task(self, task_id: str) -> CortexTask:
        """
        Rolls back property mutations executed under this task using saved snapshots.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        if not task.snapshots:
            raise ValueError(f"No snapshot available to rollback task '{task_id}'.")

        self.registry.restore_snapshot(task.property_id, task.snapshots)
        task.state = TaskState.ROLLED_BACK
        task.stage = "Property state restored from pre-execution snapshot"
        task.updated_at = datetime.now(timezone.utc)
        logger.info(f"Rolled back task '{task_id}' on property '{task.property_id}'")
        return task

    def finalize_task(self, task_id: str) -> CortexTask:
        """
        Evaluates task execution results and sets terminal state.
        RULE 14 INVARIANT: If any action was blocked, failed, or requires approval,
        the task is classified as PARTIALLY_COMPLETED (or BLOCKED), NEVER COMPLETED.
        """
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        if task.state in (TaskState.WAITING_APPROVAL, TaskState.CANCELLED, TaskState.ROLLED_BACK):
            task.updated_at = datetime.now(timezone.utc)
            return task

        has_blocked_or_pending = any(
            r.get("status") in ("PENDING_APPROVAL", "BLOCKED") or r.get("requires_approval")
            for r in task.recommendations
        )
        has_failed_execution = any(
            e.get("status") in ("FAILED", "BLOCKED")
            for e in task.executions
        )

        if task.state == TaskState.BLOCKED or (has_blocked_or_pending and not task.executions):
            task.state = TaskState.BLOCKED
            task.progress = 1.0
            task.stage = "Task blocked by security, policy, or approval gate"
        elif has_blocked_or_pending or has_failed_execution:
            # Rule 14 invariant: partial failure is PARTIALLY_COMPLETED, never COMPLETED
            task.state = TaskState.PARTIALLY_COMPLETED
            task.progress = 1.0
            task.stage = "Task partially completed: some actions were blocked or require authorization"
        else:
            task.state = TaskState.COMPLETED
            task.progress = 1.0
            task.stage = "Task fully executed and measured"

        task.updated_at = datetime.now(timezone.utc)
        return task


# Global default task manager instance
global_task_manager = TaskManager()
