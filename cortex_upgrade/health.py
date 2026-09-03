from __future__ import annotations
from dataclasses import dataclass
from typing import Awaitable, Callable

@dataclass(frozen=True)
class DependencyHealth:
    name: str
    ok: bool
    detail: str

class Readiness:
    def __init__(self, checks: dict[str, Callable[[], Awaitable[bool]]]) -> None:
        self.checks = checks

    async def probe(self):
        results = []
        for name, check in self.checks.items():
            try:
                ok = bool(await check())
                results.append(DependencyHealth(name, ok, "ok" if ok else "reported down"))
            except Exception as exc:
                results.append(DependencyHealth(name, False, type(exc).__name__))
        return all(x.ok for x in results), results
