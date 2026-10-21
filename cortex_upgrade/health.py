from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class DependencyHealth:
    name: str
    ok: bool
    detail: str


class Readiness:
    def __init__(self, checks: dict[str, Callable[[], Awaitable[bool]]]) -> None:
        self.checks = checks

    async def probe(self) -> tuple[bool, list[DependencyHealth]]:
        results: list[DependencyHealth] = []
        for name, check in self.checks.items():
            try:
                value = await check()
                if not isinstance(value, bool):
                    results.append(DependencyHealth(name, False, f"invalid result type: {type(value).__name__}"))
                    continue
                results.append(DependencyHealth(name, value, "ok" if value else "reported down"))
            except Exception as exc:
                results.append(DependencyHealth(name, False, type(exc).__name__))
        return all(result.ok for result in results), results
