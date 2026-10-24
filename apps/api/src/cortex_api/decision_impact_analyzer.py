"""
Cortex/apps/api/src/cortex_api/decision_impact_analyzer.py — Cortex Decision Impact Analyzer.

Decision outcome tracking, impact measurement, decision quality scoring,
and organizational decision intelligence.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class DecisionRecord:
    """A recorded decision."""
    decision_id: str
    description: str
    context: str = ""
    options: list[str] = field(default_factory=list)
    chosen_option: str = ""
    rationale: str = ""
    decision_maker: str = ""
    created_at: float = field(default_factory=time.time)
    outcome: str = "pending"  # pending, positive, negative, neutral


@dataclass
class ImpactMetrics:
    """Impact metrics for a decision."""
    decision_id: str
    financial_impact: float = 0.0
    operational_impact: float = 0.0
    strategic_impact: float = 0.0
    stakeholder_satisfaction: float = 0.5
    overall_impact: float = 0.0
    measured_at: float = 0.0


@dataclass
class DecisionQualityScore:
    """A quality score for decision-making."""
    score_id: str
    period: str = ""
    total_decisions: int = 0
    positive_outcomes: int = 0
    quality_score: float = 0.0
    avg_impact: float = 0.0
    trends: list[dict] = field(default_factory=list)


class DecisionImpactAnalyzer:
    """Engine for decision impact analysis and quality scoring."""

    def __init__(self) -> None:
        self._decisions: dict[str, DecisionRecord] = {}
        self._impacts: dict[str, ImpactMetrics] = {}
        self._scores: list[DecisionQualityScore] = []

    def record_decision(self, description: str, context: str, options: list[str],
                        chosen_option: str, rationale: str,
                        decision_maker: str = "") -> str:
        """Record a decision."""
        decision_id = f"dec_{uuid.uuid4().hex[:12]}"
        decision = DecisionRecord(
            decision_id=decision_id, description=description, context=context,
            options=options, chosen_option=chosen_option, rationale=rationale,
            decision_maker=decision_maker,
        )
        self._decisions[decision_id] = decision
        return decision_id

    def record_outcome(self, decision_id: str, outcome: str,
                       financial_impact: float = 0.0, operational_impact: float = 0.0,
                       strategic_impact: float = 0.0,
                       stakeholder_satisfaction: float = 0.5) -> ImpactMetrics:
        """Record the outcome of a decision."""
        decision = self._decisions.get(decision_id)
        if not decision:
            raise HTTPException(status_code=404, detail="Decision not found")

        decision.outcome = outcome
        impact = ImpactMetrics(
            decision_id=decision_id,
            financial_impact=financial_impact,
            operational_impact=operational_impact,
            strategic_impact=strategic_impact,
            stakeholder_satisfaction=stakeholder_satisfaction,
            measured_at=time.time(),
        )
        impact.overall_impact = (
            financial_impact * 0.3 + operational_impact * 0.3 +
            strategic_impact * 0.3 + stakeholder_satisfaction * 0.1
        )
        self._impacts[decision_id] = impact
        return impact

    def calculate_quality_score(self, period: str = "all") -> DecisionQualityScore:
        """Calculate decision quality score."""
        score_id = f"score_{uuid.uuid4().hex[:12]}"
        score = DecisionQualityScore(score_id=score_id, period=period)
        score.total_decisions = len(self._decisions)
        score.positive_outcomes = sum(1 for d in self._decisions.values() if d.outcome == "positive")
        score.quality_score = score.positive_outcomes / max(1, score.total_decisions)

        impacts = list(self._impacts.values())
        if impacts:
            score.avg_impact = sum(i.overall_impact for i in impacts) / len(impacts)

        self._scores.append(score)
        return score

    def get_decisions(self, outcome: str | None = None) -> list[dict[str, Any]]:
        """Get decisions."""
        decisions = list(self._decisions.values())
        if outcome:
            decisions = [d for d in decisions if d.outcome == outcome]
        return [
            {
                "decision_id": d.decision_id,
                "description": d.description[:80],
                "chosen_option": d.chosen_option,
                "outcome": d.outcome,
            }
            for d in decisions
        ]

    def get_report(self) -> dict[str, Any]:
        """Get engine report."""
        return {
            "total_decisions": len(self._decisions),
            "total_impacts": len(self._impacts),
            "total_scores": len(self._scores),
            "engine_status": "operational",
        }


engine = DecisionImpactAnalyzer()


@router.post("/cortex/impact/decisions")
async def record_decision(description: str, context: str, options: list[str],
                          chosen_option: str, rationale: str, decision_maker: str = ""):
    """Record a decision."""
    decision_id = engine.record_decision(description, context, options, chosen_option, rationale, decision_maker)
    return {"decision_id": decision_id, "status": "recorded"}


@router.post("/cortex/impact/outcomes")
async def record_outcome(decision_id: str, outcome: str, financial_impact: float = 0.0,
                         operational_impact: float = 0.0, strategic_impact: float = 0.0,
                         stakeholder_satisfaction: float = 0.5):
    """Record a decision outcome."""
    impact = engine.record_outcome(decision_id, outcome, financial_impact, operational_impact,
                                   strategic_impact, stakeholder_satisfaction)
    return {"decision_id": decision_id, "overall_impact": impact.overall_impact}


@router.get("/cortex/impact/quality")
async def calculate_quality_score(period: str = "all"):
    """Calculate decision quality score."""
    score = engine.calculate_quality_score(period)
    return {
        "quality_score": score.quality_score,
        "total_decisions": score.total_decisions,
        "positive_outcomes": score.positive_outcomes,
        "avg_impact": score.avg_impact,
    }


@router.get("/cortex/impact/decisions")
async def get_decisions(outcome: str | None = None):
    """Get decisions."""
    return {"decisions": engine.get_decisions(outcome)}


@router.get("/cortex/impact/report")
async def impact_report():
    """Get impact analyzer report."""
    return engine.get_report()
