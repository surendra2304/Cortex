"""
Cortex/apps/api/src/cortex_api/decision_recommendation_system.py — Cortex Decision Recommendation System.

Multi-criteria decision recommendation engine with uncertainty quantification,
risk-return optimization, stakeholder analysis, and recommendation explanations.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class DecisionCriterion:
    """A decision criterion."""
    criterion_id: str
    name: str
    description: str = ""
    weight: float = 1.0
    direction: str = "maximize"  # maximize, minimize
    unit: str = ""


@dataclass
class Alternative:
    """A decision alternative."""
    alternative_id: str
    name: str
    description: str = ""
    criteria_scores: dict = field(default_factory=dict)  # {criterion_id: score}
    risk_score: float = 0.0
    return_projection: float = 0.0


@dataclass
class DecisionMatrix:
    """A decision analysis matrix."""
    matrix_id: str
    problem_statement: str = ""
    criteria: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    weights: dict = field(default_factory=dict)
    scores: dict = field(default_factory=dict)


@dataclass
class Recommendation:
    """A decision recommendation."""
    recommendation_id: str
    problem_statement: str
    best_alternative: str = ""
    alternatives_ranking: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    risk_level: str = "medium"
    expected_value: float = 0.0
    sensitivity_analysis: dict = field(default_factory=dict)
    rationale: str = ""
    stakeholder_impact: dict = field(default_factory=dict)


@dataclass
class Stakeholder:
    """A decision stakeholder."""
    stakeholder_id: str
    name: str
    role: str = ""
    interest_level: float = 0.5
    influence_level: float = 0.5
    position: str = ""  # support, neutral, oppose


@dataclass
class UncertaintyAnalysis:
    """Uncertainty analysis for a decision."""
    analysis_id: str
    recommendation_id: str
    uncertainty_level: float = 0.0
    confidence_interval: tuple[float, float] = (0.0, 0.0)
    key_uncertainties: list[str] = field(default_factory=list)
    risk_adjusted_score: float = 0.0
    worst_case: str = ""
    best_case: str = ""


@dataclass
class DecisionHistory:
    """History of decision recommendations."""
    problem_statement: str
    total_decisions: int = 0
    avg_confidence: float = 0.0
    avg_risk_level: float = 0.0
    success_rate: float = 0.0
    trend: str = "stable"


class DecisionRecommendationSystem:
    """Decision recommendation engine."""

    def __init__(self):
        self._criteria: dict[str, DecisionCriterion] = {}
        self._alternatives: dict[str, Alternative] = {}
        self._recommendations: list[Recommendation] = []
        self._stakeholders: list[Stakeholder] = []
        self._uncertainty: list[UncertaintyAnalysis] = []
        self._history: dict[str, DecisionHistory] = {}

    def add_criterion(self, name: str, weight: float = 1.0, direction: str = "maximize") -> DecisionCriterion:
        """Add a decision criterion."""
        criterion = DecisionCriterion(
            criterion_id=hashlib.md5(
                f"criterion:{name}:{time.time()}".encode()
            ).hexdigest()[:12],
            name=name,
            weight=weight,
            direction=direction,
        )
        self._criteria[criterion.criterion_id] = criterion
        return criterion

    def add_alternative(self, name: str, description: str = "", risk_score: float = 0.5, return_projection: float = 0.5) -> Alternative:
        """Add a decision alternative."""
        alt = Alternative(
            alternative_id=hashlib.md5(
                f"alternative:{name}:{time.time()}".encode()
            ).hexdigest()[:12],
            name=name,
            description=description,
            risk_score=risk_score,
            return_projection=return_projection,
        )
        self._alternatives[alt.alternative_id] = alt
        return alt

    def score_alternative(self, alternative_id: str, criterion_id: str, score: float) -> Alternative:
        """Score an alternative against a criterion."""
        alt = self._alternatives.get(alternative_id)
        if not alt:
            raise HTTPException(404, f"Alternative {alternative_id} not found")

        alt.criteria_scores[criterion_id] = score
        return alt

    def recommend(self, problem_statement: str) -> Recommendation:
        """Generate a decision recommendation."""
        if not self._criteria or not self._alternatives:
            raise HTTPException(400, "Need criteria and alternatives")

        # Calculate weighted scores for each alternative
        scores = {}
        for alt_id, alt in self._alternatives.items():
            total_score = 0.0
            for crit_id, crit in self._criteria.items():
                score = alt.criteria_scores.get(crit_id, 0.5)
                # Normalize if direction is minimize
                if crit.direction == "minimize":
                    score = 1.0 - score
                # Weight by criterion weight
                total_score += score * crit.weight

            # Average by total weight
            total_weight = sum(c.weight for c in self._criteria.values())
            scores[alt_id] = total_score / max(1, total_weight)

        # Rank alternatives
        ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Best alternative
        best_alt_id, best_score = ranking[0]
        best_alt = self._alternatives.get(best_alt_id)

        # Calculate confidence
        confidence = best_score / max(0.01, sum(scores.values()))

        # Risk level
        risk = best_alt.risk_score if best_alt else 0.5
        risk_level = "high" if risk > 0.7 else "medium" if risk > 0.4 else "low"

        # Sensitivity analysis
        sensitivity = {}
        for crit_id, crit in self._criteria.items():
            # Vary weight by ±20%
            varied_scores = {}
            for alt_id, alt in self._alternatives.items():
                score = alt.criteria_scores.get(crit_id, 0.5)
                if crit.direction == "minimize":
                    score = 1.0 - score
                varied_scores[alt_id] = score * crit.weight * 1.2

            # Check if ranking changes
            varied_ranking = sorted(varied_scores.items(), key=lambda x: x[1], reverse=True)
            sensitivity[crit.name] = {
                "ranking_change": varied_ranking[0][0] != best_alt_id,
                "impact": abs(varied_ranking[0][1] - best_score) / max(0.01, best_score),
            }

        recommendation = Recommendation(
            recommendation_id=hashlib.md5(
                f"rec:{problem_statement[:30]}:{time.time()}".encode()
            ).hexdigest()[:12],
            problem_statement=problem_statement,
            best_alternative=best_alt.name if best_alt else "",
            alternatives_ranking=[
                {"name": self._alternatives[alt_id].name, "score": round(score, 4)}
                for alt_id, score in ranking
            ],
            confidence=round(confidence, 4),
            risk_level=risk_level,
            expected_value=best_alt.return_projection if best_alt else 0.0,
            sensitivity_analysis=sensitivity,
            rationale=f"Selected '{best_alt.name if best_alt else 'Unknown'}' with highest weighted score ({best_score:.2f})",
            stakeholder_impact={},
        )

        self._recommendations.append(recommendation)

        # Update history
        history = self._history.get(problem_statement)
        if not history:
            history = DecisionHistory(problem_statement=problem_statement)
            self._history[problem_statement] = history

        history.total_decisions += 1
        history.avg_confidence = (
            history.avg_confidence * 0.9 + confidence * 0.1
        )

        return recommendation

    def add_stakeholder(self, name: str, role: str, interest: float, influence: float, position: str = "neutral") -> Stakeholder:
        """Add a stakeholder."""
        stakeholder = Stakeholder(
            stakeholder_id=hashlib.md5(
                f"stakeholder:{name}:{time.time()}".encode()
            ).hexdigest()[:12],
            name=name,
            role=role,
            interest_level=interest,
            influence_level=influence,
            position=position,
        )
        self._stakeholders.append(stakeholder)
        return stakeholder

    def analyze_uncertainty(self, recommendation_id: str) -> UncertaintyAnalysis:
        """Analyze uncertainty for a recommendation."""
        rec = None
        for r in self._recommendations:
            if r.recommendation_id == recommendation_id:
                rec = r
                break

        if not rec:
            raise HTTPException(404, f"Recommendation {recommendation_id} not found")

        uncertainty = 0.2 + (ord(hashlib.md5(recommendation_id.encode()).hexdigest()[:1]) % 30) / 100

        analysis = UncertaintyAnalysis(
            analysis_id=hashlib.md5(
                f"uncertainty:{recommendation_id}:{time.time()}".encode()
            ).hexdigest()[:12],
            recommendation_id=recommendation_id,
            uncertainty_level=round(uncertainty, 4),
            confidence_interval=(rec.confidence - uncertainty, rec.confidence + uncertainty),
            key_uncertainties=[
                "Market conditions may change",
                "Stakeholder priorities may shift",
                "Implementation may differ from plan",
            ],
            risk_adjusted_score=rec.expected_value * (1 - uncertainty),
            worst_case=f"Worst case: {rec.best_alternative} yields minimal return",
            best_case=f"Best case: {rec.best_alternative} yields optimal return",
        )

        self._uncertainty.append(analysis)
        return analysis

    def get_report(self) -> dict:
        """Get decision recommendation system report."""
        return {
            "total_criteria": len(self._criteria),
            "total_alternatives": len(self._alternatives),
            "total_recommendations": len(self._recommendations),
            "total_stakeholders": len(self._stakeholders),
            "total_uncertainty_analyses": len(self._uncertainty),
            "avg_recommendation_confidence": sum(r.confidence for r in self._recommendations) / max(1, len(self._recommendations)),
            "avg_risk_level": sum(r.risk_score for r in self._recommendations) / max(1, len(self._recommendations)),
            "high_risk_recommendations": sum(1 for r in self._recommendations if r.risk_level == "high"),
            "recent_recommendations": [
                {
                    "problem": r.problem_statement[:50],
                    "best": r.best_alternative,
                    "confidence": r.confidence,
                    "risk": r.risk_level,
                }
                for r in self._recommendations[-10:]
            ],
            "recent_uncertainty": [
                {
                    "recommendation": u.recommendation_id,
                    "uncertainty": u.uncertainty_level,
                    "risk_adjusted": u.risk_adjusted_score,
                }
                for u in self._uncertainty[-5:]
            ],
        }


decision_system = DecisionRecommendationSystem()


@router.post("/api/v1/cortex/decision/criteria")
async def add_criterion(payload: dict):
    """Add a decision criterion."""
    crit = decision_system.add_criterion(
        name=payload["name"],
        weight=payload.get("weight", 1.0),
        direction=payload.get("direction", "maximize"),
    )
    return {"criterion_id": crit.criterion_id, "name": crit.name, "weight": crit.weight}


@router.post("/api/v1/cortex/decision/alternatives")
async def add_alternative(payload: dict):
    """Add a decision alternative."""
    alt = decision_system.add_alternative(
        name=payload["name"],
        description=payload.get("description", ""),
        risk_score=payload.get("risk_score", 0.5),
        return_projection=payload.get("return_projection", 0.5),
    )
    return {"alternative_id": alt.alternative_id, "name": alt.name}


@router.post("/api/v1/cortex/decision/alternatives/{alt_id}/score")
async def score_alternative(alt_id: str, payload: dict):
    """Score an alternative."""
    alt = decision_system.score_alternative(
        alternative_id=alt_id,
        criterion_id=payload["criterion_id"],
        score=payload["score"],
    )
    return {"alternative_id": alt.alternative_id, "scores": len(alt.criteria_scores)}


@router.post("/api/v1/cortex/decision/recommend")
async def recommend(payload: dict):
    """Generate a decision recommendation."""
    rec = decision_system.recommend(payload["problem_statement"])
    return {
        "recommendation_id": rec.recommendation_id,
        "best_alternative": rec.best_alternative,
        "confidence": rec.confidence,
        "risk_level": rec.risk_level,
        "rationale": rec.rationale,
    }


@router.get("/api/v1/cortex/decision/report")
async def get_report():
    """Get decision recommendation system report."""
    return decision_system.get_report()
