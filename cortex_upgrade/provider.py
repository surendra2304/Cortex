from __future__ import annotations
import asyncio
import time
from typing import Any, Awaitable, Callable
from .circuit import CircuitBreaker, CircuitOpen
from .models import FailureKind
from .retry import retry

class Provider:
    def __init__(self, name: str, fn: Callable[..., Awaitable[Any]], breaker: CircuitBreaker | None = None) -> None:
        self.name = name
        self.fn = fn
        self.breaker = breaker or CircuitBreaker()

    async def call(self, **kwargs: Any) -> dict[str, Any]:
        await self.breaker.before()
        started = time.perf_counter()
        try:
            output = await retry(
                lambda: self.fn(**kwargs),
                attempts=2,
                base_delay=.01,
                retryable=lambda exc: isinstance(exc, (TimeoutError, ConnectionError)),
            )
            await self.breaker.success()
            return {"ok": True, "provider": self.name, "output": output, "latency_ms": (time.perf_counter()-started)*1000}
        except asyncio.CancelledError:
            raise
        except CircuitOpen:
            return {"ok": False, "provider": self.name, "failure": FailureKind.PROVIDER_UNAVAILABLE.value, "retryable": True}
        except TimeoutError:
            await self.breaker.failure()
            return {"ok": False, "provider": self.name, "failure": FailureKind.TIMEOUT.value, "retryable": True}
        except PermissionError:
            await self.breaker.failure()
            return {"ok": False, "provider": self.name, "failure": FailureKind.AUTHENTICATION.value, "retryable": False}
        except ValueError:
            await self.breaker.failure()
            return {"ok": False, "provider": self.name, "failure": FailureKind.INVALID.value, "retryable": False}
        except Exception as exc:
            await self.breaker.failure()
            return {"ok": False, "provider": self.name, "failure": FailureKind.TRANSIENT.value, "retryable": True, "error_type": type(exc).__name__}
