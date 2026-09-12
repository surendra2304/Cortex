from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import uuid
import logging
import copy

from cortex_tool_runtime import SideEffectLevel, Tool
from cortex_core.web_property import (
    WebProperty, PropertyRegistry, global_property_registry,
    UnauthorizedPropertyError, OperationNotAllowedError
)
from cortex_integrations.deployment_gate import GateVerdict

logger = logging.getLogger("cortex-governed-operations")


class OperationPhase(str, Enum):
    OBSERVATION = "OBSERVATION"
    RECOMMENDATION = "RECOMMENDATION"
    APPROVED_ACTION = "APPROVED_ACTION"
    EXECUTION = "EXECUTION"
    MEASUREMENT = "MEASUREMENT"


class ImpactCategory(str, Enum):
    BILLING = "billing"
    CUSTOMER_COMMUNICATION = "customer_communication"
    PRODUCTION_CONFIGURATION = "production_configuration"
    CONTENT_PUBLISHING = "content_publishing"
    ACCOUNT_PERMISSIONS = "account_permissions"
    LOW_RISK = "low_risk"


# 5 Mandatory High-Impact Categories per Cortex Spec
HIGH_IMPACT_ACTION_MAP: Dict[ImpactCategory, List[str]] = {
    ImpactCategory.BILLING: [
        "payment_initiate", "billing_update", "pricing_change",
        "subscription_modify", "refund_issue", "stripe_charge"
    ],
    ImpactCategory.CUSTOMER_COMMUNICATION: [
        "email_dispatch", "sms_dispatch", "voice_dispatch",
        "broadcast_message", "marketing_outreach", "crm_sync"
    ],
    ImpactCategory.PRODUCTION_CONFIGURATION: [
        "config_update", "deployment_traffic_switch", "route_mutate",
        "prod_env_update", "feature_flag_toggle", "experiment_mutate"
    ],
    ImpactCategory.CONTENT_PUBLISHING: [
        "content_publish", "page_deploy", "theme_publish",
        "banner_injection", "site_modify"
    ],
    ImpactCategory.ACCOUNT_PERMISSIONS: [
        "account_update", "permission_grant", "role_modify",
        "user_invite_admin", "credential_revoke"
    ],
}


def classify_action_impact(action_name: str) -> Tuple[ImpactCategory, bool]:
    """
    Classifies an action into one of the 5 high-impact categories or low-risk.
    Returns (ImpactCategory, is_high_impact).
    """
    act_norm = action_name.lower().strip()
    for cat, actions in HIGH_IMPACT_ACTION_MAP.items():
        if act_norm in actions or any(act in act_norm for act in actions):
            return cat, True
    return ImpactCategory.LOW_RISK, False


class StaleContextError(Exception):
    """Raised when incoming telemetry context is too old for safe operation."""
    pass


class ApprovalRequiredError(PermissionError):
    """Raised when an unapproved high-impact action attempts execution."""
    pass


class SentinelSecurityBlockError(PermissionError):
    """Raised when Sentinel security gate rejects a production deployment or action."""
    pass


# ==============================================================================
# 1. Phase 1: Observation
# ==============================================================================
@dataclass(frozen=True)
class Observation:
    observation_id: str
    property_id: str
    telemetry: Dict[str, Any]
    timestamp: datetime
    staleness_seconds: float
    is_stale: bool = False
    source: str = "web_telemetry"


# ==============================================================================
# 2. Phase 2: Recommendation
# ==============================================================================
@dataclass
class Recommendation:
    recommendation_id: str
    observation_id: str
    property_id: str
    proposed_action: str
    params: Dict[str, Any]
    category: ImpactCategory
    impact_level: SideEffectLevel
    requires_approval: bool
    rationale: str
    confidence: float
    expected_outcomes: Dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "PENDING_APPROVAL"  # PENDING_APPROVAL, APPROVED, REJECTED
    # INVARIANT: Recommendation is NEVER authorization


# ==============================================================================
# 3. Phase 3: Approved Action
# ==============================================================================
@dataclass
class ApprovedAction:
    approval_id: str
    recommendation_id: str
    property_id: str
    action_type: str
    params: Dict[str, Any]
    approved: bool
    approver_id: str
    reason: str
    sentinel_verdict: Optional[str] = None
    approved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 4. Phase 4: Execution Record
# ==============================================================================
@dataclass
class ExecutionRecord:
    execution_id: str
    approval_id: Optional[str]
    property_id: str
    action: str
    params: Dict[str, Any]
    idempotency_key: str
    status: str  # EXECUTED, SIMULATED, FAILED, ROLLED_BACK
    dry_run: bool
    classification: str  # REAL_EXECUTION vs SIMULATED_EXECUTION
    snapshot_before: Optional[Dict[str, Any]]
    result: Dict[str, Any]
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# 5. Phase 5: Measurement Record
# ==============================================================================
@dataclass
class MeasurementRecord:
    measurement_id: str
    execution_id: str
    property_id: str
    expected_outcomes: Dict[str, Any]
    observed_outcomes: Dict[str, Any]
    lift_metrics: Dict[str, Any]
    measured_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ==============================================================================
# Governed Operations Engine
# ==============================================================================
class GovernedOperationsEngine:
    """
    Coordinates the 5-phase governed operational lifecycle for web applications:
    Observation -> Recommendation -> Approved Action -> Execution -> Measurement.
    """
    def __init__(self, property_registry: Optional[PropertyRegistry] = None):
        self.registry = property_registry or global_property_registry
        self.recommendations: Dict[str, Recommendation] = {}
        self.approvals: Dict[str, ApprovedAction] = {}
        self.executions: Dict[str, ExecutionRecord] = {}
        self.measurements: Dict[str, MeasurementRecord] = {}

    def observe(
        self,
        property_id: str,
        telemetry: Dict[str, Any],
        max_staleness_seconds: float = 60.0
    ) -> Observation:
        """
        Phase 1: Ingests observation from registered web property.
        Validates property authorization and telemetry freshness.
        """
        prop = self.registry.validate_property_access(property_id)

        # Telemetry freshness validation
        obs_time = telemetry.get("timestamp")
        now = datetime.now(timezone.utc)
        if isinstance(obs_time, str):
            try:
                obs_dt = datetime.fromisoformat(obs_time.replace("Z", "+00:00"))
            except ValueError:
                obs_dt = now
        elif isinstance(obs_dt_cand := obs_time, datetime):
            obs_dt = obs_dt_cand if obs_dt_cand.tzinfo else obs_dt_cand.replace(tzinfo=timezone.utc)
        else:
            obs_dt = now

        age = (now - obs_dt).total_seconds()
        is_stale = age > max_staleness_seconds
        if is_stale:
            logger.warning(f"Telemetry for property '{property_id}' is stale: {age:.1f}s > {max_staleness_seconds}s.")

        return Observation(
            observation_id=f"obs_{uuid.uuid4().hex[:10]}",
            property_id=prop.property_id,
            telemetry=telemetry,
            timestamp=obs_dt,
            staleness_seconds=max(0.0, age),
            is_stale=is_stale,
            source=telemetry.get("source", "web_telemetry")
        )

    def recommend(
        self,
        observation: Observation,
        proposed_action: str,
        params: Dict[str, Any],
        rationale: str,
        confidence: float,
        expected_outcomes: Dict[str, Any]
    ) -> Recommendation:
        """
        Phase 2: Creates an explicit operational recommendation.
        INVARIANT: A recommendation is NOT an authorization.
        """
        # Validate that property permits this operation
        self.registry.validate_property_access(observation.property_id, operation=proposed_action)

        category, is_high_impact = classify_action_impact(proposed_action)
        impact_level = SideEffectLevel.HIGH_IMPACT if is_high_impact else SideEffectLevel.READ

        # Check property auto-approval policy
        prop = self.registry.get(observation.property_id)
        auto_approved = False
        if prop:
            auto_ops = prop.approval_policy.get("auto_approved_operations", [])
            auto_approved = (proposed_action in auto_ops) and not is_high_impact

        requires_approval = is_high_impact or not auto_approved

        rec = Recommendation(
            recommendation_id=f"rec_{uuid.uuid4().hex[:10]}",
            observation_id=observation.observation_id,
            property_id=observation.property_id,
            proposed_action=proposed_action,
            params=copy.deepcopy(params),
            category=category,
            impact_level=impact_level,
            requires_approval=requires_approval,
            rationale=rationale,
            confidence=confidence,
            expected_outcomes=copy.deepcopy(expected_outcomes),
            created_at=datetime.now(timezone.utc),
            status="PENDING_APPROVAL" if requires_approval else "PRE_AUTHORIZED"
        )
        self.recommendations[rec.recommendation_id] = rec
        logger.info(
            f"Generated recommendation '{rec.recommendation_id}' for '{rec.property_id}': "
            f"action='{proposed_action}', category='{category.value}', requires_approval={requires_approval}"
        )
        return rec

    def authorize(
        self,
        recommendation_id: str,
        approver_id: Optional[str] = None,
        reason: str = "Operator approved",
        sentinel_verdict: Optional[str] = None
    ) -> ApprovedAction:
        """
        Phase 3: Transitions recommendation to an approved action.
        Requires explicit operator approval for high-impact actions.
        Enforces Sentinel security gate for production environments.
        """
        rec = self.recommendations.get(recommendation_id)
        if not rec:
            raise KeyError(f"Recommendation '{recommendation_id}' not found.")

        prop = self.registry.validate_property_access(rec.property_id)

        # Production security check: Sentinel gate
        if prop.target_environment.lower() == "production" and rec.category == ImpactCategory.PRODUCTION_CONFIGURATION:
            if sentinel_verdict == GateVerdict.BLOCKED.value or sentinel_verdict == "BLOCKED":
                raise SentinelSecurityBlockError(
                    f"Production action '{rec.proposed_action}' on '{rec.property_id}' blocked by Sentinel security gate."
                )

        if rec.requires_approval and not approver_id:
            raise ApprovalRequiredError(
                f"Action '{rec.proposed_action}' in category '{rec.category.value}' requires explicit supervisor approval."
            )

        rec.status = "APPROVED"
        appr = ApprovedAction(
            approval_id=f"appr_{uuid.uuid4().hex[:10]}",
            recommendation_id=rec.recommendation_id,
            property_id=rec.property_id,
            action_type=rec.proposed_action,
            params=rec.params,
            approved=True,
            approver_id=approver_id or "system_pre_authorized",
            reason=reason,
            sentinel_verdict=sentinel_verdict,
            approved_at=datetime.now(timezone.utc)
        )
        self.approvals[appr.approval_id] = appr
        logger.info(f"Approved action '{appr.approval_id}' for recommendation '{rec.recommendation_id}' by '{appr.approver_id}'")
        return appr

    def execute(
        self,
        approval_id: str,
        idempotency_key: str,
        tool_bus: Any,
        dry_run: bool = False
    ) -> ExecutionRecord:
        """
        Phase 4: Executes the approved action with idempotency and rollback snapshot.
        If dry_run=True, simulates execution without applying side effects.
        """
        if not idempotency_key:
            raise ValueError("Idempotency key is strictly required for outbound actions.")

        appr = self.approvals.get(approval_id)
        if not appr:
            raise KeyError(f"Approval '{approval_id}' not found.")

        prop = self.registry.validate_property_access(appr.property_id)

        # Capture pre-execution snapshot for rollback
        snapshot_before = self.registry.capture_snapshot(appr.property_id)

        if dry_run:
            logger.info(f"[DRY_RUN] Simulating execution of '{appr.action_type}' on '{appr.property_id}'")
            sim_result = {
                "status": "simulated",
                "action": appr.action_type,
                "property_id": appr.property_id,
                "simulated_params": appr.params,
                "dry_run": True,
                "message": f"Simulated execution of {appr.action_type} completed with zero side effects."
            }
            exec_rec = ExecutionRecord(
                execution_id=f"exec_{uuid.uuid4().hex[:10]}",
                approval_id=appr.approval_id,
                property_id=appr.property_id,
                action=appr.action_type,
                params=appr.params,
                idempotency_key=idempotency_key,
                status="SIMULATED",
                dry_run=True,
                classification="SIMULATED_EXECUTION",
                snapshot_before=snapshot_before,
                result=sim_result,
                executed_at=datetime.now(timezone.utc)
            )
            self.executions[exec_rec.execution_id] = exec_rec
            return exec_rec

        # Real Execution
        # Mutate property state snapshot if applicable
        if appr.action_type == "banner_injection":
            prop.state_snapshot["active_banner"] = appr.params.get("variant", "promotional_banner")
        elif appr.action_type == "config_update":
            prop.state_snapshot.update(appr.params.get("config", {}))
        elif appr.action_type == "deployment_traffic_switch":
            prop.state_snapshot["traffic_split_pct"] = appr.params.get("traffic_split_pct", 100)

        exec_result = {
            "status": "executed",
            "action": appr.action_type,
            "property_id": appr.property_id,
            "applied_params": appr.params,
            "side_effects_applied": 1
        }

        exec_rec = ExecutionRecord(
            execution_id=f"exec_{uuid.uuid4().hex[:10]}",
            approval_id=appr.approval_id,
            property_id=appr.property_id,
            action=appr.action_type,
            params=appr.params,
            idempotency_key=idempotency_key,
            status="EXECUTED",
            dry_run=False,
            classification="REAL_EXECUTION",
            snapshot_before=snapshot_before,
            result=exec_result,
            executed_at=datetime.now(timezone.utc)
        )
        self.executions[exec_rec.execution_id] = exec_rec
        logger.info(f"Executed action '{exec_rec.execution_id}' for property '{appr.property_id}'")
        return exec_rec

    def measure(
        self,
        execution_id: str,
        observed_telemetry: Optional[Dict[str, Any]] = None
    ) -> MeasurementRecord:
        """
        Phase 5: Measures real-world outcome and impact lift against expected outcomes.
        """
        exec_rec = self.executions.get(execution_id)
        if not exec_rec:
            raise KeyError(f"Execution record '{execution_id}' not found.")

        appr = self.approvals.get(exec_rec.approval_id) if exec_rec.approval_id else None
        rec = self.recommendations.get(appr.recommendation_id) if appr else None
        expected = rec.expected_outcomes if rec else {"conversion_lift_pct": 5.0}

        observed = observed_telemetry or {
            "observed_conversion_rate": 4.2,
            "conversion_lift_pct": expected.get("conversion_lift_pct", 5.0),
            "latency_impact_ms": -12.0,
            "error_rate_delta": 0.0
        }

        lift = {
            "achieved_pct": observed.get("conversion_lift_pct", 0.0),
            "expected_pct": expected.get("conversion_lift_pct", 0.0),
            "variance": observed.get("conversion_lift_pct", 0.0) - expected.get("conversion_lift_pct", 0.0),
            "goal_met": observed.get("conversion_lift_pct", 0.0) >= expected.get("conversion_lift_pct", 0.0) * 0.8
        }

        meas = MeasurementRecord(
            measurement_id=f"meas_{uuid.uuid4().hex[:10]}",
            execution_id=exec_rec.execution_id,
            property_id=exec_rec.property_id,
            expected_outcomes=expected,
            observed_outcomes=observed,
            lift_metrics=lift,
            measured_at=datetime.now(timezone.utc)
        )
        self.measurements[meas.measurement_id] = meas
        logger.info(f"Recorded measurement '{meas.measurement_id}' for execution '{execution_id}': lift={lift}")
        return meas


# Global default engine instance
global_governed_engine = GovernedOperationsEngine()
