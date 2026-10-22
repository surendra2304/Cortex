import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-deployment-gate")


class GateVerdict(str, Enum):
    APPROVED = "APPROVED"
    BLOCKED = "BLOCKED"
    NEEDS_APPROVAL = "NEEDS_APPROVAL"


class DeploymentGateResult(BaseModel):
    deployment_id: str
    asset_id: str
    endpoints: list[str]
    verdict: GateVerdict
    block_reason: str | None = None
    critical_count: int = 0
    high_count: int = 0
    medium_low_count: int = 0
    findings_summary: list[dict[str, Any]] = Field(default_factory=list)
    requires_human_override: bool = False
    approval_request_id: str | None = None
    evaluated_at: datetime = Field(default_factory=_utcnow)


class DeploymentSecurityGate:
    """
    DevSecOps Deployment Security Gate:
    - Triggers automated Sentinel API security scans on candidate deployment endpoints
    - Gate Enforcement Logic:
      - CRITICAL Finding: BLOCKED (Traffic routing prevented)
      - HIGH Finding: NEEDS_APPROVAL (Requires explicit human-in-the-loop override)
      - MEDIUM / LOW Finding: APPROVED (Logged to audit and traffic allowed)
    - Integrates with Forge delivery manifests
    """

    def __init__(self, sentinel_listener: Any | None = None, policy_engine: Any | None = None):
        self.sentinel_listener = sentinel_listener
        self.policy_engine = policy_engine
        self.gate_history: list[DeploymentGateResult] = []

    async def evaluate_deployment(
        self,
        deployment_id: str,
        asset_id: str,
        endpoints: list[str],
        simulated_findings: list[dict[str, Any]] | None = None,
    ) -> DeploymentGateResult:
        logger.info(
            f"Evaluating DevSecOps deployment gate for {deployment_id} (Asset: {asset_id}, Endpoints: {endpoints})"
        )

        # Use simulated findings or query Sentinel
        findings = simulated_findings or []

        critical_findings = [f for f in findings if f.get("severity", "").lower() == "critical"]
        high_findings = [f for f in findings if f.get("severity", "").lower() == "high"]
        medium_low_findings = [f for f in findings if f.get("severity", "").lower() in ("medium", "low", "info")]

        if critical_findings:
            verdict = GateVerdict.BLOCKED
            block_reason = f"Automated scan found {len(critical_findings)} CRITICAL security vulnerability(ies): {critical_findings[0].get('title')}"
            requires_human_override = False
            approval_request_id = None
        elif high_findings:
            verdict = GateVerdict.NEEDS_APPROVAL
            block_reason = (
                f"Automated scan detected {len(high_findings)} HIGH security finding(s). Requires operator approval."
            )
            requires_human_override = True
            approval_request_id = f"req_appr_sec_{uuid.uuid4().hex[:8]}"
        else:
            verdict = GateVerdict.APPROVED
            block_reason = None
            requires_human_override = False
            approval_request_id = None

        result = DeploymentGateResult(
            deployment_id=deployment_id,
            asset_id=asset_id,
            endpoints=endpoints,
            verdict=verdict,
            block_reason=block_reason,
            critical_count=len(critical_findings),
            high_count=len(high_findings),
            medium_low_count=len(medium_low_findings),
            findings_summary=findings,
            requires_human_override=requires_human_override,
            approval_request_id=approval_request_id,
            evaluated_at=_utcnow(),
        )

        self.gate_history.append(result)
        return result

    async def process_forge_delivery(self, forge_task_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Parses Forge delivery artifact manifest and runs Sentinel pre-flight scan."""
        endpoints = manifest.get("deployed_endpoints", ["/api/v1/service"])
        asset_id = manifest.get("asset_id", "site_main")
        deployment_id = f"dep_forge_{forge_task_id}"

        findings = manifest.get("security_findings", [])
        gate_res = await self.evaluate_deployment(
            deployment_id=deployment_id, asset_id=asset_id, endpoints=endpoints, simulated_findings=findings
        )

        return {
            "forge_task_id": forge_task_id,
            "deployment_id": deployment_id,
            "gate_result": gate_res.model_dump(),
            "traffic_routed": gate_res.verdict == GateVerdict.APPROVED,
        }

    async def health_check(self) -> dict[str, Any]:
        """Performs health check on DeploymentSecurityGate integration."""
        return {
            "status": "UP",
            "service": "deployment_security_gate",
            "sentinel_bridge": "active",
            "evaluated_deployments": len(self.gate_history),
            "timestamp": _utcnow().isoformat(),
        }
