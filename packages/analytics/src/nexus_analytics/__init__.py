from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from nexus_api.db_models import LeadModel, LeadScoreHistoryModel, EventModel

logger = logging.getLogger("nexus-analytics")


class ScoreBreakdown(BaseModel):
    total: float
    behavior: float
    firmographic: float
    engagement: float
    source: float
    details: Dict[str, Any] = Field(default_factory=dict)


class ScoringEngine:
    """
    Explainable Lead Scoring Model per NEXUS spec:
    - BEHAVIOR (40%): pricing views, demo requests, doc depth, session recency, visit frequency
    - FIRMOGRAPHIC (30%): company domain classification, employee size hints, industry pages
    - ENGAGEMENT (20%): email opens, chat/form interactions, return visits
    - SOURCE (10%): campaign attribution, referrer quality
    """

    def compute_score(
        self,
        events: List[Dict[str, Any]],
        traits: Dict[str, Any],
        session_summary: Optional[Dict[str, Any]] = None
    ) -> ScoreBreakdown:
        session = session_summary or {}

        # 1. BEHAVIOR (40%)
        pricing_views = session.get("pricing_view_count", sum(1 for e in events if "pricing" in e.get("type", "").lower()))
        demo_views = session.get("demo_view_count", sum(1 for e in events if "demo" in e.get("type", "").lower()))
        docs_views = sum(1 for e in events if "doc" in e.get("type", "").lower() or "api" in e.get("type", "").lower())
        pages_depth = session.get("pages_viewed", len([e for e in events if "page_view" in e.get("type", "").lower()]))
        
        behavior_raw = (
            min(pricing_views * 0.15, 0.40) +
            min(demo_views * 0.25, 0.40) +
            min(docs_views * 0.10, 0.20) +
            min(pages_depth * 0.03, 0.15)
        )
        behavior_score = min(behavior_raw, 1.0) * 0.40

        # 2. FIRMOGRAPHIC (30%)
        email = traits.get("email", "") or traits.get("primary_email", "")
        company = traits.get("company", "")
        emp_size = traits.get("employee_count", 0) or traits.get("company_size", "")

        is_corp_domain = any(d in email.lower() for d in ["corp.com", "enterprise", "inc.com", "ltd.com", ".gov", ".edu", "tech.co"])
        is_free_domain = any(f in email.lower() for f in ["gmail.com", "yahoo.com", "hotmail.com", "outlook.com"])

        if is_corp_domain or (company and len(company) > 3):
            firmographic_raw = 1.0
        elif email and not is_free_domain and "@" in email:
            firmographic_raw = 0.70
        elif email:
            firmographic_raw = 0.30
        else:
            firmographic_raw = 0.0
        firmographic_score = firmographic_raw * 0.30

        # 3. ENGAGEMENT (20%)
        email_interactions = sum(1 for e in events if "email." in e.get("type", "").lower())
        form_submits = sum(1 for e in events if "form" in e.get("type", "").lower() or "identify" in e.get("type", "").lower())
        visit_events = len(events)
        engagement_raw = min((email_interactions * 0.30) + (form_submits * 0.40) + min(visit_events * 0.05, 0.30), 1.0)
        engagement_score = engagement_raw * 0.20

        # 4. SOURCE (10%)
        source = str(traits.get("source", "") or traits.get("utm_source", "")).lower()
        if source in ("direct", "referral", "linkedin", "organic_search", "google"):
            source_raw = 1.0
        elif source:
            source_raw = 0.60
        else:
            source_raw = 0.30
        source_score = source_raw * 0.10

        total = round(behavior_score + firmographic_score + engagement_score + source_score, 2)

        return ScoreBreakdown(
            total=total,
            behavior=round(behavior_score, 2),
            firmographic=round(firmographic_score, 2),
            engagement=round(engagement_score, 2),
            source=round(source_score, 2),
            details={
                "pricing_views": pricing_views,
                "demo_views": demo_views,
                "pages_depth": pages_depth,
                "is_corp_domain": is_corp_domain,
                "email_present": bool(email),
                "engagement_events": email_interactions + form_submits
            }
        )

    async def evaluate_and_record(
        self,
        db: AsyncSession,
        lead_id: str,
        events: List[Dict[str, Any]],
        traits: Dict[str, Any],
        session_summary: Optional[Dict[str, Any]] = None,
        triggered_by: str = "event"
    ) -> ScoreBreakdown:
        breakdown = self.compute_score(events, traits, session_summary)

        # Update current lead score
        lead_res = await db.execute(select(LeadModel).where(LeadModel.id == lead_id))
        lead = lead_res.scalar_one_or_none()
        if lead:
            lead.score = breakdown.total
            # Record trend in history table
            history = LeadScoreHistoryModel(
                id=f"sc_{uuid.uuid4().hex[:10]}",
                tenant_id=lead.tenant_id,
                lead_id=lead.id,
                total_score=breakdown.total,
                behavior_score=breakdown.behavior,
                firmographic_score=breakdown.firmographic,
                engagement_score=breakdown.engagement,
                source_score=breakdown.source,
                score_breakdown=breakdown.details,
                triggered_by=triggered_by,
                created_at=datetime.utcnow()
            )
            db.add(history)
            await db.commit()

        return breakdown

    async def get_score_history(self, db: AsyncSession, lead_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        stmt = select(LeadScoreHistoryModel).where(
            LeadScoreHistoryModel.lead_id == lead_id
        ).order_by(desc(LeadScoreHistoryModel.created_at)).limit(limit)
        res = await db.execute(stmt)
        return [
            {
                "score_id": r.id,
                "total_score": r.total_score,
                "behavior": r.behavior_score,
                "firmographic": r.firmographic_score,
                "engagement": r.engagement_score,
                "source": r.source_score,
                "breakdown": r.score_breakdown,
                "triggered_by": r.triggered_by,
                "created_at": r.created_at.isoformat()
            }
            for r in res.scalars().all()
        ]


class FunnelEngine:
    """
    Funnel Analysis Engine per NEXUS spec:
    - Analyzes multi-step conversions
    - Calculates drop-off and conversion rates
    - Detects 2-sigma conversion anomalies
    """

    def analyze_funnel(
        self,
        events: List[Dict[str, Any]],
        steps: List[str]
    ) -> Dict[str, Any]:
        if not steps:
            return {"steps": [], "overall_conversion_pct": 0.0}

        # Count occurrences per step in the event sequence
        step_counts = {}
        for step in steps:
            step_counts[step] = 0

        # Group events by session_id to measure session-level funnel completion
        sessions: Dict[str, List[str]] = {}
        for e in events:
            sid = e.get("session_id", "default")
            etype = e.get("type", "")
            data_path = str(e.get("data", {}).get("path", ""))
            
            # Map event to step definition
            for step in steps:
                if step in etype or step in data_path or (":" in step and step.split(":", 1)[1] in data_path):
                    sessions.setdefault(sid, []).append(step)

        # Calculate sequential funnel completion
        step_completions = [0] * len(steps)
        for sid, user_steps in sessions.items():
            current_step_idx = 0
            for step in steps:
                if step in user_steps:
                    step_completions[current_step_idx] += 1
                    current_step_idx += 1
                else:
                    break

        total_entries = step_completions[0] if step_completions else 0
        step_results = []
        for idx, step in enumerate(steps):
            count = step_completions[idx]
            prev_count = step_completions[idx - 1] if idx > 0 else count
            step_conv = (count / prev_count * 100.0) if prev_count > 0 else 0.0
            overall_conv = (count / total_entries * 100.0) if total_entries > 0 else 0.0
            drop_off_pct = round(100.0 - step_conv, 1) if idx > 0 else 0.0

            step_results.append({
                "step": step,
                "visitors_count": count,
                "step_conversion_pct": round(step_conv, 1),
                "overall_conversion_pct": round(overall_conv, 1),
                "drop_off_pct": drop_off_pct
            })

        overall_pct = (step_completions[-1] / total_entries * 100.0) if total_entries > 0 else 0.0

        # 2-Sigma Anomaly check against baseline (mock/baseline average 65%)
        baseline_rate = 65.0
        sigma = 10.0
        anomalies = []
        for res in step_results[1:]:
            if res["step_conversion_pct"] < (baseline_rate - (2 * sigma)):
                anomalies.append({
                    "step": res["step"],
                    "actual_conversion_pct": res["step_conversion_pct"],
                    "baseline_pct": baseline_rate,
                    "severity": "CRITICAL_DROP",
                    "message": f"Step '{res['step']}' conversion ({res['step_conversion_pct']}%) is >2 sigma below baseline."
                })

        return {
            "funnel_steps": step_results,
            "total_visitors": total_entries,
            "completed_visitors": step_completions[-1] if step_completions else 0,
            "overall_conversion_pct": round(overall_pct, 1),
            "anomalies_detected": anomalies
        }


class CohortEngine:
    """Cohort Analysis Engine per NEXUS spec."""

    def compute_cohorts(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Group actors into week cohorts based on their earliest event
        actor_first_seen: Dict[str, datetime] = {}
        actor_active_weeks: Dict[str, set] = {}

        for e in events:
            aid = e.get("actor_id") or e.get("actor", {}).get("id") or "anon"
            occurred_str = e.get("occurred_at")
            try:
                occurred = datetime.fromisoformat(occurred_str.replace("Z", "+00:00")) if occurred_str else datetime.utcnow()
            except Exception:
                occurred = datetime.utcnow()

            if aid not in actor_first_seen or occurred < actor_first_seen[aid]:
                actor_first_seen[aid] = occurred

            week_key = occurred.strftime("%Y-W%W")
            actor_active_weeks.setdefault(aid, set()).add(week_key)

        cohort_groups: Dict[str, List[str]] = {}
        for aid, first_dt in actor_first_seen.items():
            cohort_week = first_dt.strftime("%Y-W%W")
            cohort_groups.setdefault(cohort_week, []).append(aid)

        results = []
        for cohort_week, members in sorted(cohort_groups.items()):
            size = len(members)
            retention_w0 = size
            retention_w1 = sum(1 for m in members if len(actor_active_weeks.get(m, set())) > 1)
            results.append({
                "cohort_week": cohort_week,
                "cohort_size": size,
                "week_0_retention_pct": 100.0,
                "week_1_retention_pct": round((retention_w1 / size * 100.0), 1) if size > 0 else 0.0
            })

        return results


from nexus_analytics.outcomes import OutcomeTracker, OutcomeVerdict, StrategyStatus, OutcomeRecord
from nexus_analytics.experiments import (
    ExperimentationEngine,
    ExperimentDefinition,
    ExperimentVariant,
    ExperimentStatus
)
from nexus_analytics.nl_query import (
    AdvancedAnalyticsEngine,
    NLQueryRequest,
    NLQueryResponse
)

__all__ = [
    "ScoringEngine",
    "ScoreBreakdown",
    "FunnelEngine",
    "CohortEngine",
    "OutcomeTracker",
    "OutcomeVerdict",
    "StrategyStatus",
    "OutcomeRecord",
    "ExperimentationEngine",
    "ExperimentDefinition",
    "ExperimentVariant",
    "ExperimentStatus",
    "AdvancedAnalyticsEngine",
    "NLQueryRequest",
    "NLQueryResponse",
    "SecurityBaselineTracker",
    "PostureSnapshot"
]

from .security_baseline import SecurityBaselineTracker, PostureSnapshot
