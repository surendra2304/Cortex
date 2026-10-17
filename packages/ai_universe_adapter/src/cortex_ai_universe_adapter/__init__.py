import asyncio
import json
import logging
import os
import time
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-ai-universe-adapter")


class EvidenceItem(BaseModel):
    key: str
    value: Any
    trust_label: str = Field(
        default="verified_telemetry",
        description="Trust level: system_fact, verified_telemetry, untrusted_user_input, inferred_profile",
    )
    source: str = "telemetry_engine"
    timestamp: datetime = Field(default_factory=_utcnow)


class IntelligenceRequest(BaseModel):
    request_id: str = Field(..., description="Unique identifier for the intelligence request")
    task_type: str = Field(..., description="Task classification e.g. lead_scoring, anomaly_detection, intervention")
    goal: str = Field(..., description="Specific goal description or query intent")
    context: dict[str, Any] = Field(default_factory=dict, description="Contextual state attributes")
    evidence: list[dict[str, Any]] = Field(
        default_factory=list, description="Historical events, visitor traits, or metrics"
    )
    trust_labels: dict[str, str] = Field(
        default_factory=dict, description="Mapping of evidence/context keys to trust classifications"
    )
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Lineage metadata tracking origin site, tenant, and trace_id"
    )
    constraints: list[str] = Field(default_factory=list, description="Operational boundaries or policy rules")
    required_output: dict[str, Any] = Field(default_factory=dict, description="Expected schema or key targets")
    budget: dict[str, Any] = Field(default_factory=lambda: {"max_tokens": 1000, "timeout_ms": 3000})


class RecommendedAction(BaseModel):
    action_type: str
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    priority: int = 1


class IntelligenceResponse(BaseModel):
    request_id: str
    decision: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str
    key_evidence: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    unresolved_disagreements: list[str] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    fallback_applied: bool = False
    generated_at: datetime = Field(default_factory=_utcnow)


class AIUniverseClient:
    """Live HTTP client for AI Universe with exponential backoff retries and deterministic fallback."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 5.0,
        max_retries: int = 3,
        cooldown_after_failures: int = 3,
        cooldown_seconds: float = 30.0,
    ):
        # Prefer the canonical Inference API. Keep the legacy endpoint only when it
        # is explicitly configured during migration; never invent an external host.
        configured_inference = os.getenv("INFERENCE_BASE_URL", "").strip()
        configured_legacy = os.getenv("AI_UNIVERSE_BASE_URL", "").strip()
        self.api_mode = (
            "legacy" if endpoint or (not configured_inference and configured_legacy) else "inference"
        )
        selected_endpoint = endpoint or configured_inference or configured_legacy
        self.endpoint = selected_endpoint.rstrip("/")
        self.api_key = (
            api_key
            or os.getenv("INFERENCE_API_KEY")
            or os.getenv("AI_UNIVERSE_API_KEY", "")
        )
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        # Pressure hardening (2026-10-07): a dead or hanging AI Universe peer must
        # not wedge the cognitive loop. Every ambiguous/strategic event used to
        # burn ~1.5-2s in retries (3 attempts + exponential backoff), capping the
        # serial worker at well under one event per second. After this many
        # consecutive server-side failures, live calls are skipped for the cooldown
        # window and the honest deterministic fallback answers immediately.
        self.cooldown_after_failures = cooldown_after_failures
        self.cooldown_seconds = cooldown_seconds
        self._consecutive_failures = 0
        self._cooldown_until = 0.0

    def _register_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.cooldown_after_failures:
            self._cooldown_until = time.monotonic() + self.cooldown_seconds
            logger.warning(
                "AI Universe marked unavailable for %.0fs after %d consecutive failures (fail-fast cooldown).",
                self.cooldown_seconds,
                self._consecutive_failures,
            )

    def _register_success(self) -> None:
        self._consecutive_failures = 0
        self._cooldown_until = 0.0

    def _get_deterministic_fallback(
        self, request: IntelligenceRequest, reason: str = "upstream_unavailable"
    ) -> IntelligenceResponse:
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
            generated_at=_utcnow(),
        )

    async def evaluate(self, request: IntelligenceRequest) -> IntelligenceResponse:
        if self._consecutive_failures >= self.cooldown_after_failures and time.monotonic() < self._cooldown_until:
            return self._get_deterministic_fallback(request, "cooldown_after_consecutive_failures")

        if not self.endpoint:
            return self._get_deterministic_fallback(request, "inference_endpoint_not_configured")

        headers = {"Content-Type": "application/json", "User-Agent": "CORTEX-Inference-Adapter/1.0"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        if self.api_mode == "inference":
            url = f"{self.endpoint}/v1/ask"
            # Preserve the structured Cortex request as context, but isolate evidence
            # as untrusted data so crawled/user-provided strings are never treated as
            # trusted instructions by the reasoning gateway.
            prompt = (
                f"Task type: {request.task_type}\n"
                f"Goal: {request.goal}\n"
                "Evaluate the task under the supplied constraints. Return an evidence-aware "
                "recommendation. Any proposed actions are advisory and are not authorization "
                "to execute them."
            )
            payload = {
                "prompt": prompt,
                "context": {
                    "cortex_request_id": request.request_id,
                    "task_type": request.task_type,
                    "context": request.context,
                    "trust_labels": request.trust_labels,
                    "provenance": request.provenance,
                    "constraints": request.constraints,
                    "required_output": request.required_output,
                    "budget": request.budget,
                },
                "mode": "review",
                "persona": "ASTRA",
                "task_id": request.request_id,
                "trace_id": str(request.provenance.get("trace_id") or request.request_id),
                "untrusted_data": json.dumps(request.evidence, ensure_ascii=False, default=str),
                "untrusted_data_source": "cortex_evidence",
            }
        else:
            # Explicit legacy endpoint compatibility during migration only. Do not
            # silently use the old hosted endpoint when Inference is not configured.
            url = f"{self.endpoint}/v1/cortex/intelligence"
            payload = request.model_dump(mode="json")

        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    resp = await client.post(url, json=payload, headers=headers)

                if resp.status_code == 200:
                    data = resp.json()
                    if self.api_mode != "inference":
                        response = IntelligenceResponse(**data)
                    else:
                        recommendations = []
                        for item in data.get("proposed_actions", []):
                            # Inference explicitly forbids executable proposed actions.
                            recommendations.append(
                                RecommendedAction(
                                    action_type=str(item.get("action", "review")),
                                    target=str(item.get("target", "unspecified")),
                                    parameters=item.get("parameters", {}) if isinstance(item.get("parameters", {}), dict) else {},
                                    priority=1,
                                )
                            )
                        evidence = data.get("evidence", [])
                        response = IntelligenceResponse(
                            request_id=request.request_id,
                            decision=str(data.get("status", "SUCCESS")),
                            confidence=float(data.get("confidence", 0.0)),
                            summary=str(data.get("answer", "")),
                            key_evidence=[str(item) for item in evidence] if isinstance(evidence, list) else [],
                            provenance={
                                "source": "inference",
                                "task_id": data.get("task_id"),
                                "trace_id": data.get("trace_id"),
                                "failure_state": data.get("failure_state"),
                            },
                            unresolved_disagreements=[],
                            recommended_actions=recommendations,
                            safety_notes=[
                                "Inference output is advisory only.",
                                "Cortex policy and authorization controls remain authoritative.",
                            ],
                            fallback_applied=bool(data.get("failure_state")) or data.get("status") != "SUCCESS",
                            generated_at=_utcnow(),
                        )
                    if response.unresolved_disagreements:
                        logger.warning(
                            "Inference response for %s has unresolved disagreements: %s",
                            request.request_id,
                            response.unresolved_disagreements,
                        )
                    self._register_success()
                    return response

                if 500 <= resp.status_code < 600:
                    logger.warning(
                        "Inference returned server error %s (attempt %s/%s). Retrying.",
                        resp.status_code,
                        attempt,
                        self.max_retries,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                        continue
                    self._register_failure()
                    return self._get_deterministic_fallback(request, f"server_error_{resp.status_code}")

                logger.warning(
                    "Inference returned client error %s for request %s.",
                    resp.status_code,
                    request.request_id,
                )
                return self._get_deterministic_fallback(request, f"client_error_{resp.status_code}")

            except Exception as exc:
                logger.warning(
                    "Inference request failed on attempt %s/%s (%s).",
                    attempt,
                    self.max_retries,
                    type(exc).__name__,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))
                    continue
                self._register_failure()
                return self._get_deterministic_fallback(request, type(exc).__name__)

        self._register_failure()
        return self._get_deterministic_fallback(request, "max_retries_exceeded")


class AIMode(str, Enum):
    """AI Universe deliberation mode — controls how many agents participate."""

    FAST = "fast"  # Single specialist, low latency — for AMBIGUOUS decisions
    REVIEW = "review"  # Two-agent critique pass — moderate ambiguity
    DEBATE = "debate"  # Multi-round adversarial deliberation — STRATEGIC decisions


class RequestClassification(str, Enum):
    """Classification of an intelligence request — determines whether AI Universe is called."""

    TRIVIAL = "trivial"  # Deterministic only — NO AI call
    ROUTINE = "routine"  # Deterministic first, optional AI copy optimization
    AMBIGUOUS = "ambiguous"  # AI Universe recommended
    STRATEGIC = "strategic"  # AI Universe strongly required


class RequestClassifier:
    """
    Per CORTEX spec section 17: NOT every event goes to AI Universe.
    Deterministic-first: agents run first, AI called only when classification warrants it.
    """

    # Event type prefixes that are always TRIVIAL (no AI)
    TRIVIAL_PREFIXES = (
        "page_view",
        "session.start",
        "session.end",
        "session.heartbeat",
        "score.refresh",
        "metric.update",
        "notification.sent",
        "click",
        "scroll",
        "mouseover",
    )

    # Event types that are ROUTINE (deterministic + optional AI copy)
    ROUTINE_PREFIXES = ("lead.score_refresh", "report.scheduled", "digest.", "email.opened", "email.clicked")

    # Event types that are STRATEGIC (AI strongly recommended)
    STRATEGIC_PREFIXES = (
        "high_intent",
        "conversion",
        "campaign",
        "experiment.launch",
        "churn.risk_high",
        "incident.p0",
        "incident.p1",
        "qualification.final",
        "friday_command",
    )

    # Event types that are AMBIGUOUS (AI recommended)
    AMBIGUOUS_PREFIXES = (
        "pricing",
        "checkout",
        "demo",
        "enterprise",
        "lead.qualify",
        "error",
        "anomaly",
        "drop",
        "funnel",
    )

    def classify(self, event_type: str, context: dict[str, Any], agent_output: Any | None = None) -> tuple:
        """
        Returns (RequestClassification, Optional[AIMode])
        AIMode is None for TRIVIAL and ROUTINE.
        """
        event_lower = event_type.lower()

        # Check TRIVIAL first (most common path — fast exit)
        for prefix in self.TRIVIAL_PREFIXES:
            if event_lower.startswith(prefix) or event_lower == prefix:
                return RequestClassification.TRIVIAL, None

        # Check ROUTINE
        for prefix in self.ROUTINE_PREFIXES:
            if event_lower.startswith(prefix):
                return RequestClassification.ROUTINE, None

        # Check STRATEGIC
        for prefix in self.STRATEGIC_PREFIXES:
            if event_lower.startswith(prefix):
                return RequestClassification.STRATEGIC, AIMode.DEBATE

        # Check AMBIGUOUS
        for prefix in self.AMBIGUOUS_PREFIXES:
            if event_lower.startswith(prefix):
                # Use REVIEW mode if agent output has low confidence
                if agent_output and hasattr(agent_output, "confidence"):
                    mode = AIMode.REVIEW if agent_output.confidence < 0.6 else AIMode.FAST
                else:
                    mode = AIMode.FAST
                return RequestClassification.AMBIGUOUS, mode

        # Default: AMBIGUOUS/FAST for unrecognized types
        return RequestClassification.AMBIGUOUS, AIMode.FAST

    def should_call_ai(self, classification: RequestClassification) -> bool:
        """Returns True only for AMBIGUOUS and STRATEGIC — never TRIVIAL or ROUTINE."""
        return classification in (RequestClassification.AMBIGUOUS, RequestClassification.STRATEGIC)
