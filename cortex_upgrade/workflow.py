from __future__ import annotations
import asyncio
from dataclasses import dataclass
from .models import JobState

class WorkflowConflict(RuntimeError):
    pass

ALLOWED = {
    JobState.CREATED: {JobState.QUEUED, JobState.CANCELLED},
    JobState.QUEUED: {JobState.RUNNING, JobState.CANCELLED},
    JobState.RUNNING: {JobState.WAITING_APPROVAL, JobState.VERIFYING, JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED},
    JobState.WAITING_APPROVAL: {JobState.RUNNING, JobState.CANCELLED, JobState.FAILED},
    JobState.VERIFYING: {JobState.SUCCEEDED, JobState.FAILED, JobState.CANCELLED},
    JobState.SUCCEEDED: set(),
    JobState.FAILED: {JobState.QUEUED},
    JobState.CANCELLED: set(),
}

@dataclass(frozen=True)
class WorkflowSnapshot:
    state: JobState
    version: int

class WorkflowStateMachine:
    def __init__(self, state: JobState = JobState.CREATED) -> None:
        self._state = state
        self._version = 0
        self._lock = asyncio.Lock()

    async def transition(self, expected_version: int, target: JobState) -> WorkflowSnapshot:
        async with self._lock:
            if expected_version != self._version:
                raise WorkflowConflict("stale version")
            if target not in ALLOWED[self._state]:
                raise WorkflowConflict(f"invalid transition {self._state.value}->{target.value}")
            self._state = target
            self._version += 1
            return WorkflowSnapshot(self._state, self._version)

    async def snapshot(self) -> WorkflowSnapshot:
        async with self._lock:
            return WorkflowSnapshot(self._state, self._version)
