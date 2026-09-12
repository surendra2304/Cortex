from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from enum import Enum
import logging
import sys
import os

sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))

from cortex_tool_runtime import Tool, Execution, SideEffectLevel, PolicyDecision

logger = logging.getLogger("cortex-policy-engine")


class HighImpactCategory(str, Enum):
    BILLING = "billing"
    CUSTOMER_COMMUNICATION = "customer_communication"
    PRODUCTION_CONFIGURATION = "production_configuration"
    CONTENT_PUBLISHING = "content_publishing"
    ACCOUNT_PERMISSIONS = "account_permissions"


HIGH_IMPACT_CATEGORIES: Dict[HighImpactCategory, List[str]] = {
    HighImpactCategory.BILLING: [
        "payment_initiate", "billing_update", "pricing_change",
        "subscription_modify", "refund_issue", "stripe_charge"
    ],
    HighImpactCategory.CUSTOMER_COMMUNICATION: [
        "email_dispatch", "sms_dispatch", "voice_dispatch",
        "broadcast_message", "marketing_outreach", "crm_sync"
    ],
    HighImpactCategory.PRODUCTION_CONFIGURATION: [
        "config_update", "deployment_traffic_switch", "route_mutate",
        "prod_env_update", "feature_flag_toggle", "experiment_mutate"
    ],
    HighImpactCategory.CONTENT_PUBLISHING: [
        "content_publish", "page_deploy", "theme_publish",
        "banner_injection", "site_modify"
    ],
    HighImpactCategory.ACCOUNT_PERMISSIONS: [
        "account_update", "permission_grant", "role_modify",
        "user_invite_admin", "credential_revoke"
    ],
}


def check_high_impact_category(tool_name: str) -> Optional[Tuple[HighImpactCategory, str]]:
    norm = tool_name.lower().strip()
    for cat, ops in HIGH_IMPACT_CATEGORIES.items():
        if norm in ops or any(op in norm for op in ops):
            return cat, norm
    return None


class PolicyEngine:
    def __init__(self, human_in_the_loop_enabled: bool = True):
        self.human_in_the_loop_enabled = human_in_the_loop_enabled

    def evaluate(self, execution: Execution, tool: Tool) -> PolicyDecision:
        level = tool.side_effect_level

        # Check if tool belongs to any of the 5 mandatory high-impact categories
        hi_check = check_high_impact_category(tool.name)
        if hi_check:
            category, _ = hi_check
            level = SideEffectLevel.HIGH_IMPACT

        # Check if an explicit supervisor approval record was provided
        has_approval = (
            execution.approval is not None
            and isinstance(execution.approval, dict)
            and execution.approval.get("approved") is True
        )

        if has_approval:
            return PolicyDecision(
                approved=True,
                requires_human_approval=False,
                reason=f"Operation approved via explicit supervisor token ({execution.approval.get('approver_id', 'operator')}).",
                risk_score=0.2,
                evaluated_at=datetime.utcnow()
            )

        if level == SideEffectLevel.READ:
            return PolicyDecision(
                approved=True,
                requires_human_approval=False,
                reason="Read-only operations are automatically approved without state mutations.",
                risk_score=0.0,
                evaluated_at=datetime.utcnow()
            )

        elif level == SideEffectLevel.SENSITIVE:
            return PolicyDecision(
                approved=True,
                requires_human_approval=False,
                reason="Sensitive operation auto-approved under audited telemetry guidelines.",
                risk_score=0.3,
                evaluated_at=datetime.utcnow()
            )

        elif level == SideEffectLevel.HIGH_IMPACT:
            cat_name = hi_check[0].value if hi_check else "high_impact"
            if self.human_in_the_loop_enabled:
                return PolicyDecision(
                    approved=False,
                    requires_human_approval=True,
                    reason=f"High-impact operation in category '{cat_name}' requires explicit operator approval.",
                    risk_score=0.8,
                    evaluated_at=datetime.utcnow()
                )
            return PolicyDecision(
                approved=True,
                requires_human_approval=False,
                reason="High-impact tool auto-approved under autonomous execution.",
                risk_score=0.8,
                evaluated_at=datetime.utcnow()
            )

        elif level == SideEffectLevel.DANGEROUS:
            return PolicyDecision(
                approved=False,
                requires_human_approval=True,
                reason="Dangerous side-effect operation blocked. Requires administrator manual override.",
                risk_score=1.0,
                evaluated_at=datetime.utcnow()
            )

        return PolicyDecision(
            approved=False,
            requires_human_approval=True,
            reason=f"Unknown side-effect level {level}. Blocked by default safe invariant.",
            risk_score=1.0,
            evaluated_at=datetime.utcnow()
        )


from cortex_policy_engine.privacy import (
    SecretScrubber,
    PrivacyComplianceService,
    DataSubjectExport
)

__all__ = [
    "PolicyEngine",
    "HighImpactCategory",
    "HIGH_IMPACT_CATEGORIES",
    "check_high_impact_category",
    "SecretScrubber",
    "PrivacyComplianceService",
    "DataSubjectExport"
]
