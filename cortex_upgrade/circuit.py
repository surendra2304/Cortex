from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass

class CircuitOpen(RuntimeError):
    pass

@dataclass
class CircuitState:
    consecutive_failures: int = 0
    opened_until: float = 0.0

class CircuitBreaker:
    def __init__(self, threshold: int = 3, reset_seconds: float = 15.0) -> None:
        self.threshold = threshold
        self.reset_seconds = reset_seconds
        self.state = CircuitState()
        self._lock = asyncio.Lock()

    async def before(self) -> None:
        async with self._lock:
            if time.monotonic() < self.state.opened_until:
                raise CircuitOpen("circuit is open")

    async def success(self) -> None:
        async with self._lock:
            self.state.consecutive_failures = 0
            self.state.opened_until = 0.0

    async def failure(self) -> None:
        async with self._lock:
            self.state.consecutive_failures += 1
            if self.state.consecutive_failures >= self.threshold:
                self.state.opened_until = time.monotonic() + self.reset_seconds
