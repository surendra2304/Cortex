from __future__ import annotations
import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass

@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    remaining: int
    retry_after: float

class AtomicSlidingWindow:
    """Reference backend for tests/dev; production should use Redis + atomic script."""
    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def consume(self, key: str, limit: int, window_seconds: float) -> LimitResult:
        if limit <= 0 or window_seconds <= 0:
            raise ValueError("invalid rate limit")
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets[key]
            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= limit:
                retry = max(0.0, bucket[0] + window_seconds - now)
                return LimitResult(False, 0, retry)
            bucket.append(now)
            return LimitResult(True, limit - len(bucket), 0.0)
