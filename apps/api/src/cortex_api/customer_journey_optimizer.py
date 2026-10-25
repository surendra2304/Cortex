"""
Cortex/apps/api/src/cortex_api/customer_journey_optimizer.py — Cortex Customer Journey Optimizer.

Extends Cortex's capabilities with:
1. Journey Mapping: map customer journey stages
2. Drop-off Analysis: identify where customers drop off
3. Journey Personalization: personalize journeys per segment
4. Conversion Path Optimization: optimize conversion paths
5. Micro-Moment Detection: detect key micro-moments
6. Journey Automation: automate journey steps
7. Customer Lifetime Value Prediction: predict CLV
8. Churn Prediction and Prevention: predict and prevent churn
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class JourneyStage:
    """A customer journey stage."""
    stage: str  # awareness, consideration, conversion, retention, advocacy
    metric: str
    current_rate: float
    target_rate: float
    dropoff: float
    improvements: list[str] = field(default_factory=list)


@dataclass
class DropoffPoint:
    """A drop-off point in the journey."""
    stage: str
    from_stage: str
    to_stage: str
    dropoff_rate: float
    reason: str
    impact: float
    fix_priority: str  # high, medium, low


@dataclass
class CustomerSegment:
    """A customer segment for journey personalization."""
    segment_id: str
    name: str
    criteria: str
    size: int = 0
    conversion_rate: float = 0.0
    avg_value: float = 0.0
    journey_stage: str = "awareness"
    recommended_actions: list[str] = field(default_factory=list)


@dataclass
class MicroMoment:
    """A customer micro-moment."""
    moment_id: str
    trigger: str
    action: str
    emotion: str
    context: str
    conversion_prob: float = 0.0
    recommended_response: str = ""


@dataclass
class ConversionPath:
    """A conversion path."""
    path_id: str
    steps: list[str]
    conversion_rate: float
    avg_time_to_convert: float
    dropoff_points: list[str]
    recommended_optimizations: list[str] = field(default_factory=list)


@dataclass
class CLVPrediction:
    """Customer Lifetime Value prediction."""
    segment: str
    clv: float
    churn_prob: float
    retention_rate: float
    recommended_spend: float
    rOI: float
    timeline: str = ""


@dataclass
class ChurnPrediction:
    """Churn prediction."""
    customer_id: str
    churn_probability: float
    risk_factors: list[str]
    health_score: float
    recommended_actions: list[str]
    time_to_churn: str


@dataclass
class JourneyReport:
    """Customer journey report."""
    total_customers: int
    journey_completion_rate: float
    avg_time_to_conversion: float
    top_dropoff: str
    estimated_revenue_impact: float
    recommendations: list[str]


class CustomerJourneyOptimizer:
    """Customer journey optimization engine."""

    def __init__(self):
        self._journeys: dict[str, list[JourneyStage]] = {}
        self._segments: dict[str, CustomerSegment] = {}
        self._micro_moments: list[MicroMoment] = []
        self._paths: dict[str, ConversionPath] = {}
        self._churn_predictions: dict[str, ChurnPrediction] = {}

    # ── Journey Mapping ───────────────────────────────────────────────────

    def map_journey(
        self,
        customer_id: str,
        stages: list[dict],
    ) -> list[JourneyStage]:
        """Map a customer's journey."""
        journey = []
        for stage in stages:
            current = stage.get("current_rate", 0.0)
            target = stage.get("target_rate", 1.0)
            dropoff = 1.0 - current / max(0.001, target)

            improvements = []
            if dropoff > 0.3:
                improvements.append(f"Improve {stage['stage']} conversion")

            journey.append(JourneyStage(
                stage=stage["stage"],
                metric=stage.get("metric", stage["stage"]),
                current_rate=current,
                target_rate=target,
                dropoff=dropoff,
                improvements=improvements,
            ))

        self._journeys[customer_id] = journey
        return journey

    # ── Drop-off Analysis ────────────────────────────────────────────────

    def analyze_dropoffs(
        self,
        journeys: list[list[JourneyStage]],
    ) -> list[DropoffPoint]:
        """Analyze drop-off points across journeys."""
        dropoffs = []

        for journey in journeys:
            for i in range(1, len(journey)):
                prev = journey[i-1]
                curr = journey[i]

                dropoff_rate = 1.0 - curr.current_rate / max(0.001, prev.current_rate)

                if dropoff_rate > 0.2:
                    # Determine reason
                    reason = self._identify_dropoff_reason(prev, curr)

                    # Impact
                    impact = dropoff_rate * 100

                    # Fix priority
                    if dropoff_rate > 0.5:
                        pri = "high"
                    elif dropoff_rate > 0.3:
                        pri = "medium"
                    else:
                        pri = "low"

                    dropoffs.append(DropoffPoint(
                        stage=curr.stage,
                        from_stage=prev.stage,
                        to_stage=curr.stage,
                        dropoff_rate=dropoff_rate,
                        reason=reason,
                        impact=impact,
                        fix_priority=pri,
                    ))

        # Sort by impact
        dropoffs.sort(key=lambda d: -d.impact)
        return dropoffs

    def _identify_dropoff_reason(self, prev: JourneyStage, curr: JourneyStage) -> str:
        """Identify why a customer dropped off."""
        reasons = {
            "awareness": "Low brand awareness, insufficient reach",
            "consideration": "Lack of compelling value proposition",
            "conversion": "Friction in checkout/signup process",
            "retention": "Poor onboarding or engagement",
            "advocacy": "Insufficient incentive or community",
        }
        return reasons.get(curr.stage, "Unknown reason")

    # ── Journey Personalization ─────────────────────────────────────────

    def personalize_journey(
        self,
        segment: dict,
    ) -> CustomerSegment:
        """Personalize journey for a customer segment."""
        seg = CustomerSegment(
            segment_id=hashlib.md5(f"seg:{segment['name']}:{time.time()}".encode()).hexdigest()[:12],
            name=segment["name"],
            criteria=segment.get("criteria", ""),
            size=segment.get("size", 0),
            conversion_rate=segment.get("conversion_rate", 0.0),
            avg_value=segment.get("avg_value", 0.0),
            journey_stage=segment.get("journey_stage", "awareness"),
        )

        # Generate recommended actions based on segment
        if seg.journey_stage == "awareness":
            seg.recommended_actions = ["Expand reach", "Improve content", "Leverage social proof"]
        elif seg.journey_stage == "consideration":
            seg.recommended_actions = ["Offer demo", "Provide case studies", "Comparison content"]
        elif seg.journey_stage == "conversion":
            seg.recommended_actions = ["Simplify checkout", "Offer discount", "Reduce friction"]
        elif seg.journey_stage == "retention":
            seg.recommended_actions = ["Improve onboarding", "Regular engagement", "Value reinforcement"]
        else:
            seg.recommended_actions = ["Referral program", "Community building", "Advocacy incentives"]

        self._segments[seg.segment_id] = seg
        return seg

    # ── Conversion Path Optimization ─────────────────────────────────────

    def optimize_conversion_paths(
        self,
        path_data: list[dict],
    ) -> list[ConversionPath]:
        """Optimize conversion paths."""
        paths = []

        for pd in path_data:
            steps = pd.get("steps", [])
            conversion_rate = pd.get("conversion_rate", 0.0)
            avg_time = pd.get("avg_time_to_convert", 0.0)

            # Identify dropoff points
            dropoffs = []
            for i in range(1, len(steps)):
                prev_conv = pd.get(f"step_{steps[i-1]}_conversion", 0.9)
                curr_conv = pd.get(f"step_{steps[i]}_conversion", 0.9)
                if curr_conv < prev_conv * 0.7:
                    dropoffs.append(steps[i])

            # Recommendations
            recommendations = []
            if dropoffs:
                recommendations.append(f"Focus on reducing dropoff at: {', '.join(dropoffs[:3])}")
            if conversion_rate < 0.05:
                recommendations.append("Simplify conversion process")
            if avg_time > 7 * 86400:  # 7 days
                recommendations.append("Reduce time to conversion")

            path = ConversionPath(
                path_id=hashlib.md5(f"path:{steps}:{time.time()}".encode()).hexdigest()[:12],
                steps=steps,
                conversion_rate=conversion_rate,
                avg_time_to_convert=avg_time,
                dropoff_points=dropoffs,
                recommended_optimizations=recommendations,
            )

            self._paths[path.path_id] = path
            paths.append(path)

        return paths

    # ── Micro-Moment Detection ───────────────────────────────────────────

    def detect_micro_moments(
        self,
        customer_data: dict,
    ) -> list[MicroMoment]:
        """Detect customer micro-moments."""
        moments = []

        triggers = {
            "first_visit": {"action": "explore", "emotion": "curious", "context": "first interaction"},
            "repeat_visit": {"action": "engage", "emotion": "interested", "context": "returning"},
            "view_price": {"action": "compare", "emotion": "considering", "context": "evaluating"},
            "abandoned_cart": {"action": "recover", "emotion": "hesitant", "context": "cart abandoned"},
            "view_checkout": {"action": "convert", "emotion": "ready", "context": "checkout page"},
            "repeat_purchase": {"action": "retain", "emotion": "loyal", "context": "repeat customer"},
            "share_content": {"action": "advocate", "emotion": "enthusiastic", "context": "sharing"},
        }

        for trigger, data in triggers.items():
            if customer_data.get(trigger, False):
                conv_prob = {
                    "first_visit": 0.05,
                    "repeat_visit": 0.15,
                    "view_price": 0.30,
                    "abandoned_cart": 0.25,
                    "view_checkout": 0.60,
                    "repeat_purchase": 0.80,
                    "share_content": 0.90,
                }.get(trigger, 0.1)

                response = self._recommend_response(trigger)

                moment = MicroMoment(
                    moment_id=hashlib.md5(f"moment:{trigger}:{time.time()}".encode()).hexdigest()[:12],
                    trigger=trigger,
                    action=data["action"],
                    emotion=data["emotion"],
                    context=data["context"],
                    conversion_prob=conv_prob,
                    recommended_response=response,
                )

                moments.append(moment)

        self._micro_moments.extend(moments)
        return moments

    def _recommend_response(self, trigger: str) -> str:
        responses = {
            "first_visit": "Welcome message with key value proposition",
            "repeat_visit": "Personalized recommendations based on history",
            "view_price": "Show social proof, financing options",
            "abandoned_cart": "Send reminder with limited-time discount",
            "view_checkout": "Simplify checkout, offer express pay",
            "repeat_purchase": "Loyalty reward, cross-sell relevant products",
            "share_content": "Thank you + referral incentive",
        }
        return responses.get(trigger, "Generic engagement prompt")

    # ── Customer Lifetime Value Prediction ───────────────────────────────

    def predict_clv(
        self,
        segment: str,
        avg_order_value: float,
        purchase_frequency: float,
        churn_rate: float,
    ) -> CLVPrediction:
        """Predict Customer Lifetime Value."""
        # CLV = (Avg Order Value × Purchase Frequency) / Churn Rate
        clv = (avg_order_value * purchase_frequency) / max(0.001, churn_rate)

        retention = 1.0 - churn_rate
        rOI = clv * retention / max(1, avg_order_value)

        # Recommended marketing spend
        spend = clv * 0.1  # 10% of CLV

        timeline = (
            "High value, invest aggressively" if clv > 1000 else
            "Medium value, moderate investment" if clv > 100 else
            "Low value, maintain efficiently"
        )

        return CLVPrediction(
            segment=segment,
            clv=clv,
            churn_prob=churn_rate,
            retention_rate=retention,
            recommended_spend=spend,
            rOI=rOI,
            timeline=timeline,
        )

    # ── Churn Prediction and Prevention ─────────────────────────────────

    def predict_churn(
        self,
        customer_id: str,
        engagement_score: float,
        days_since_last_activity: int,
        purchase_count: int,
        support_tickets: int,
    ) -> ChurnPrediction:
        """Predict customer churn."""
        # Calculate churn probability
        churn_prob = 0.0

        if engagement_score < 0.2:
            churn_prob += 0.3
        elif engagement_score < 0.4:
            churn_prob += 0.15

        if days_since_last_activity > 30:
            churn_prob += 0.3
        elif days_since_last_activity > 14:
            churn_prob += 0.15

        if purchase_count < 2:
            churn_prob += 0.2

        if support_tickets > 3:
            churn_prob += 0.15

        churn_prob = min(1.0, churn_prob)

        # Health score
        health_score = 1.0 - churn_prob

        # Risk factors
        risk_factors = []
        if engagement_score < 0.3:
            risk_factors.append("Low engagement")
        if days_since_last_activity > 14:
            risk_factors.append("Inactive for extended period")
        if purchase_count < 2:
            risk_factors.append("Low purchase history")
        if support_tickets > 3:
            risk_factors.append("High support ticket volume")

        # Recommended actions
        actions = []
        if churn_prob > 0.5:
            actions = ["Immediate outreach", "Personalized discount", "Dedicated support"]
        elif churn_prob > 0.3:
            actions = ["Re-engagement email", "Content recommendation", "Special offer"]
        else:
            actions = ["Maintain engagement", "Cross-sell relevant products"]

        # Time to churn
        if churn_prob > 0.7:
            tt_churn = "7 days"
        elif churn_prob > 0.4:
            tt_churn = "30 days"
        else:
            tt_churn = "60+ days"

        prediction = ChurnPrediction(
            customer_id=customer_id,
            churn_probability=churn_prob,
            risk_factors=risk_factors,
            health_score=health_score,
            recommended_actions=actions,
            time_to_churn=tt_churn,
        )

        self._churn_predictions[customer_id] = prediction
        return prediction

    # ── Journey Automation ────────────────────────────────────────────────

    def automate_journey(
        self,
        customer_id: str,
        current_stage: str,
        next_stage: str,
    ) -> dict:
        """Automate a journey step."""
        automation_map = {
            ("awareness", "consideration"): {
                "action": "send_demo_email",
                "trigger": "viewed_pricing",
                "content": "demo request",
            },
            ("consideration", "conversion"): {
                "action": "offer_discount",
                "trigger": "abandoned_cart",
                "content": "10% off limited time",
            },
            ("conversion", "retention"): {
                "action": "onboarding_sequence",
                "trigger": "purchase_completed",
                "content": "welcome + setup guide",
            },
            ("retention", "advocacy"): {
                "action": "referral_program",
                "trigger": "repeat_purchase",
                "content": "referral reward",
            },
        }

        key = (current_stage, next_stage)
        automation = automation_map.get(key, {
            "action": "generic_engagement",
            "trigger": "stage_change",
            "content": "engagement message",
        })

        return {
            "customer_id": customer_id,
            "from_stage": current_stage,
            "to_stage": next_stage,
            "automation": automation,
            "status": "queued",
        }

    # ── Reporting ────────────────────────────────────────────────────────

    def generate_journey_report(
        self,
        journeys: list[list[JourneyStage]],
    ) -> JourneyReport:
        """Generate customer journey report."""
        if not journeys:
            return JourneyReport(
                total_customers=0,
                journey_completion_rate=0.0,
                avg_time_to_conversion=0.0,
                top_dropoff="none",
                estimated_revenue_impact=0.0,
                recommendations=["Collect journey data first"],
            )

        # Calculate metrics
        total_customers = len(journeys)
        completed = sum(
            1 for j in journeys
            if j and j[-1].stage == "advocacy"
        )
        completion_rate = completed / total_customers

        # Top dropoff
        dropoffs = self.analyze_dropoffs(journeys)
        top_dropoff = dropoffs[0].stage if dropoffs else "none"

        # Revenue impact
        revenue_impact = sum(d.impact * 100 for d in dropoffs[:3])

        # Recommendations
        recommendations = []
        for d in dropoffs[:5]:
            if d.fix_priority == "high":
                recommendations.append(f"Fix high-impact dropoff at {d.stage} ({d.dropoff_rate:.0%})")

        return JourneyReport(
            total_customers=total_customers,
            journey_completion_rate=completion_rate,
            avg_time_to_conversion=7.0,
            top_dropoff=top_dropoff,
            estimated_revenue_impact=revenue_impact,
            recommendations=recommendations,
        )


# ── API Routes ──────────────────────────────────────────────────────────────

journey_optimizer = CustomerJourneyOptimizer()


@router.post("/api/v1/journey/map")
async def map_journey(payload: dict):
    """Map customer journey."""
    journey = journey_optimizer.map_journey(
        customer_id=payload["customer_id"],
        stages=payload["stages"],
    )
    return [s.__dict__ for s in journey]


@router.post("/api/v1/journey/dropoffs")
async def analyze_dropoffs(payload: dict):
    """Analyze drop-offs."""
    journeys = [
        journey_optimizer.map_journey(cid, stages)
        for cid, stages in payload["journeys"].items()
    ]
    dropoffs = journey_optimizer.analyze_dropoffs(journeys)
    return [d.__dict__ for d in dropoffs]


@router.post("/api/v1/journey/personalize")
async def personalize_journey(payload: dict):
    """Personalize journey for segment."""
    seg = journey_optimizer.personalize_journey(payload["segment"])
    return seg.__dict__


@router.post("/api/v1/journey/conversion_paths")
async def optimize_conversion_paths(payload: dict):
    """Optimize conversion paths."""
    paths = journey_optimizer.optimize_conversion_paths(payload["path_data"])
    return [p.__dict__ for p in paths]


@router.post("/api/v1/journey/micro_moments")
async def detect_micro_moments(payload: dict):
    """Detect micro-moments."""
    moments = journey_optimizer.detect_micro_moments(payload["customer_data"])
    return [m.__dict__ for m in moments]


@router.post("/api/v1/journey/clv")
async def predict_clv(payload: dict):
    """Predict CLV."""
    result = journey_optimizer.predict_clv(
        segment=payload["segment"],
        avg_order_value=payload["avg_order_value"],
        purchase_frequency=payload["purchase_frequency"],
        churn_rate=payload["churn_rate"],
    )
    return result.__dict__


@router.post("/api/v1/journey/churn")
async def predict_churn(payload: dict):
    """Predict churn."""
    result = journey_optimizer.predict_churn(
        customer_id=payload["customer_id"],
        engagement_score=payload["engagement_score"],
        days_since_last_activity=payload["days_since_last_activity"],
        purchase_count=payload["purchase_count"],
        support_tickets=payload["support_tickets"],
    )
    return result.__dict__


@router.post("/api/v1/journey/automate")
async def automate_journey(payload: dict):
    """Automate journey step."""
    return journey_optimizer.automate_journey(
        payload["customer_id"],
        payload["current_stage"],
        payload["next_stage"],
    )


@router.post("/api/v1/journey/report")
async def generate_journey_report(payload: dict):
    """Generate journey report."""
    journeys = [
        journey_optimizer.map_journey(cid, stages)
        for cid, stages in payload["journeys"].items()
    ]
    report = journey_optimizer.generate_journey_report(journeys)
    return report.__dict__
