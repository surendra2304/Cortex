import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

logger = logging.getLogger("nexus-sentinel-listener")


class SentinelFinding(BaseModel):
    finding_id: str
    severity: str  # critical, high, medium, low, info
    title: str
    description: str
    evidence_ref: Optional[str] = None
    attack_vector: Optional[str] = None
    affected_endpoint: Optional[str] = None


class SentinelPayload(BaseModel):
    sentinel_task_id: str
    asset_id: str
    findings: List[SentinelFinding] = Field(default_factory=list)
    posture_score: float = 100.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SentinelEventListener:
    """
    Sentinel Security Findings Listener & Bridge:
    - Receives automated vulnerability and posture findings from Sentinel
    - Transforms findings into typed Nexus security events for Cognitive Loop ingestion
    - Integrates with AssetExposureMonitor to evaluate actual attack surface exposure
    """

    def __init__(self, exposure_monitor: Optional[Any] = None):
        self.exposure_monitor = exposure_monitor
        self.received_findings: List[Dict[str, Any]] = []

    async def handle_findings(self, payload: SentinelPayload, orchestrator: Optional[Any] = None) -> Dict[str, Any]:
        logger.info(f"Received Sentinel security findings for asset {payload.asset_id} (Task: {payload.sentinel_task_id})")

        processed_events = []
        for finding in payload.findings:
            finding_data = finding.model_dump()
            self.received_findings.append({
                "sentinel_task_id": payload.sentinel_task_id,
                "asset_id": payload.asset_id,
                "posture_score": payload.posture_score,
                **finding_data
            })

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
                    "exposure_level": exposure_level
                },
                "occurred_at": payload.timestamp.isoformat()
            }
            processed_events.append(event_wire)

        return {
            "status": "ingested",
            "asset_id": payload.asset_id,
            "findings_count": len(payload.findings),
            "events_created": len(processed_events),
            "posture_score": payload.posture_score,
            "processed_at": datetime.utcnow().isoformat()
        }
