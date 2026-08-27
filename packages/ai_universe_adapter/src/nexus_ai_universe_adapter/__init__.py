from typing import Any, Dict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import httpx
import logging

logger = logging.getLogger("nexus-ai-universe-adapter")


class IntelligenceRequest(BaseModel):
    request_id: str = Field(..., description="Unique identifier for the intelligence request")
    task_type: str = Field(..., description="Task classification e.g. lead_scoring, anomaly_detection, intervention")
    goal: str = Field(..., description="Specific goal description or query intent")
    context: Dict[str, Any] = Field(default_factory=dict, description="Contextual state attributes")
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Historical events, visitor traits, or metrics")
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
    def __init__(self, endpoint: str = "https://api.ai-universe.dev", api_key: Optional[str] = None, timeout_seconds: float = 5.0):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def _get_deterministic_fallback(self, request: IntelligenceRequest) -> IntelligenceResponse:
        return IntelligenceResponse(
            request_id=request.request_id,
            decision="NOOP",
            confidence=1.0,
            summary="Fallback policy applied due to upstream service unavailability.",
            key_evidence=["ai_universe_unreachable_or_timed_out"],
            provenance={"source": "deterministic_fallback_policy"},
            unresolved_disagreements=[],
            recommended_actions=[],
            safety_notes=["Deterministic fallback activated to preserve platform safety."],
            fallback_applied=True
        )

    async def evaluate(self, request: IntelligenceRequest) -> IntelligenceResponse:
        url = f"{self.endpoint}/v1/nexus/intelligence"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}" if self.api_key else ""
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(url, json=request.model_dump(mode="json"), headers=headers)
                if resp.status_code == 200:
                    return IntelligenceResponse(**resp.json())
                else:
                    logger.warning(f"AI Universe returned status {resp.status_code}. Applying fallback.")
                    return self._get_deterministic_fallback(request)
        except Exception as exc:
            logger.warning(f"AI Universe call failed ({exc}). Applying deterministic fallback.")
            return self._get_deterministic_fallback(request)
