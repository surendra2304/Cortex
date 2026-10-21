"""
Funnel Engine & Multi-Goal Conversion Tracker for Cortex.

Implements pre-configured conversion funnels and optimization goals for the FRIDAY Universe:
- Option A: Enterprise Demo / Meeting Bookings (demo_request_submitted)
- Option B: Paid SaaS Subscriptions (checkout_completed)
- Option C: Community / User Waitlist Signups (signup_completed)
- Option D: Full 10-Agent Mesh Multi-Step Journey (landing -> agents -> pricing -> checkout)
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from cortex_intelligence.bandit_allocator import (
    BanditAlgorithm,
    global_bandit_engine,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(dt_val: Any) -> datetime:
    if isinstance(dt_val, datetime):
        return dt_val if dt_val.tzinfo else dt_val.replace(tzinfo=UTC)
    if isinstance(dt_val, str):
        try:
            cleaned = dt_val.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return _utcnow()
    return _utcnow()


class FridayConversionGoalType(str, Enum):
    DEMO_BOOKING = "demo_request_submitted"
    PAID_SUBSCRIPTION = "checkout_completed"
    WAITLIST_SIGNUP = "signup_completed"
    MULTI_STEP_JOURNEY = "universe_multi_step_journey"


class FunnelStep(BaseModel):
    step_id: str
    name: str
    step_index: int
    target_path: str
    required_event_type: str
    description: str = ""


class FunnelDefinition(BaseModel):
    funnel_id: str
    name: str
    description: str
    target_site_id: str = "site_friday_universe"
    steps: list[FunnelStep]
    primary_goal: FridayConversionGoalType
    created_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class StepMetric(BaseModel):
    step_id: str
    name: str
    step_index: int
    visitors_reached: int
    conversion_from_previous_pct: float
    drop_off_count: int
    drop_off_pct: float
    median_seconds_from_entry: float = 0.0


class FunnelAnalysisReport(BaseModel):
    funnel_id: str
    name: str
    total_sessions_analyzed: int
    completed_sessions: int
    overall_conversion_rate_pct: float
    steps: list[StepMetric]
    drop_off_hotspots: list[dict[str, Any]]
    analyzed_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class FridayUniverseFunnelManager:
    """
    Manages pre-configured funnels and MAB experiment integration for Friday Universe.
    """

    def __init__(self) -> None:
        self._funnels: dict[str, FunnelDefinition] = {}
        self._seed_friday_universe_funnels()

    def _seed_friday_universe_funnels(self) -> None:
        # ── Option A: Enterprise Demo / Meeting Booking Funnel ──────────────────
        self.register_funnel(
            FunnelDefinition(
                funnel_id="funnel_enterprise_demo",
                name="Enterprise Demo & Meeting Booking",
                description="Tracks high-intent visitors requesting an executive 1:1 demo with the agent architecture team.",
                primary_goal=FridayConversionGoalType.DEMO_BOOKING,
                steps=[
                    FunnelStep(
                        step_id="step_landing",
                        name="Portal Landing Page",
                        step_index=0,
                        target_path="/",
                        required_event_type="page_view",
                    ),
                    FunnelStep(
                        step_id="step_demo_view",
                        name="Demo Request Modal Opened",
                        step_index=1,
                        target_path="/demo",
                        required_event_type="demo_modal_open",
                    ),
                    FunnelStep(
                        step_id="step_demo_submitted",
                        name="Enterprise Demo Booked",
                        step_index=2,
                        target_path="/demo/confirmed",
                        required_event_type=FridayConversionGoalType.DEMO_BOOKING.value,
                    ),
                ],
            )
        )

        # ── Option B: Paid SaaS Subscription Funnel ───────────────────────────
        self.register_funnel(
            FunnelDefinition(
                funnel_id="funnel_saas_subscription",
                name="Paid SaaS Tier Subscription",
                description="Tracks users upgrading to Pro/Enterprise FRIDAY agent mesh licenses.",
                primary_goal=FridayConversionGoalType.PAID_SUBSCRIPTION,
                steps=[
                    FunnelStep(
                        step_id="step_pricing_view",
                        name="Pricing & Tiers Viewed",
                        step_index=0,
                        target_path="/pricing",
                        required_event_type="page_view",
                    ),
                    FunnelStep(
                        step_id="step_checkout_init",
                        name="Stripe Checkout Session Initiated",
                        step_index=1,
                        target_path="/checkout",
                        required_event_type="checkout_initiated",
                    ),
                    FunnelStep(
                        step_id="step_checkout_success",
                        name="Paid Subscription Confirmed",
                        step_index=2,
                        target_path="/checkout/success",
                        required_event_type=FridayConversionGoalType.PAID_SUBSCRIPTION.value,
                    ),
                ],
            )
        )

        # ── Option C: Community & Waitlist Signup Funnel ───────────────────────
        self.register_funnel(
            FunnelDefinition(
                funnel_id="funnel_waitlist_signup",
                name="Community & Developer Waitlist Signup",
                description="Tracks developers and operators signing up for the autonomous mesh waitlist.",
                primary_goal=FridayConversionGoalType.WAITLIST_SIGNUP,
                steps=[
                    FunnelStep(
                        step_id="step_home",
                        name="Home Showcase",
                        step_index=0,
                        target_path="/",
                        required_event_type="page_view",
                    ),
                    FunnelStep(
                        step_id="step_signup_click",
                        name="Signup CTA Engaged",
                        step_index=1,
                        target_path="/signup",
                        required_event_type="signup_cta_click",
                    ),
                    FunnelStep(
                        step_id="step_signup_complete",
                        name="Waitlist Registration Verified",
                        step_index=2,
                        target_path="/signup/welcome",
                        required_event_type=FridayConversionGoalType.WAITLIST_SIGNUP.value,
                    ),
                ],
            )
        )

        # ── Option D: Full 10-Agent Mesh Multi-Step Journey ────────────────────
        self.register_funnel(
            FunnelDefinition(
                funnel_id="funnel_10_agent_mesh_journey",
                name="FRIDAY Universe 10-Agent Mesh Multi-Step Journey",
                description="Comprehensive cross-agent exploration funnel across Homepage, Agent Showcase, Pricing, and Conversion.",
                primary_goal=FridayConversionGoalType.MULTI_STEP_JOURNEY,
                steps=[
                    FunnelStep(
                        step_id="stage_1_homepage",
                        name="1. Universe Gateway Landing",
                        step_index=0,
                        target_path="/",
                        required_event_type="page_view",
                        description="Visitor lands on https://friday-universe.duckdns.org",
                    ),
                    FunnelStep(
                        step_id="stage_2_agents_showcase",
                        name="2. 10 Specialist Agents Showcase",
                        step_index=1,
                        target_path="/agents",
                        required_event_type="agent_showcase_explore",
                        description="Explores Cortex, Forge, Sentinel, IntelX, Futuris, VyralX, Stratex, Memora, Inference, and FRIDAY Core",
                    ),
                    FunnelStep(
                        step_id="stage_3_pricing_plans",
                        name="3. Architecture & Pricing Evaluation",
                        step_index=2,
                        target_path="/pricing",
                        required_event_type="pricing_view",
                        description="Views tier matrix and token quota allocation",
                    ),
                    FunnelStep(
                        step_id="stage_4_conversion_action",
                        name="4. Goal Conversion (Demo or Subscription)",
                        step_index=3,
                        target_path="/convert",
                        required_event_type="conversion_completed",
                        description="Successfully triggers demo booking, paid subscription, or developer key activation",
                    ),
                ],
            )
        )

    def register_funnel(self, funnel: FunnelDefinition) -> None:
        self._funnels[funnel.funnel_id] = funnel

    def get_funnel(self, funnel_id: str) -> FunnelDefinition | None:
        return self._funnels.get(funnel_id)

    def list_funnels(self) -> list[FunnelDefinition]:
        return list(self._funnels.values())

    def seed_associated_bandit_experiments(self, tenant_id: str) -> list[str]:
        """
        Pre-seeds contextual Multi-Armed Bandit experiments for each of the 4 conversion goals.
        """
        created_exp_ids: list[str] = []

        # MAB for Option A (Enterprise Demo CTA)
        exp_a = global_bandit_engine.create_experiment(
            tenant_id=tenant_id,
            experiment_id="exp_enterprise_demo_cta",
            name="Enterprise Demo CTA Optimization",
            algorithm=BanditAlgorithm.THOMPSON_SAMPLING,
            arm_configs=[
                {"arm_id": "cta_control", "label": "Schedule Demo"},
                {"arm_id": "cta_architect", "label": "Book 1:1 Agent Architect Session"},
                {"arm_id": "cta_test_drive", "label": "Deploy Agent 6 Live on Mesh"},
            ],
            min_samples_for_decision=30,
            confidence_threshold=0.95,
        )
        created_exp_ids.append(exp_a.experiment_id)

        # MAB for Option B (SaaS Pricing Banner)
        exp_b = global_bandit_engine.create_experiment(
            tenant_id=tenant_id,
            experiment_id="exp_saas_pricing_tier",
            name="SaaS Tier Incentive Banner",
            algorithm=BanditAlgorithm.UCB1,
            arm_configs=[
                {"arm_id": "tier_monthly", "label": "Monthly Flexible License"},
                {"arm_id": "tier_annual_discount", "label": "Annual Plan - 2 Months Free"},
                {"arm_id": "tier_usage_payg", "label": "Pay-As-You-Go Token Billing"},
            ],
            min_samples_for_decision=30,
        )
        created_exp_ids.append(exp_b.experiment_id)

        # MAB for Option C (Developer Waitlist)
        exp_c = global_bandit_engine.create_experiment(
            tenant_id=tenant_id,
            experiment_id="exp_developer_waitlist_hook",
            name="Developer Waitlist Headline Hook",
            algorithm=BanditAlgorithm.THOMPSON_SAMPLING,
            arm_configs=[
                {"arm_id": "hook_mesh", "label": "Join FRIDAY Autonomous Developer Mesh"},
                {"arm_id": "hook_free_key", "label": "Claim Free 10-Agent API Key"},
            ],
            min_samples_for_decision=30,
        )
        created_exp_ids.append(exp_c.experiment_id)

        # MAB for Option D (Multi-Step Onboarding Mode)
        exp_d = global_bandit_engine.create_experiment(
            tenant_id=tenant_id,
            experiment_id="exp_agent_mesh_onboarding",
            name="10-Agent Mesh Exploration Onboarding",
            algorithm=BanditAlgorithm.THOMPSON_SAMPLING,
            arm_configs=[
                {"arm_id": "onboard_interactive_tour", "label": "Guided Interactive Agent Walkthrough"},
                {"arm_id": "onboard_sandbox", "label": "Instant Interactive Playground"},
                {"arm_id": "onboard_video", "label": "Architecture Video Demo"},
            ],
            min_samples_for_decision=30,
        )
        created_exp_ids.append(exp_d.experiment_id)

        return created_exp_ids

    def evaluate_funnel(
        self,
        funnel_id: str,
        sessions_events: dict[str, list[dict[str, Any]]],
    ) -> FunnelAnalysisReport:
        """
        Evaluates a mapping of {session_id: [event1, event2, ...]} against the funnel steps.
        """
        funnel = self.get_funnel(funnel_id)
        if not funnel:
            raise KeyError(f"Funnel '{funnel_id}' not found.")

        total_sessions = len(sessions_events)
        if total_sessions == 0:
            return FunnelAnalysisReport(
                funnel_id=funnel_id,
                name=funnel.name,
                total_sessions_analyzed=0,
                completed_sessions=0,
                overall_conversion_rate_pct=0.0,
                steps=[
                    StepMetric(
                        step_id=s.step_id,
                        name=s.name,
                        step_index=s.step_index,
                        visitors_reached=0,
                        conversion_from_previous_pct=0.0,
                        drop_off_count=0,
                        drop_off_pct=0.0,
                    )
                    for s in funnel.steps
                ],
                drop_off_hotspots=[],
            )

        step_counts: list[int] = [0] * len(funnel.steps)
        step_entry_deltas: list[list[float]] = [[] for _ in funnel.steps]
        completed_sessions = 0

        for session_id, raw_events in sessions_events.items():
            sorted_events = sorted(raw_events, key=lambda e: _parse_datetime(e.get("occurred_at")))
            if not sorted_events:
                continue

            first_event_time = _parse_datetime(sorted_events[0].get("occurred_at"))

            current_step_idx = 0
            for ev in sorted_events:
                if current_step_idx >= len(funnel.steps):
                    break

                target_step = funnel.steps[current_step_idx]
                ev_type = str(ev.get("type", "")).lower()
                ev_path = str(ev.get("data", {}).get("path", ev.get("path", ""))).lower()

                # Step match check
                matched = False
                if target_step.required_event_type.lower() in ev_type:
                    matched = True
                elif target_step.target_path and target_step.target_path.lower() in ev_path:
                    matched = True
                elif (
                    target_step.required_event_type == "conversion_completed"
                    and any(
                        goal.value in ev_type
                        for goal in [
                            FridayConversionGoalType.DEMO_BOOKING,
                            FridayConversionGoalType.PAID_SUBSCRIPTION,
                            FridayConversionGoalType.WAITLIST_SIGNUP,
                        ]
                    )
                ):
                    matched = True

                if matched:
                    step_counts[current_step_idx] += 1
                    ev_time = _parse_datetime(ev.get("occurred_at"))
                    delta_s = max(0.0, (ev_time - first_event_time).total_seconds())
                    step_entry_deltas[current_step_idx].append(delta_s)
                    current_step_idx += 1

            if current_step_idx >= len(funnel.steps):
                completed_sessions += 1

        # Build Step Metrics
        step_metrics: list[StepMetric] = []
        drop_off_hotspots: list[dict[str, Any]] = []

        for idx, step in enumerate(funnel.steps):
            reached = step_counts[idx]
            prev_reached = step_counts[idx - 1] if idx > 0 else total_sessions

            conv_pct = round((reached / prev_reached * 100.0) if prev_reached > 0 else 0.0, 2)
            drop_off_count = max(0, prev_reached - reached)
            drop_off_pct = round((drop_off_count / prev_reached * 100.0) if prev_reached > 0 else 0.0, 2)

            median_sec = 0.0
            if step_entry_deltas[idx]:
                median_sec = round(statistics.median(step_entry_deltas[idx]), 1)

            step_metrics.append(
                StepMetric(
                    step_id=step.step_id,
                    name=step.name,
                    step_index=step.step_index,
                    visitors_reached=reached,
                    conversion_from_previous_pct=conv_pct,
                    drop_off_count=drop_off_count,
                    drop_off_pct=drop_off_pct,
                    median_seconds_from_entry=median_sec,
                )
            )

            if drop_off_pct > 40.0 and prev_reached >= 5:
                drop_off_hotspots.append({
                    "step_name": step.name,
                    "step_index": step.step_index,
                    "drop_off_pct": drop_off_pct,
                    "severity": "HIGH" if drop_off_pct > 65.0 else "MEDIUM",
                    "recommendation": f"Optimize friction on {step.name}; drop-off exceeds {drop_off_pct:.1f}%.",
                })

        overall_conv_pct = round((completed_sessions / total_sessions * 100.0) if total_sessions > 0 else 0.0, 2)

        return FunnelAnalysisReport(
            funnel_id=funnel_id,
            name=funnel.name,
            total_sessions_analyzed=total_sessions,
            completed_sessions=completed_sessions,
            overall_conversion_rate_pct=overall_conv_pct,
            steps=step_metrics,
            drop_off_hotspots=drop_off_hotspots,
        )


global_funnel_manager = FridayUniverseFunnelManager()
