"""
Cortex/apps/api/src/cortex_api/marketing_campaign_optimizer.py — Cortex Marketing Campaign Optimizer.

Campaign planning, channel allocation, ROI prediction, and
multi-channel optimization.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class CampaignPlan:
    """A marketing campaign plan."""
    plan_id: str
    name: str
    objective: str
    budget: float = 0.0
    channels: list[str] = field(default_factory=list)
    allocations: dict[str, float] = field(default_factory=dict)
    expected_roi: float = 0.0
    target_audience: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass
class ChannelPerformance:
    """Performance data for a marketing channel."""
    channel: str
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    ctr: float = 0.0
    roi: float = 0.0


@dataclass
class OptimizationResult:
    """Result of campaign optimization."""
    result_id: str
    plan: CampaignPlan
    optimized_allocations: dict[str, float] = field(default_factory=dict)
    projected_roi: float = 0.0
    improvements: list[str] = field(default_factory=list)


class MarketingCampaignOptimizer:
    """Engine for marketing campaign optimization."""

    def __init__(self) -> None:
        self._plans: dict[str, CampaignPlan] = {}
        self._channel_data: dict[str, ChannelPerformance] = {}
        self._optimizations: list[OptimizationResult] = []

    def create_plan(self, name: str, objective: str, budget: float,
                    target_audience: str = "", channels: list[str] | None = None) -> CampaignPlan:
        """Create a campaign plan."""
        plan_id = f"camp_{uuid.uuid4().hex[:12]}"
        channels = channels or ["email", "social", "search", "display"]
        plan = CampaignPlan(
            plan_id=plan_id, name=name, objective=objective, budget=budget,
            channels=channels, target_audience=target_audience,
        )
        # Default allocation
        equal_alloc = budget / len(channels)
        for ch in channels:
            plan.allocations[ch] = equal_alloc
        plan.expected_roi = 2.5
        self._plans[plan_id] = plan
        return plan

    def record_channel_performance(self, channel: str, spend: float, impressions: int,
                                   clicks: int, conversions: int) -> ChannelPerformance:
        """Record channel performance data."""
        perf = ChannelPerformance(
            channel=channel, spend=spend, impressions=impressions,
            clicks=clicks, conversions=conversions,
        )
        perf.ctr = clicks / max(1, impressions)
        perf.roi = (conversions * 10) / max(1, spend)
        self._channel_data[channel] = perf
        return perf

    def optimize_campaign(self, plan_id: str) -> OptimizationResult:
        """Optimize a campaign's budget allocation."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        result_id = f"opt_{uuid.uuid4().hex[:12]}"
        result = OptimizationResult(result_id=result_id, plan=plan)

        # Weight allocations by channel ROI
        total_roi = 0.0
        weights: dict[str, float] = {}
        for ch in plan.channels:
            perf = self._channel_data.get(ch)
            roi = perf.roi if perf else 1.0
            weights[ch] = roi
            total_roi += roi

        if total_roi > 0:
            for ch in plan.channels:
                result.optimized_allocations[ch] = plan.budget * (weights[ch] / total_roi)

        # Calculate projected ROI
        result.projected_roi = sum(
            self._channel_data.get(ch, ChannelPerformance(channel=ch)).roi * result.optimized_allocations.get(ch, 0)
            for ch in plan.channels
        ) / max(1, plan.budget)

        # Generate improvements
        for ch in plan.channels:
            perf = self._channel_data.get(ch)
            if perf and perf.roi > 2.0:
                result.improvements.append(f"Increase budget for {ch} (ROI: {perf.roi:.1f})")
            elif perf and perf.roi < 0.5:
                result.improvements.append(f"Decrease budget for {ch} (ROI: {perf.roi:.1f})")

        self._optimizations.append(result)
        return result

    def get_plan(self, plan_id: str) -> dict[str, Any]:
        """Get a campaign plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        return {
            "plan_id": plan.plan_id,
            "name": plan.name,
            "budget": plan.budget,
            "channels": plan.channels,
            "allocations": plan.allocations,
            "expected_roi": plan.expected_roi,
        }

    def get_report(self) -> dict[str, Any]:
        """Get engine report."""
        return {
            "total_plans": len(self._plans),
            "total_channels_tracked": len(self._channel_data),
            "total_optimizations": len(self._optimizations),
            "engine_status": "operational",
        }


engine = MarketingCampaignOptimizer()


@router.post("/cortex/campaigns/plans")
async def create_plan(name: str, objective: str, budget: float, target_audience: str = "",
                      channels: list[str] | None = None):
    """Create a marketing campaign plan."""
    plan = engine.create_plan(name, objective, budget, target_audience, channels)
    return {"plan_id": plan.plan_id, "channels": plan.channels, "budget": plan.budget}


@router.post("/cortex/campaigns/performance")
async def record_performance(channel: str, spend: float, impressions: int,
                             clicks: int, conversions: int):
    """Record channel performance."""
    perf = engine.record_channel_performance(channel, spend, impressions, clicks, conversions)
    return {"channel": channel, "ctr": perf.ctr, "roi": perf.roi}


@router.post("/cortex/campaigns/plans/{plan_id}/optimize")
async def optimize_campaign(plan_id: str):
    """Optimize a campaign."""
    result = engine.optimize_campaign(plan_id)
    return {
        "result_id": result.result_id,
        "optimized_allocations": result.optimized_allocations,
        "projected_roi": result.projected_roi,
        "improvements": result.improvements,
    }


@router.get("/cortex/campaigns/plans/{plan_id}")
async def get_plan(plan_id: str):
    """Get a campaign plan."""
    return engine.get_plan(plan_id)


@router.get("/cortex/campaigns/report")
async def campaign_report():
    """Get campaign optimizer report."""
    return engine.get_report()
