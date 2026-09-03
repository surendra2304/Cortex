from __future__ import annotations
import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

async def retry(op: Callable[[], Awaitable[T]], *, attempts: int = 3,
                base_delay: float = .1, max_delay: float = 2.0,
                retryable: Callable[[Exception], bool] | None = None) -> T:
    if attempts < 1:
        raise ValueError("attempts must be positive")
    last: Exception | None = None
    for idx in range(attempts):
        try:
            return await op()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            last = exc
            if idx == attempts - 1 or (retryable and not retryable(exc)):
                raise
            await asyncio.sleep(min(max_delay, base_delay * (2 ** idx)) * random.uniform(.8, 1.2))
    assert last is not None
    raise last
