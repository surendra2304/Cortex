from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable
from .models import JobState
from .workflow import WorkflowStateMachine

@dataclass(frozen=True)
class AgentResult:
    state: JobState
    output: Any
    steps: int
    error: str | None = None

class CancellationToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()
    def cancel(self) -> None:
        self._event.set()
    def throw_if_cancelled(self) -> None:
        if self._event.is_set():
            raise asyncio.CancelledError()

class BoundedAgent:
    def __init__(self, max_steps: int = 12) -> None:
        if max_steps < 1:
            raise ValueError("max_steps must be positive")
        self.max_steps = max_steps

    async def run(self, step: Callable[[int], Awaitable[Any]], token: CancellationToken | None = None) -> AgentResult:
        token = token or CancellationToken()
        sm = WorkflowStateMachine()
        queued = await sm.transition(0, JobState.QUEUED)
        await sm.transition(queued.version, JobState.RUNNING)
        attempts = 0
        try:
            for number in range(1, self.max_steps + 1):
                token.throw_if_cancelled()
                attempts += 1
                result = await step(number)
                if result is not None:
                    current = await sm.snapshot()
                    verifying = await sm.transition(current.version, JobState.VERIFYING)
                    await sm.transition(verifying.version, JobState.SUCCEEDED)
                    return AgentResult(JobState.SUCCEEDED, result, attempts)
            current = await sm.snapshot()
            await sm.transition(current.version, JobState.FAILED)
            return AgentResult(JobState.FAILED, None, attempts, "step limit reached")
        except asyncio.CancelledError:
            current = await sm.snapshot()
            if current.state in {JobState.RUNNING, JobState.VERIFYING}:
                await sm.transition(current.version, JobState.CANCELLED)
            raise
        except Exception as exc:
            current = await sm.snapshot()
            if current.state in {JobState.RUNNING, JobState.VERIFYING}:
                await sm.transition(current.version, JobState.FAILED)
            return AgentResult(JobState.FAILED, None, attempts, f"{type(exc).__name__}: {exc}")
