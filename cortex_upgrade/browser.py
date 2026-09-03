from __future__ import annotations
import asyncio
from dataclasses import dataclass
from urllib.parse import urlsplit
from .policy import PolicyEngine, PolicyDenied

@dataclass(frozen=True)
class BrowserPolicy:
    allowed_hosts: frozenset[str] = frozenset()
    max_navigation_hops: int = 5
    max_steps: int = 30

@dataclass(frozen=True)
class BrowserAction:
    kind: str
    target: str
    value: str | None = None

class BrowserGuard:
    def __init__(self, policy: BrowserPolicy) -> None:
        self.policy = policy
        self.steps = 0
        self.history: list[str] = []

    def validate_navigation(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise PolicyDenied("invalid browser URL")
        host = parts.hostname.lower().rstrip(".")
        if self.policy.allowed_hosts and host not in self.policy.allowed_hosts:
            raise PolicyDenied("host not allowlisted")
        PolicyEngine.validate_url(url, set(self.policy.allowed_hosts) if self.policy.allowed_hosts else None)
        if len(self.history) >= self.policy.max_navigation_hops:
            raise PolicyDenied("navigation hop limit exceeded")

    def record(self, action: BrowserAction) -> None:
        self.steps += 1
        if self.steps > self.policy.max_steps:
            raise PolicyDenied("browser step limit exceeded")
        self.history.append(action.target)

class BrowserSession:
    def __init__(self, guard: BrowserGuard) -> None:
        self.guard = guard
        self.closed = False

    async def navigate(self, url: str) -> None:
        if self.closed:
            raise RuntimeError("session closed")
        self.guard.validate_navigation(url)
        await asyncio.sleep(0)
        self.guard.record(BrowserAction("navigate", url))

    async def close(self) -> None:
        self.closed = True
