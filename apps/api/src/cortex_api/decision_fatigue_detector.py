"""
Cortex/apps/api/src/cortex_api/decision_fatigue_detector.py — Cortex Decision Fatigue Detector.

Decision fatigue measurement, cognitive load assessment, decision quality degradation,
and optimal decision cadence recommendation.
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
    """A recorded decision with fatigue context."""
    decision_id: str
    description: str
    timestamp: float
    complexity: float = 0.5
    time_spent: float = 0.0
    quality_score: float = 0.8
    fatigue_level: float = 0.0


@dataclass
class FatigueAssessment:
    """A fatigue assessment."""
    assessment_id: str
    total_decisions: int = 0
    avg_fatigue: float = 0.0
    max_fatigue: float = 0.0
    fatigue_trend: str = "stable"  # increasing, decreasing, stable
    recommendations: list[str] = field(default_factory=list)


@dataclass
class CadenceRecommendation:
    """Decision cadence recommendation."""
    recommendation_id: str
    optimal_interval: float = 0.0
    max_daily_decisions: int = 0
    break_frequency: float = 0.0
    rationale: str = ""


class DecisionFatigueDetector:
    """Engine for decision fatigue detection."""

    def __init__(self) -> None:
        self._records: list[DecisionRecord] = []
        self._assessments: list[FatigueAssessment] = []
        self._recommendations: list[CadenceRecommendation] = []

    def record_decision(self, description: str, complexity: float = 0.5,
                        time_spent: float = 0.0,
                        quality_score: float = 0.8) -> DecisionRecord:
        """Record a decision."""
        record_id = f"dec_{uuid.uuid4().hex[:12]}"
        record = DecisionRecord(
            decision_id=record_id, description=description,
            timestamp=time.time(), complexity=complexity,
            time_spent=time_spent, quality_score=quality_score,
        )

        # Calculate fatigue based on recent decisions
        recent = [r for r in self._records if r.timestamp > time.time() - 86400]
        fatigue = 0.0
        if recent:
            fatigue = (
                len(recent) * 0.05 +
                sum(r.complexity for r in recent) * 0.1 +
                sum(r.time_spent for r in recent) * 0.01
            )
            fatigue = min(1.0, fatigue)

        record.fatigue_level = fatigue
        self._records.append(record)
        return record

    def assess_fatigue(self) -> FatigueAssessment:
        """Assess decision fatigue."""
        assessment_id = f"fat_{uuid.uuid4().hex[:12]}"
        assessment = FatigueAssessment(assessment_id=assessment_id)
        assessment.total_decisions = len(self._records)

        if self._records:
            assessment.avg_fatigue = sum(r.fatigue_level for r in self._records) / len(self._records)
            assessment.max_fatigue = max(r.fatigue_level for r in self._records)

            # Trend analysis
            recent_half = self._records[-len(self._records) // 2:]
            older_half = self._records[:len(self._records) // 2]
            recent_avg = sum(r.fatigue_level for r in recent_half) / max(1, len(recent_half))
            older_avg = sum(r.fatigue_level for r in older_half) / max(1, len(older_half))

            if recent_avg > older_avg + 0.1:
                assessment.fatigue_trend = "increasing"
            elif recent_avg < older_avg - 0.1:
                assessment.fatigue_trend = "decreasing"
            else:
                assessment.fatigue_trend = "stable"

            if assessment.avg_fatigue > 0.6:
                assessment.recommendations = [
                    "Take a break from decision-making",
                    "Delegate lower-priority decisions",
                    "Reduce decision complexity",
                    "Implement decision automation",
                ]
            else:
                assessment.recommendations = [
                    "Decision fatigue within normal range",
                    "Continue monitoring",
                ]

        self._assessments.append(assessment)
        return assessment

    def recommend_cadence(self) -> CadenceRecommendation:
        """Recommend decision cadence."""
        recommendation_id = f"cad_{uuid.uuid4().hex[:12]}"
        recommendation = CadenceRecommendation(recommendation_id=recommendation_id)

        if self._records:
            avg_fatigue = sum(r.fatigue_level for r in self._records) / len(self._records)
            recommendation.optimal_interval = max(60.0, 3600.0 - avg_fatigue * 1800.0)
            recommendation.max_daily_decisions = max(10, 50 - int(avg_fatigue * 30))
            recommendation.break_frequency = max(0.1, 0.3 - avg_fatigue * 0.2)
            recommendation.rationale = (
                f"Based on {len(self._records)} decisions with average fatigue {avg_fatigue:.2f}"
            )
        else:
            recommendation.optimal_interval = 3600.0
            recommendation.max_daily_decisions = 30
            recommendation.break_frequency = 0.2
            recommendation.rationale = "Default cadence: no decision history"

        self._recommendations.append(recommendation)
        return recommendation

    def get_records(self, min_fatigue: float = 0.0) -> list[dict[str, Any]]:
        """Get decision records."""
        records = [r for r in self._records if r.fatigue_level >= min_fatigue]
        return [
            {"description": r.description[:60], "complexity": r.complexity,
             "quality": r.quality_score, "fatigue": r.fatigue_level}
            for r in records[-10:]
        ]

    def get_report(self) -> dict[str, Any]:
        """Get engine report."""
        return {
            "total_decisions": len(self._records),
            "total_assessments": len(self._assessments),
            "total_recommendations": len(self._recommendations),
            "engine_status": "operational",
        }


engine = DecisionFatigueDetector()


@router.post("/cortex/fatigue/decisions")
async def record_decision(description: str, complexity: float = 0.5,
                          time_spent: float = 0.0, quality_score: float = 0.8):
    """Record a decision."""
    record = engine.record_decision(description, complexity, time_spent, quality_score)
    return {"decision_id": record.decision_id, "fatigue": record.fatigue_level}


@router.post("/cortex/fatigue/assess")
async def assess_fatigue():
    """Assess decision fatigue."""
    assessment = engine.assess_fatigue()
    return {
        "assessment_id": assessment.assessment_id,
        "total_decisions": assessment.total_decisions,
        "avg_fatigue": assessment.avg_fatigue,
        "trend": assessment.fatigue_trend,
        "recommendations": assessment.recommendations,
    }


@router.post("/cortex/fatigue/cadence")
async def recommend_cadence():
    """Recommend decision cadence."""
    recommendation = engine.recommend_cadence()
    return {
        "optimal_interval": recommendation.optimal_interval,
        "max_daily_decisions": recommendation.max_daily_decisions,
        "break_frequency": recommendation.break_frequency,
        "rationale": recommendation.rationale,
    }


@router.get("/cortex/fatigue/records")
async def get_records(min_fatigue: float = 0.0):
    """Get decision records."""
    return {"records": engine.get_records(min_fatigue)}


@router.get("/cortex/fatigue/report")
async def fatigue_report():
    """Get fatigue detector report."""
    return engine.get_report()
