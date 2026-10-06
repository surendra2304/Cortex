import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-sentinel-listener")


class SentinelFinding(BaseModel):
    finding_id: str
    severity: str  # critical, high, medium, low, info
    title: str
    description: str
    evidence_ref: str | None = None
    attack_vector: str | None = None
    affected_endpoint: str | None = None


class SentinelPayload(BaseModel):
    sentinel_task_id: str
    asset_id: str
    findings: list[SentinelFinding] = Field(default_factory=list)
    posture_score: float = 100.0
    timestamp: datetime = Field(default_factory=_utcnow)


class SentinelEventListener:
    """
    Sentinel Security Findings Listener & Bridge:
    - Receives automated vulnerability and posture findings from Sentinel
    - Transforms findings into typed Cortex security events for Cognitive Loop ingestion
    - Integrates with AssetExposureMonitor to evaluate actual attack surface exposure
    """

    def __init__(self, exposure_monitor: Any | None = None):
        self.exposure_monitor = exposure_monitor
        self.received_findings: list[dict[str, Any]] = []

    async def handle_findings(self, payload: SentinelPayload, orchestrator: Any | None = None) -> dict[str, Any]:
        logger.info(
            f"Received Sentinel security findings for asset {payload.asset_id} (Task: {payload.sentinel_task_id})"
        )

        processed_events = []
        for finding in payload.findings:
            finding_data = finding.model_dump()
            self.received_findings.append(
                {
                    "sentinel_task_id": payload.sentinel_task_id,
                    "asset_id": payload.asset_id,
                    "posture_score": payload.posture_score,
                    **finding_data,
                }
            )

            # Evaluate exposure if exposure monitor is available
            exposure_level = "standard"
            if self.exposure_monitor and hasattr(self.exposure_monitor, "evaluate_exposure"):
                endpoint = finding.affected_endpoint or f"/api/{payload.asset_id}"
                exposure = self.exposure_monitor.evaluate_exposure(payload.asset_id, endpoint)
                exposure_level = exposure.get("exposure_level", "standard")

            event_wire = {
                "event_id": f"evt_sec_{uuid.uuid4().hex[:10]}",
                "type": f"security.finding.{finding.severity.lower()}",
                "site_id": payload.asset_id,
                "actor": {"type": "sentinel_system", "id": "sentinel_scanner"},
                "data": {
                    "sentinel_task_id": payload.sentinel_task_id,
                    "finding_id": finding.finding_id,
                    "severity": finding.severity,
                    "title": finding.title,
                    "description": finding.description,
                    "evidence_ref": finding.evidence_ref,
                    "attack_vector": finding.attack_vector,
                    "posture_score": payload.posture_score,
                    "exposure_level": exposure_level,
                },
                "occurred_at": payload.timestamp.isoformat(),
            }
            processed_events.append(event_wire)

        return {
            "status": "ingested",
            "asset_id": payload.asset_id,
            "findings_count": len(payload.findings),
            "events_created": len(processed_events),
            "posture_score": payload.posture_score,
            "processed_at": _utcnow().isoformat(),
        }
