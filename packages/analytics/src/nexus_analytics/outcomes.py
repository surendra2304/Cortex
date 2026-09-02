from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
from pydantic import BaseModel, Field
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from cortex_api.db_models import StrategyPerformanceModel

logger = logging.getLogger("cortex-outcome-tracker")


class OutcomeVerdict(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILURE = "FAILURE"
    NO_EFFECT = "NO_EFFECT"


class StrategyStatus(str, Enum):
    PROVEN = "PROVEN"
    PROBATION = "PROBATION"
    DEMOTED = "DEMOTED"


class OutcomeRecord(BaseModel):
    id: str
    action_id: str
    workflow_run_id: Optional[str] = None
    strategy_key: str
    action_type: str
    target: str
    context_snapshot: Dict[str, Any] = Field(default_factory=dict)
    outcome_events: List[Dict[str, Any]] = Field(default_factory=list)
    verdict: OutcomeVerdict = OutcomeVerdict.NO_EFFECT
    lift_pct: float = 0.0
    measured_at: datetime = Field(default_factory=datetime.utcnow)


class OutcomeTracker:
    """
    Closed-Loop Outcome Measurement & Strategy Learning per CORTEX spec section 21:
    - Tracks downstream events attributable to actions
    - Promotes strategies with >60% success (PROVEN)
    - Demotes strategies with <30% success (DEMOTED)
    - Informs agents of strategy performance before action proposals
    """

    def evaluate_verdict(
        self,
        action_type: str,
        downstream_events: List[Dict[str, Any]]
    ) -> OutcomeVerdict:
        if not downstream_events:
            return OutcomeVerdict.NO_EFFECT

        event_types = [str(e.get("type", "")).lower() for e in downstream_events]

        if "banner" in action_type:
            if any("checkout.completed" in t or "purchase" in t or "convert" in t for t in event_types):
                return OutcomeVerdict.SUCCESS
            if any("click" in t or "cta" in t or "view" in t for t in event_types):
                return OutcomeVerdict.PARTIAL
            return OutcomeVerdict.FAILURE

        if "email" in action_type or "dispatch" in action_type or "send" in action_type:
            if any("repli" in t or "reply" in t or "convert" in t or "response" in t for t in event_types):
                return OutcomeVerdict.SUCCESS
            if any("open" in t or "click" in t or "deliver" in t for t in event_types):
                return OutcomeVerdict.PARTIAL
            return OutcomeVerdict.FAILURE

        if any("completed" in t or "success" in t or "verified" in t for t in event_types):
            return OutcomeVerdict.SUCCESS

        return OutcomeVerdict.PARTIAL

    async def record_and_update_strategy(
        self,
        db: Optional[AsyncSession],
        strategy_key: str,
        action_type: str,
        action_id: str,
        downstream_events: List[Dict[str, Any]],
        tenant_id: str = "default",
        workflow_run_id: Optional[str] = None
    ) -> StrategyStatus:
        verdict = self.evaluate_verdict(action_type, downstream_events)
        is_success = verdict in (OutcomeVerdict.SUCCESS, OutcomeVerdict.PARTIAL)

        if not db:
            return StrategyStatus.PROBATION

        try:
            stmt = select(StrategyPerformanceModel).where(
                StrategyPerformanceModel.tenant_id == tenant_id,
                StrategyPerformanceModel.strategy_key == strategy_key
            )
            res = await db.execute(stmt)
            strat = res.scalar_one_or_none()

            if not strat:
                strat = StrategyPerformanceModel(
                    id=f"strat_{uuid.uuid4().hex[:10]}",
                    tenant_id=tenant_id,
                    strategy_key=strategy_key,
                    status=StrategyStatus.PROBATION.value,
                    total_executions=0,
                    successes=0,
                    failures=0,
                    success_rate=0.0,
                    confidence=0.1,
                    recent_outcomes=[],
                    last_updated_at=datetime.utcnow()
                )
                db.add(strat)

            strat.total_executions += 1
            if is_success:
                strat.successes += 1
            else:
                strat.failures += 1

            strat.success_rate = round(strat.successes / strat.total_executions, 2)
            strat.confidence = round(min(strat.total_executions / 20.0, 1.0), 2)

            recent = list(strat.recent_outcomes or [])
            recent.append({"action_id": action_id, "verdict": verdict.value, "time": datetime.utcnow().isoformat()})
            strat.recent_outcomes = recent[-20:]
            strat.last_updated_at = datetime.utcnow()

            # Spec Rule: Auto-promote if > 60% over n>=20; Auto-demote if < 30% over n>=10
            if strat.total_executions >= 20 and strat.success_rate >= 0.60:
                strat.status = StrategyStatus.PROVEN.value
            elif strat.total_executions >= 10 and strat.success_rate < 0.30:
                strat.status = StrategyStatus.DEMOTED.value
                logger.warning(f"STRATEGY DEMOTED: '{strategy_key}' success rate fell to {strat.success_rate*100}%.")
            else:
                strat.status = StrategyStatus.PROBATION.value

            await db.commit()
            return StrategyStatus(strat.status)

        except Exception as exc:
            logger.error(f"Strategy performance update failed: {exc}")
            if db:
                await db.rollback()
            return StrategyStatus.PROBATION

    async def get_strategy_performance(
        self,
        db: AsyncSession,
        tenant_id: str = "default"
    ) -> List[Dict[str, Any]]:
        stmt = select(StrategyPerformanceModel).where(
            StrategyPerformanceModel.tenant_id == tenant_id
        ).order_by(desc(StrategyPerformanceModel.success_rate))
        res = await db.execute(stmt)
        return [
            {
                "strategy_key": s.strategy_key,
                "status": s.status,
                "total_executions": s.total_executions,
                "success_rate_pct": round(s.success_rate * 100, 1),
                "confidence": s.confidence,
                "recent_outcomes": s.recent_outcomes
            }
            for s in res.scalars().all()
        ]
