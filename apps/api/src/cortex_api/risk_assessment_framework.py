"""
Cortex/apps/api/src/cortex_api/risk_assessment_framework.py — Cortex Risk Assessment Framework.

Comprehensive risk assessment: risk identification, analysis, evaluation,
treatment planning, monitoring, and reporting. Implements risk frameworks
like NIST, ISO 27001, and custom risk matrices.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class Risk:
    """A identified risk."""
    risk_id: str
    name: str
    description: str = ""
    category: str = ""  # financial, operational, strategic, compliance, reputational
    likelihood: float = 0.5  # 0-1
    impact: float = 0.5  # 0-1
    risk_score: float = 0.0
    risk_level: str = "medium"  # low, medium, high, critical
    inherent_risk: float = 0.0
    residual_risk: float = 0.0
    status: str = "identified"  # identified, analyzed, evaluated, treated, monitored, closed
    owner: str = ""
    treatment: str = ""  # accept, mitigate, transfer, avoid
    created_at: float = 0.0


@dataclass
class RiskCategory:
    """A risk category."""
    category_id: str
    name: str
    description: str = ""
    risks: list[str] = field(default_factory=list)
    total_inherent: float = 0.0
    total_residual: float = 0.0


@dataclass
class RiskMatrix:
    """A risk assessment matrix."""
    matrix_id: str
    name: str
    likelihood_scale: list[str] = field(default_factory=lambda: ["Rare", "Unlikely", "Possible", "Likely", "Almost Certain"])
    impact_scale: list[str] = field(default_factory=lambda: ["Negligible", "Minor", "Moderate", "Major", "Catastrophic"])
    cells: dict = field(default_factory=dict)  # {likelihood_idx: {impact_idx: risk_level}}


@dataclass
class TreatmentPlan:
    """A risk treatment plan."""
    plan_id: str
    risk_id: str
    treatment_strategy: str = ""  # mitigate, transfer, avoid, accept
    actions: list[str] = field(default_factory=list)
    budget: float = 0.0
    deadline: float = 0.0
    responsible: str = ""
    status: str = "planned"  # planned, in_progress, completed
    expected_residual: float = 0.0
    created_at: float = 0.0


@dataclass
class RiskMonitor:
    """Risk monitoring setup."""
    monitor_id: str
    risk_id: str
    metrics: list[str] = field(default_factory=list)
    thresholds: dict = field(default_factory=dict)
    frequency: str = "daily"  # hourly, daily, weekly, monthly
    last_check: float = 0.0
    alerts: int = 0
    status: str = "active"


@dataclass
class RiskReport:
    """Comprehensive risk report."""
    report_id: str
    total_risks: int = 0
    critical_risks: int = 0
    high_risks: int = 0
    medium_risks: int = 0
    low_risks: int = 0
    inherent_exposure: float = 0.0
    residual_exposure: float = 0.0
    risk_reduction: float = 0.0
    top_risks: list[str] = field(default_factory=list)
    trend: str = "stable"


@dataclass
class RiskEvent:
    """A risk event (risk materialization)."""
    event_id: str
    risk_id: str
    description: str = ""
    actual_impact: float = 0.0
    detected_at: float = 0.0
    root_cause: str = ""
    lesson_learned: str = ""


class RiskAssessmentFramework:
    """Risk assessment framework engine."""

    def __init__(self):
        self._risks: dict[str, Risk] = {}
        self._categories: dict[str, RiskCategory] = {}
        self._matrix: RiskMatrix | None = None
        self._treatments: dict[str, TreatmentPlan] = {}
        self._monitors: dict[str, RiskMonitor] = {}
        self._events: list[RiskEvent] = []
        self._reports: list[RiskReport] = []

        # Create default matrix
        self._create_matrix()

    def _create_matrix(self):
        """Create default risk matrix."""
        matrix = RiskMatrix(
            matrix_id=hashlib.md5(f"matrix:{time.time()}".encode()).hexdigest()[:12],
            name="Standard Risk Matrix",
        )

        levels = ["low", "medium", "high", "critical"]
        for l in range(5):
            matrix.cells[l] = {}
            for i in range(5):
                score = (l + 1) * (i + 1)
                level = "low" if score <= 4 else "medium" if score <= 9 else "high" if score <= 14 else "critical"
                matrix.cells[l][i] = level

        self._matrix = matrix
        return matrix

    def identify_risk(
        self,
        name: str,
        description: str,
        category: str,
        likelihood: float,
        impact: float,
        owner: str = "",
    ) -> Risk:
        """Identify a new risk."""
        risk = Risk(
            risk_id=hashlib.md5(
                f"risk:{name}:{time.time()}".encode()
            ).hexdigest()[:12],
            name=name,
            description=description,
            category=category,
            likelihood=likelihood,
            impact=impact,
            inherent_risk=likelihood * impact,
            status="identified",
            owner=owner,
            created_at=time.time(),
        )

        # Calculate risk level from matrix
        if self._matrix:
            l_idx = int(likelihood * 4)
            i_idx = int(impact * 4)
            risk.risk_level = self._matrix.cells.get(l_idx, {}).get(i_idx, "medium")
        else:
            score = likelihood * impact
            risk.risk_level = "critical" if score > 0.6 else "high" if score > 0.4 else "medium" if score > 0.2 else "low"

        risk.risk_score = risk.inherent_risk

        # Add to category
        cat = self._categories.get(category)
        if not cat:
            cat = RiskCategory(
                category_id=hashlib.md5(f"category:{category}".encode()).hexdigest()[:12],
                name=category,
            )
            self._categories[category] = cat
        cat.risks.append(risk.risk_id)

        self._risks[risk.risk_id] = risk
        return risk

    def create_treatment(
        self,
        risk_id: str,
        strategy: str,
        actions: list[str],
        budget: float = 0.0,
        deadline: float | None = None,
        responsible: str = "",
        expected_residual: float = 0.0,
    ) -> TreatmentPlan:
        """Create a risk treatment plan."""
        plan = TreatmentPlan(
            plan_id=hashlib.md5(
                f"treatment:{risk_id}:{time.time()}".encode()
            ).hexdigest()[:12],
            risk_id=risk_id,
            treatment_strategy=strategy,
            actions=actions,
            budget=budget,
            deadline=deadline or time.time() + 30 * 86400,
            responsible=responsible,
            expected_residual=expected_residual,
            created_at=time.time(),
        )

        self._treatments[plan.plan_id] = plan

        # Update risk
        risk = self._risks.get(risk_id)
        if risk:
            risk.treatment = strategy
            risk.status = "treated"
            risk.residual_risk = expected_residual

        return plan

    def add_monitor(self, risk_id: str, metrics: list[str], frequency: str = "daily") -> RiskMonitor:
        """Add risk monitoring."""
        monitor = RiskMonitor(
            monitor_id=hashlib.md5(
                f"monitor:{risk_id}:{time.time()}".encode()
            ).hexdigest()[:12],
            risk_id=risk_id,
            metrics=metrics,
            frequency=frequency,
            last_check=time.time(),
            status="active",
        )

        self._monitors[monitor.monitor_id] = monitor
        return monitor

    def record_event(self, risk_id: str, description: str, actual_impact: float, root_cause: str = "") -> RiskEvent:
        """Record a risk event."""
        event = RiskEvent(
            event_id=hashlib.md5(
                f"event:{risk_id}:{time.time()}".encode()
            ).hexdigest()[:12],
            risk_id=risk_id,
            description=description,
            actual_impact=actual_impact,
            detected_at=time.time(),
            root_cause=root_cause,
        )

        self._events.append(event)
        return event

    def generate_report(self) -> RiskReport:
        """Generate a comprehensive risk report."""
        risks = list(self._risks.values())

        report = RiskReport(
            report_id=hashlib.md5(
                f"report:{time.time()}".encode()
            ).hexdigest()[:12],
            total_risks=len(risks),
            critical_risks=sum(1 for r in risks if r.risk_level == "critical"),
            high_risks=sum(1 for r in risks if r.risk_level == "high"),
            medium_risks=sum(1 for r in risks if r.risk_level == "medium"),
            low_risks=sum(1 for r in risks if r.risk_level == "low"),
            inherent_exposure=sum(r.inherent_risk for r in risks),
            residual_exposure=sum(r.residual_risk for r in risks),
            top_risks=[r.name for r in sorted(risks, key=lambda x: x.risk_score, reverse=True)[:5]],
        )

        report.risk_reduction = (
            (report.inherent_exposure - report.residual_exposure) / max(0.01, report.inherent_exposure)
        ) if report.inherent_exposure > 0 else 0

        report.trend = "improving" if report.risk_reduction > 0.3 else "stable" if report.risk_reduction > 0.1 else "declining"

        self._reports.append(report)
        return report

    def get_report(self) -> dict:
        """Get risk assessment framework report."""
        latest = self._reports[-1] if self._reports else RiskReport()

        return {
            "total_risks": len(self._risks),
            "total_categories": len(self._categories),
            "total_treatments": len(self._treatments),
            "total_monitors": len(self._monitors),
            "total_events": len(self._events),
            "total_reports": len(self._reports),
            "critical_risks": latest.critical_risks,
            "high_risks": latest.high_risks,
            "medium_risks": latest.medium_risks,
            "low_risks": latest.low_risks,
            "inherent_exposure": round(latest.inherent_exposure, 3),
            "residual_exposure": round(latest.residual_exposure, 3),
            "risk_reduction": round(latest.risk_reduction, 3),
            "trend": latest.trend,
            "risks_by_category": {
                cat.name: {
                    "count": len(cat.risks),
                    "inherent": round(sum(self._risks[rid].inherent_risk for rid in cat.risks if rid in self._risks), 3),
                    "residual": round(sum(self._risks[rid].residual_risk for rid in cat.risks if rid in self._risks), 3),
                }
                for cat in self._categories.values()
            },
            "top_risks": [
                {"name": r.name, "level": r.risk_level, "score": r.risk_score, "category": r.category}
                for r in sorted(self._risks.values(), key=lambda x: x.risk_score, reverse=True)[:10]
            ],
            "recent_events": [
                {"risk": e.risk_id, "description": e.description[:60], "impact": e.actual_impact}
                for e in self._events[-5:]
            ],
            "active_treatments": [
                {"risk": t.risk_id, "strategy": t.treatment_strategy, "status": t.status, "budget": t.budget}
                for t in self._treatments.values() if t.status != "completed"
            ],
        }


risk_framework = RiskAssessmentFramework()


@router.post("/api/v1/cortex/risk/risks")
async def identify_risk(payload: dict):
    """Identify a new risk."""
    risk = risk_framework.identify_risk(
        name=payload["name"],
        description=payload["description"],
        category=payload["category"],
        likelihood=payload["likelihood"],
        impact=payload["impact"],
        owner=payload.get("owner", ""),
    )
    return {"risk_id": risk.risk_id, "name": risk.name, "level": risk.risk_level, "score": risk.risk_score}


@router.post("/api/v1/cortex/risk/treatments")
async def create_treatment(payload: dict):
    """Create a risk treatment plan."""
    plan = risk_framework.create_treatment(
        risk_id=payload["risk_id"],
        strategy=payload["strategy"],
        actions=payload.get("actions", []),
        budget=payload.get("budget", 0.0),
        responsible=payload.get("responsible", ""),
        expected_residual=payload.get("expected_residual", 0.0),
    )
    return {"plan_id": plan.plan_id, "risk_id": plan.risk_id, "strategy": plan.treatment_strategy, "status": plan.status}


@router.post("/api/v1/cortex/risk/monitors")
async def add_monitor(payload: dict):
    """Add risk monitoring."""
    monitor = risk_framework.add_monitor(
        risk_id=payload["risk_id"],
        metrics=payload.get("metrics", []),
        frequency=payload.get("frequency", "daily"),
    )
    return {"monitor_id": monitor.monitor_id, "risk_id": monitor.risk_id, "frequency": monitor.frequency}


@router.post("/api/v1/cortex/risk/events")
async def record_event(payload: dict):
    """Record a risk event."""
    event = risk_framework.record_event(
        risk_id=payload["risk_id"],
        description=payload["description"],
        actual_impact=payload["actual_impact"],
        root_cause=payload.get("root_cause", ""),
    )
    return {"event_id": event.event_id, "risk_id": event.risk_id, "impact": event.actual_impact}


@router.get("/api/v1/cortex/risk/report")
async def get_report():
    """Get risk assessment framework report."""
    return risk_framework.get_report()
