from __future__ import annotations
from dataclasses import dataclass, field
from datetime import UTC, datetime

@dataclass
class StrategyStats:
    strategy_id: str
    wins: int = 0
    losses: int = 0
    exposures: int = 0
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    @property
    def win_rate(self) -> float:
        n = self.wins + self.losses
        return self.wins / n if n else 0.0

class StrategyLearner:
    def __init__(self, promote_at=.60, demote_at=.30, min_samples=20):
        if not 0 < demote_at < promote_at < 1:
            raise ValueError("invalid promotion thresholds")
        self.promote_at = promote_at
        self.demote_at = demote_at
        self.min_samples = min_samples
        self._stats: dict[str, StrategyStats] = {}

    def observe(self, strategy_id: str, won: bool) -> StrategyStats:
        s = self._stats.setdefault(strategy_id, StrategyStats(strategy_id))
        s.exposures += 1
        if won: s.wins += 1
        else: s.losses += 1
        s.updated_at = datetime.now(UTC)
        return s

    def disposition(self, strategy_id: str) -> str:
        s = self._stats[strategy_id]
        if s.wins + s.losses < self.min_samples:
            return "hold"
        if s.win_rate >= self.promote_at:
            return "promote"
        if s.win_rate < self.demote_at:
            return "demote"
        return "hold"
