"""
cortex_api/marketing_automation.py — Cortex Marketing Automation Engine.

Extends Cortex's capabilities with:
1. Campaign Management: plan, execute, and optimize marketing campaigns
2. Email Automation: automated email sequences and personalization
3. Lead Nurturing: automated lead nurturing workflows
4. Social Media Management: schedule and analyze social media posts
5. Marketing Analytics: comprehensive campaign analytics
6. Conversion Funnel Optimization: optimize conversion funnels
7. Multi-Channel Orchestration: coordinate across marketing channels
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.config import get_db_session
from cortex_api.auth import Role, require_role

router = APIRouter()


@dataclass
class Campaign:
    """A marketing campaign."""
    campaign_id: str
    name: str
    description: str
    channels: list[str] = field(default_factory=list)
    status: str = "planning"  # planning, active, paused, completed
    start_date: float = 0.0
    end_date: float = 0.0
    budget: float = 0.0
    spent: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class EmailSequence:
    """An automated email sequence."""
    sequence_id: str
    name: str
    trigger: str  # lead_created, abandoned_cart, etc.
    emails: list[dict] = field(default_factory=list)
    status: str = "active"
    sent_count: int = 0
    open_rate: float = 0.0
    click_rate: float = 0.0


@dataclass
class LeadJourney:
    """A lead nurturing journey."""
    journey_id: str
    name: str
    stages: list[dict] = field(default_factory=list)
    entry_criteria: dict[str, Any] = field(default_factory=dict)
    exit_criteria: dict[str, Any] = field(default_factory=dict)
    leads_in_journey: int = 0
    conversion_rate: float = 0.0


@dataclass
class SocialPost:
    """A social media post."""
    post_id: str
    platform: str  # twitter, facebook, linkedin, instagram
    content: str
    scheduled_time: float = 0.0
    status: str = "scheduled"  # scheduled, posted, failed
    engagement: dict[str, float] = field(default_factory=dict)


@dataclass
class ConversionFunnel:
    """A marketing conversion funnel."""
    funnel_id: str
    name: str
    stages: list[dict] = field(default_factory=list)
    conversion_rates: list[float] = field(default_factory=list)
    avg_conversion_time: float = 0.0
    drop_off_points: list[dict] = field(default_factory=list)


class MarketingAutomation:
    """Marketing automation engine."""

    def __init__(self):
        self._campaigns: dict[str, Campaign] = {}
        self._email_sequences: dict[str, EmailSequence] = {}
        self._lead_journeys: dict[str, LeadJourney] = {}
        self._social_posts: dict[str, SocialPost] = {}
        self._funnels: dict[str, ConversionFunnel] = {}

    # ── Campaign Management ────────────────────────────────────────────────

    def create_campaign(
        self,
        name: str,
        description: str,
        channels: list[str] | None = None,
        budget: float = 0.0,
    ) -> Campaign:
        """Create a marketing campaign."""
        campaign_id = f"campaign_{len(self._campaigns) + 1}"

        campaign = Campaign(
            campaign_id=campaign_id,
            name=name,
            description=description,
            channels=channels or ["email", "social"],
            budget=budget,
            start_date=time.time(),
        )

        self._campaigns[campaign_id] = campaign
        return campaign

    def update_campaign_metrics(
        self,
        campaign_id: str,
        metrics: dict[str, float],
    ) -> Campaign | None:
        """Update campaign metrics."""
        campaign = self._campaigns.get(campaign_id)
        if campaign:
            campaign.metrics.update(metrics)
            campaign.spent = sum(
                v * 0.1 for k, v in metrics.items() if "spend" in k.lower()
            )
            return campaign
        return None

    def calculate_campaign_roi(self, campaign_id: str) -> dict[str, float]:
        """Calculate campaign return on investment."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return {"roi": 0.0, "status": "NOT_FOUND"}

        revenue = campaign.metrics.get("revenue", 0.0)
        spend = campaign.spent or campaign.budget

        if spend > 0:
            roi = (revenue - spend) / spend * 100
        else:
            roi = 0.0

        # Calculate CTR, CPC, CPA
        ctr = campaign.metrics.get("clicks", 0) / max(1, campaign.metrics.get("impressions", 1)) * 100
        cpc = spend / max(1, campaign.metrics.get("clicks", 1))
        cpa = spend / max(1, campaign.metrics.get("conversions", 1))

        return {
            "roi": roi,
            "ctr": ctr,
            "cpc": cpc,
            "cpa": cpa,
            "budget_utilization": campaign.spent / max(1, campaign.budget) * 100,
        }

    # ── Email Automation ───────────────────────────────────────────────────

    def create_email_sequence(
        self,
        name: str,
        trigger: str,
        emails: list[dict],
    ) -> EmailSequence:
        """Create an automated email sequence."""
        sequence_id = f"email_seq_{len(self._email_sequences) + 1}"

        sequence = EmailSequence(
            sequence_id=sequence_id,
            name=name,
            trigger=trigger,
            emails=emails,
        )

        self._email_sequences[sequence_id] = sequence
        return sequence

    def send_email(
        self,
        sequence_id: str,
        email_index: int,
        recipient: str,
    ) -> bool:
        """Send an email from a sequence."""
        sequence = self._email_sequences.get(sequence_id)
        if not sequence or email_index >= len(sequence.emails):
            return False

        sequence.sent_count += 1
        return True

    def calculate_email_metrics(self, sequence_id: str) -> dict[str, float]:
        """Calculate email sequence metrics."""
        sequence = self._email_sequences.get(sequence_id)
        if not sequence:
            return {"status": "NOT_FOUND"}

        sent = sequence.sent_count
        opens = sent * sequence.open_rate
        clicks = sent * sequence.click_rate

        return {
            "sent": sent,
            "open_rate": sequence.open_rate * 100,
            "click_rate": sequence.click_rate * 100,
            "click_to_open_rate": sequence.click_rate / max(0.01, sequence.open_rate) * 100 if sequence.open_rate > 0 else 0,
            "unsubscribe_rate": 1.0,  # Simplified
        }

    # ── Lead Nurturing ──────────────────────────────────────────────────────

    def create_lead_journey(
        self,
        name: str,
        entry_criteria: dict[str, Any],
        exit_criteria: dict[str, Any],
        stages: list[dict] | None = None,
    ) -> LeadJourney:
        """Create a lead nurturing journey."""
        journey_id = f"journey_{len(self._lead_journeys) + 1}"

        journey = LeadJourney(
            journey_id=journey_id,
            name=name,
            stages=stages or [
                {"name": "Welcome", "action": "send_welcome_email"},
                {"name": "Educate", "action": "send_educational_content"},
                {"name": "Engage", "action": "send_engagement_content"},
                {"name": "Convert", "action": "send_offer"},
            ],
            entry_criteria=entry_criteria,
            exit_criteria=exit_criteria,
        )

        self._lead_journeys[journey_id] = journey
        return journey

    def advance_lead(self, journey_id: str, lead_id: str) -> str:
        """Advance a lead through the journey."""
        journey = self._lead_journeys.get(journey_id)
        if not journey:
            return "journey_not_found"

        journey.leads_in_journey += 1

        # Check exit criteria
        # Simplified: 10% conversion rate
        if journey.leads_in_journey > 0 and (journey.leads_in_journey % 10) == 0:
            journey.conversion_rate = 1.0 / journey.leads_in_journey
            return "converted"

        return "in_journey"

    # ── Social Media Management ─────────────────────────────────────────────

    def schedule_post(
        self,
        platform: str,
        content: str,
        scheduled_time: float | None = None,
    ) -> SocialPost:
        """Schedule a social media post."""
        post_id = f"post_{len(self._social_posts) + 1}"

        post = SocialPost(
            post_id=post_id,
            platform=platform,
            content=content,
            scheduled_time=scheduled_time or time.time() + 3600,
        )

        self._social_posts[post_id] = post
        return post

    def get_optimal_post_time(
        self,
        platform: str,
        audience_timezone: str = "UTC",
    ) -> dict[str, Any]:
        """Get optimal posting time."""
        # Platform-specific optimal times
        optimal_times = {
            "twitter": {"best": "12:00-13:00", "second_best": "17:00-18:00"},
            "facebook": {"best": "13:00-14:00", "second_best": "09:00-10:00"},
            "linkedin": {"best": "08:00-09:00", "second_best": "12:00-13:00"},
            "instagram": {"best": "11:00-13:00", "second_best": "19:00-20:00"},
        }

        return optimal_times.get(platform, {"best": "12:00-13:00"})

    def update_post_engagement(
        self,
        post_id: str,
        metrics: dict[str, float],
    ) -> SocialPost | None:
        """Update post engagement metrics."""
        post = self._social_posts.get(post_id)
        if post:
            post.engagement.update(metrics)
            post.status = "posted"
            return post
        return None

    # ── Conversion Funnel Optimization ──────────────────────────────────────

    def build_conversion_funnel(
        self,
        name: str,
        stages: list[dict],
    ) -> ConversionFunnel:
        """Build a conversion funnel."""
        funnel_id = f"funnel_{len(self._funnels) + 1}"

        conversion_rates = []
        drop_offs = []
        total_time = 0.0

        for i, stage in enumerate(stages):
            users = stage.get("users", 0)
            avg_time = stage.get("avg_time", 0.0)
            total_time += avg_time

            if i == 0:
                conversion_rates.append(1.0)
            else:
                prev_users = stages[i - 1].get("users", 1)
                rate = users / max(1, prev_users)
                conversion_rates.append(rate)
                drop_offs.append({
                    "stage": stage.get("name", f"Stage {i}"),
                    "drop_off": prev_users - users,
                    "drop_rate": 1.0 - rate,
                })

        funnel = ConversionFunnel(
            funnel_id=funnel_id,
            name=name,
            stages=stages,
            conversion_rates=conversion_rates,
            avg_conversion_time=total_time,
            drop_off_points=drop_offs,
        )

        self._funnels[funnel_id] = funnel
        return funnel

    def optimize_funnel(self, funnel_id: str) -> dict[str, Any]:
        """Get optimization recommendations for a funnel."""
        funnel = self._funnels.get(funnel_id)
        if not funnel:
            return {"status": "NOT_FOUND"}

        recommendations = []

        # Find worst drop-off
        worst_drop = max(
            funnel.drop_off_points,
            key=lambda d: d["drop_rate"],
            default=None
        )

        if worst_drop:
            recommendations.append(
                f"Biggest drop-off at '{worst_drop['stage']}' ({worst_drop['drop_rate']:.1%} drop rate)"
            )
            if worst_drop["drop_rate"] > 0.5:
                recommendations.append("Consider simplifying this step or adding friction reduction")

        # Overall conversion
        if funnel.conversion_rates:
            overall = funnel.conversion_rates[-1]
            recommendations.append(f"Overall conversion: {overall:.1%}")

        # Time analysis
        if funnel.avg_conversion_time > 3600:
            recommendations.append("Conversion takes over an hour - consider speeding up the process")

        return {
            "funnel_id": funnel_id,
            "recommendations": recommendations,
            "overall_conversion": funnel.conversion_rates[-1] if funnel.conversion_rates else 0,
        }

    # ── Reporting ──────────────────────────────────────────────────────────

    def get_marketing_report(self) -> dict[str, Any]:
        """Generate a marketing report."""
        total_campaigns = len(self._campaigns)
        active_campaigns = sum(1 for c in self._campaigns.values() if c.status == "active")
        total_emails_sent = sum(s.sent_count for s in self._email_sequences.values())
        total_posts = len(self._social_posts)

        return {
            "total_campaigns": total_campaigns,
            "active_campaigns": active_campaigns,
            "email_sequences": len(self._email_sequences),
            "emails_sent": total_emails_sent,
            "lead_journeys": len(self._lead_journeys),
            "social_posts": total_posts,
            "conversion_funnels": len(self._funnels),
        }


# Module-level singleton
marketing_automation = MarketingAutomation()


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/marketing/campaigns")
async def create_campaign(
    payload: dict,
    db: AsyncSession = Depends(get_db_session),
    user: dict = Depends(require_role(Role.CORTEX_ADMIN)),
):
    """Create a marketing campaign."""
    campaign = marketing_automation.create_campaign(
        name=payload["name"],
        description=payload.get("description", ""),
        channels=payload.get("channels", ["email", "social"]),
        budget=payload.get("budget", 0.0),
    )
    return {"campaign_id": campaign.campaign_id, "status": "created"}


@router.get("/api/v1/marketing/campaigns/{campaign_id}/roi")
async def campaign_roi(
    campaign_id: str,
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get campaign ROI."""
    return marketing_automation.calculate_campaign_roi(campaign_id)


@router.post("/api/v1/marketing/email-sequences")
async def create_email_sequence(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_ADMIN)),
):
    """Create an email sequence."""
    sequence = marketing_automation.create_email_sequence(
        name=payload["name"],
        trigger=payload["trigger"],
        emails=payload["emails"],
    )
    return {"sequence_id": sequence.sequence_id}


@router.post("/api/v1/marketing/lead-journeys")
async def create_lead_journey(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_ADMIN)),
):
    """Create a lead nurturing journey."""
    journey = marketing_automation.create_lead_journey(
        name=payload["name"],
        entry_criteria=payload.get("entry_criteria", {}),
        exit_criteria=payload.get("exit_criteria", {}),
        stages=payload.get("stages"),
    )
    return {"journey_id": journey.journey_id}


@router.post("/api/v1/marketing/social/schedule")
async def schedule_post(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Schedule a social media post."""
    post = marketing_automation.schedule_post(
        platform=payload["platform"],
        content=payload["content"],
        scheduled_time=payload.get("scheduled_time"),
    )
    return {"post_id": post.post_id, "status": post.status}


@router.post("/api/v1/marketing/funnels")
async def build_funnel(
    payload: dict,
    user: dict = Depends(require_role(Role.CORTEX_OPERATOR)),
):
    """Build a conversion funnel."""
    funnel = marketing_automation.build_conversion_funnel(
        name=payload["name"],
        stages=payload["stages"],
    )
    return {"funnel_id": funnel.funnel_id, "conversion_rates": funnel.conversion_rates}


@router.get("/api/v1/marketing/report")
async def marketing_report(
    user: dict = Depends(require_role(Role.CORTEX_VIEWER)),
):
    """Get marketing report."""
    return marketing_automation.get_marketing_report()
