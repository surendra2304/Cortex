from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import httpx
import os
import asyncio
import logging

logger = logging.getLogger("nexus-ai-universe-adapter")


class EvidenceItem(BaseModel):
    key: str
    value: Any
    trust_label: str = Field(
        default="verified_telemetry",
        description="Trust level: system_fact, verified_telemetry, untrusted_user_input, inferred_profile"
    )
    source: str = "telemetry_engine"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class IntelligenceRequest(BaseModel):
    request_id: str = Field(..., description="Unique identifier for the intelligence request")
    task_type: str = Field(..., description="Task classification e.g. lead_scoring, anomaly_detection, intervention")
    goal: str = Field(..., description="Specific goal description or query intent")
    context: Dict[str, Any] = Field(default_factory=dict, description="Contextual state attributes")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Historical events, visitor traits, or metrics")
    trust_labels: Dict[str, str] = Field(default_factory=dict, description="Mapping of evidence/context keys to trust classifications")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Lineage metadata tracking origin site, tenant, and trace_id")
    constraints: List[str] = Field(default_factory=list, description="Operational boundaries or policy rules")
    required_output: Dict[str, Any] = Field(default_factory=dict, description="Expected schema or key targets")
    budget: Dict[str, Any] = Field(default_factory=lambda: {"max_tokens": 1000, "timeout_ms": 3000})


class RecommendedAction(BaseModel):
    action_type: str
    target: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 1


class IntelligenceResponse(BaseModel):
    request_id: str
    decision: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str
    key_evidence: List[str] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    unresolved_disagreements: List[str] = Field(default_factory=list)
    recommended_actions: List[RecommendedAction] = Field(default_factory=list)
    safety_notes: List[str] = Field(default_factory=list)
    fallback_applied: bool = False
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class AIUniverseClient:
    """Live HTTP client for AI Universe with exponential backoff retries and deterministic fallback."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: float = 5.0,
        max_retries: int = 3
    ):
        self.endpoint = (
            endpoint
            or os.getenv("AI_UNIVERSE_BASE_URL", "https://api.ai-universe.dev")
        ).rstrip("/")
        self.api_key = api_key or os.getenv("AI_UNIVERSE_API_KEY", "")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    def _get_deterministic_fallback(self, request: IntelligenceRequest, reason: str = "upstream_unavailable") -> IntelligenceResponse:
        """Deterministic safety policy fallback when AI Universe is unavailable or times out."""
        return IntelligenceResponse(
            request_id=request.request_id,
            decision="NOOP_FALLBACK",
            confidence=0.0,
            summary=f"Deterministic safety fallback applied: {reason}.",
            key_evidence=["ai_universe_fallback_activated"],
            provenance={"source": "deterministic_fallback_policy", "origin_request_id": request.request_id},
            unresolved_disagreements=[],
            recommended_actions=[],
            safety_notes=["Deterministic fallback activated to preserve platform safety and system invariants."],
            fallback_applied=True,
            generated_at=datetime.utcnow()
        )

    async def evaluate(self, request: IntelligenceRequest) -> IntelligenceResponse:
        url = f"{self.endpoint}/v1/nexus/intelligence"
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "NEXUS-AIUniverse-Adapter/1.0"
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = request.model_dump(mode="json")

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.post(url, json=payload, headers=headers)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        response = IntelligenceResponse(**data)
                        if response.unresolved_disagreements:
                            logger.warning(
                                f"AI Universe response for {request.request_id} has unresolved disagreements: {response.unresolved_disagreements}"
                            )
                        return response
                    elif 500 <= resp.status_code < 600:
                        logger.warning(
                            f"AI Universe returned server error {resp.status_code} (attempt {attempt}/{self.max_retries}). Retrying..."
                        )
                        if attempt < self.max_retries:
                            await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                            continue
                        return self._get_deterministic_fallback(request, f"server_error_{resp.status_code}")
                    else:
                        logger.warning(f"AI Universe returned client error {resp.status_code}: {resp.text}.")
                        return self._get_deterministic_fallback(request, f"client_error_{resp.status_code}")

            except (httpx.TimeoutException, httpx.NetworkError, Exception) as exc:
                logger.warning(f"AI Universe request failed on attempt {attempt}/{self.max_retries} ({exc}).")
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                return self._get_deterministic_fallback(request, str(exc))

        return self._get_deterministic_fallback(request, "max_retries_exceeded")
