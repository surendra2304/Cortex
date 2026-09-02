from typing import Dict, Any, Optional
from datetime import datetime
import logging
import sys
import os

sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))

from cortex_tool_runtime import Tool, Execution, SideEffectLevel, PolicyDecision

logger = logging.getLogger("cortex-policy-engine")


class PolicyEngine:
    def __init__(self, human_in_the_loop_enabled: bool = True):
        self.human_in_the_loop_enabled = human_in_the_loop_enabled

    def evaluate(self, execution: Execution, tool: Tool) -> PolicyDecision:
        level = tool.side_effect_level

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
            if self.human_in_the_loop_enabled:
                return PolicyDecision(
                    approved=False,
                    requires_human_approval=True,
                    reason="High impact tool execution requires explicit operator confirmation.",
                    risk_score=0.8,
                    evaluated_at=datetime.utcnow()
                )
            return PolicyDecision(
                approved=True,
                requires_human_approval=False,
                reason="High impact tool auto-approved under autonomous execution.",
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
    "SecretScrubber",
    "PrivacyComplianceService",
    "DataSubjectExport"
]
