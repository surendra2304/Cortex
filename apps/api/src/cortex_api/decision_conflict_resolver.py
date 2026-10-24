"""
Cortex/apps/api/src/cortex_api/decision_conflict_resolver.py — Cortex Decision Conflict Resolver.

Resolves conflicts between multiple decision sources: conflicting predictions,
contradictory recommendations, multi-agent disagreements, and policy conflicts.
Provides conflict detection, arbitration, and resolution strategies.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class DecisionSource:
    """A decision source."""
    source_id: str
    source_name: str
    source_type: str = ""  # model, rule, agent, expert, policy
    recommendation: str = ""
    confidence: float = 0.0
    timestamp: float = 0.0
    rationale: str = ""
    weight: float = 1.0


@dataclass
class Conflict:
    """A conflict between decision sources."""
    conflict_id: str
    topic: str
    sources: list[str] = field(default_factory=list)
    description: str = ""
    severity: str = "medium"  # low, medium, high, critical
    detected_at: float = 0.0
    resolution: str = ""
    resolution_strategy: str = ""  # weighted_vote, highest_confidence, priority_order, policy_override
    resolved: bool = False
    resolved_at: float = 0.0


@dataclass
class ArbitrationResult:
    """Result of arbitration."""
    arbitration_id: str
    conflict_id: str
    winner: str = ""
    winner_recommendation: str = ""
    strategy_used: str = ""
    vote_distribution: dict = field(default_factory=dict)
    final_confidence: float = 0.0
    rationale: str = ""


@dataclass
class ResolutionPolicy:
    """Policy for resolving conflicts."""
    policy_id: str
    priority_order: list[str] = field(default_factory=list)  # source types in priority order
    use_weighted_vote: bool = True
    use_confidence: bool = True
    use_recency: bool = True
    min_conflict_threshold: float = 0.2
    auto_resolve: bool = True
    created_at: float = 0.0


@dataclass
class ConflictHistory:
    """History of conflicts and resolutions."""
    topic: str
    total_conflicts: int = 0
    resolved_conflicts: int = 0
    unresolved_conflicts: int = 0
    avg_resolution_time_ms: float = 0.0
    most_common_strategy: str = ""
    resolution_trend: str = "stable"  # improving, stable, declining


@dataclass
class ConsensusMetrics:
    """Metrics on consensus quality."""
    total_decisions: int = 0
    consensus_rate: float = 0.0  # percentage of decisions with consensus
    avg_disagreement_level: float = 0.0
    conflict_resolution_success: float = 0.0
    most_conflicted_topics: list[str] = field(default_factory=list)


class DecisionConflictResolver:
    """Decision conflict resolution engine."""

    def __init__(self):
        self._sources: dict[str, DecisionSource] = {}
        self._conflicts: list[Conflict] = []
        self._arbitrations: list[ArbitrationResult] = []
        self._policies: dict[str, ResolutionPolicy] = {}
        self._history: dict[str, ConflictHistory] = {}
        self._metrics: ConsensusMetrics = ConsensusMetrics()

        # Create default policy
        self._create_policy(
            priority_order=["policy", "expert", "agent", "model", "rule"],
            use_weighted_vote=True,
            use_confidence=True,
            use_recency=True,
        )

    def _create_policy(
        self,
        priority_order: list[str],
        use_weighted_vote: bool,
        use_confidence: bool,
        use_recency: bool,
    ) -> ResolutionPolicy:
        """Create a resolution policy."""
        policy = ResolutionPolicy(
            policy_id=hashlib.md5(
                f"policy:{time.time()}".encode()
            ).hexdigest()[:12],
            priority_order=priority_order,
            use_weighted_vote=use_weighted_vote,
            use_confidence=use_confidence,
            use_recency=use_recency,
            created_at=time.time(),
        )
        self._policies[policy.policy_id] = policy
        return policy

    def register_source(
        self,
        source_name: str,
        recommendation: str,
        confidence: float = 0.8,
        source_type: str = "model",
        rationale: str = "",
        weight: float = 1.0,
    ) -> DecisionSource:
        """Register a decision source."""
        source = DecisionSource(
            source_id=hashlib.md5(
                f"source:{source_name}:{recommendation[:30]}:{time.time()}".encode()
            ).hexdigest()[:12],
            source_name=source_name,
            source_type=source_type,
            recommendation=recommendation,
            confidence=confidence,
            timestamp=time.time(),
            rationale=rationale,
            weight=weight,
        )
        self._sources[source.source_id] = source
        return source

    def detect_conflict(self, topic: str, recommendations: list[dict]) -> Conflict:
        """Detect a conflict between recommendations."""
        # Check for disagreement
        unique_recs = set(r.get("recommendation", "") for r in recommendations)

        if len(unique_recs) <= 1:
            return Conflict(
                conflict_id="",
                topic=topic,
                sources=[r.get("source_id", "") for r in recommendations],
                description="No conflict: all sources agree",
                severity="low",
                detected_at=time.time(),
                resolved=True,
            )

        severity = "high" if len(unique_recs) >= 3 else "medium"

        conflict = Conflict(
            conflict_id=hashlib.md5(
                f"conflict:{topic}:{time.time()}".encode()
            ).hexdigest()[:12],
            topic=topic,
            sources=[r.get("source_id", "") for r in recommendations],
            description=f"{len(unique_recs)} conflicting recommendations from {len(recommendations)} sources",
            severity=severity,
            detected_at=time.time(),
        )

        self._conflicts.append(conflict)
        return conflict

    def arbitrate(self, conflict_id: str, policy_id: str = "") -> ArbitrationResult:
        """Arbitrate a conflict."""
        conflict = None
        for c in self._conflicts:
            if c.conflict_id == conflict_id:
                conflict = c
                break

        if not conflict:
            raise HTTPException(404, f"Conflict {conflict_id} not found")

        # Get policy
        policy = None
        for p in self._policies.values():
            if p.policy_id == policy_id or p.policy_id == list(self._policies.keys())[0]:
                policy = p
                break

        # Get sources
        sources = [self._sources.get(s) for s in conflict.sources]
        sources = [s for s in sources if s]

        # Weighted vote
        vote_distribution = {}
        total_weight = 0.0

        for source in sources:
            rec = source.recommendation
            weight = source.weight

            if policy.use_confidence:
                weight *= source.confidence

            if policy.use_recency:
                age_factor = max(0.1, 1.0 - (time.time() - source.timestamp) / 86400)
                weight *= age_factor

            vote_distribution[rec] = vote_distribution.get(rec, 0) + weight
            total_weight += weight

        # Find winner
        winner_rec = max(vote_distribution, key=vote_distribution.get)
        winner_source = max(sources, key=lambda s: s.weight * s.confidence)

        # Calculate final confidence
        final_confidence = vote_distribution[winner_rec] / max(0.1, total_weight)

        result = ArbitrationResult(
            arbitration_id=hashlib.md5(
                f"arbitration:{conflict_id}:{time.time()}".encode()
            ).hexdigest()[:12],
            conflict_id=conflict_id,
            winner=winner_source.source_name,
            winner_recommendation=winner_rec,
            strategy_used="weighted_vote" if policy.use_weighted_vote else "highest_confidence",
            vote_distribution={k: round(v, 2) for k, v in vote_distribution.items()},
            final_confidence=round(final_confidence, 2),
            rationale=f"Selected '{winner_rec}' with {final_confidence:.0%} weighted vote confidence",
        )

        self._arbitrations.append(result)

        # Mark conflict as resolved
        conflict.resolution = winner_rec
        conflict.resolution_strategy = result.strategy_used
        conflict.resolved = True
        conflict.resolved_at = time.time()

        # Update history
        history = self._history.get(conflict.topic)
        if not history:
            history = ConflictHistory(topic=conflict.topic)
            self._history[conflict.topic] = history

        history.total_conflicts += 1
        history.resolved_conflicts += 1

        return result

    def get_consensus_metrics(self) -> ConsensusMetrics:
        """Get consensus quality metrics."""
        total = len(self._conflicts)
        resolved = sum(1 for c in self._conflicts if c.resolved)

        self._metrics.total_decisions = total
        self._metrics.consensus_rate = 100.0 if total == 0 else (resolved / total * 100)
        self._metrics.conflict_resolution_success = resolved / max(1, total)
        self._metrics.avg_disagreement_level = len(set(c.topic for c in self._conflicts)) / max(1, total)

        # Find most conflicted topics
        topic_counts = {}
        for c in self._conflicts:
            topic_counts[c.topic] = topic_counts.get(c.topic, 0) + 1
        self._metrics.most_conflicted_topics = sorted(topic_counts, key=topic_counts.get, reverse=True)[:5]

        return self._metrics

    def get_report(self) -> dict:
        """Get decision conflict resolver report."""
        metrics = self.get_consensus_metrics()

        return {
            "total_sources": len(self._sources),
            "total_conflicts": len(self._conflicts),
            "total_arbitrations": len(self._arbitrations),
            "total_policies": len(self._policies),
            "total_topics": len(self._history),
            "resolved_conflicts": sum(1 for c in self._conflicts if c.resolved),
            "unresolved_conflicts": sum(1 for c in self._conflicts if not c.resolved),
            "critical_conflicts": sum(1 for c in self._conflicts if c.severity == "critical"),
            "consensus_rate": metrics.consensus_rate,
            "conflict_resolution_success": metrics.conflict_resolution_success,
            "most_conflicted_topics": metrics.most_conflicted_topics,
            "recent_conflicts": [
                {
                    "topic": c.topic[:50],
                    "severity": c.severity,
                    "resolved": c.resolved,
                    "strategy": c.resolution_strategy,
                }
                for c in self._conflicts[-10:]
            ],
            "recent_arbitrations": [
                {
                    "conflict": a.conflict_id,
                    "winner": a.winner,
                    "recommendation": a.winner_recommendation[:50],
                    "confidence": a.final_confidence,
                }
                for a in self._arbitrations[-5:]
            ],
        }


# Module-level singleton
conflict_resolver = DecisionConflictResolver()


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/cortex/conflicts/sources")
async def register_source(payload: dict):
    """Register a decision source."""
    source = conflict_resolver.register_source(
        source_name=payload["source_name"],
        recommendation=payload["recommendation"],
        confidence=payload.get("confidence", 0.8),
        source_type=payload.get("source_type", "model"),
        rationale=payload.get("rationale", ""),
        weight=payload.get("weight", 1.0),
    )
    return {"source_id": source.source_id, "source_name": source.source_name}


@router.post("/api/v1/cortex/conflicts/detect")
async def detect_conflict(payload: dict):
    """Detect a conflict between recommendations."""
    conflict = conflict_resolver.detect_conflict(
        topic=payload["topic"],
        recommendations=payload["recommendations"],
    )
    return {
        "conflict_id": conflict.conflict_id,
        "topic": conflict.topic,
        "severity": conflict.severity,
        "resolved": conflict.resolved,
    }


@router.post("/api/v1/cortex/conflicts/{conflict_id}/arbitrate")
async def arbitrate(conflict_id: str):
    """Arbitrate a conflict."""
    result = conflict_resolver.arbitrate(conflict_id)
    return {
        "arbitration_id": result.arbitration_id,
        "winner": result.winner,
        "recommendation": result.winner_recommendation,
        "strategy": result.strategy_used,
        "confidence": result.final_confidence,
    }


@router.get("/api/v1/cortex/conflicts/report")
async def get_report():
    """Get decision conflict resolver report."""
    return conflict_resolver.get_report()
