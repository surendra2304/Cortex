import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from .peer_transport import PeerTransport


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-intelx-client")


class CompetitorProfile(BaseModel):
    competitor_name: str
    pricing_model: str
    feature_gaps: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    market_share_tier: str = "established"  # challenger, established, dominant
    battlecard_summary: str = ""
    evidence_citations: list[str] = Field(default_factory=list)
    # Provenance: "intelx" when this came from the real service, "fallback" otherwise.
    source: str = "fallback"
    degraded: bool = False
    degraded_reason: str | None = None
    research_run_id: str | None = None
    findings_confidence: float | None = None


class MarketSignal(BaseModel):
    signal_id: str
    industry: str
    trend_title: str
    impact_level: str  # low, medium, high, strategic
    summary: str
    recommended_positioning: str
    trending_topics: list[str] = Field(default_factory=list)
    citations: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=_utcnow)
    source: str = "fallback"
    degraded: bool = False
    degraded_reason: str | None = None
    research_run_id: str | None = None


class IntelXClient:
    """
    IntelX Autonomous Market & Competitive Intelligence Client:
    - Queries IntelX for competitive intelligence on alternatives (pricing, feature gaps, battlecards)
    - Retrieves real-time market trends, industry regulations, and high-velocity topics
    - Feeds structured insights into GrowthAgent, SalesAgent, and Cortex Personalization
    """

    def __init__(
        self,
        api_key: str | None = None,
        mock_mode: bool | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ):
        self.api_key = api_key or os.getenv("INTELX_API_KEY", "mock_intelx_key")
        self.transport = PeerTransport("intelx", base_url=base_url, api_key=api_key, timeout_seconds=timeout_seconds)
        # ``mock_mode`` stays for backward compatibility, but it now means what it says:
        # True forces fixtures, False requires the live service, None decides by configuration.
        if mock_mode is True:
            self.transport.base_url = None
        self.mock_mode = mock_mode if mock_mode is not None else not self.transport.configured
        self.research_cache: dict[str, Any] = {}

    @property
    def live(self) -> bool:
        """True when this client will talk to a real IntelX deployment."""
        return self.transport.configured and not self.mock_mode

    async def fetch_competitor_intelligence(self, competitor_name: str) -> CompetitorProfile:
        """Competitive analysis from IntelX when deployed; deterministic fallback otherwise."""
        logger.info(f"Querying IntelX competitive intelligence for '{competitor_name}'")

        if self.live:
            live_profile = await self._live_competitor_intelligence(competitor_name)
            if live_profile is not None:
                return live_profile

        return self._offline_competitor_intelligence(competitor_name)

    def _offline_competitor_intelligence(self, competitor_name: str, reason: str | None = None) -> CompetitorProfile:
        """Deterministic, documented fallback (identical to the pre-transport behaviour)."""
        norm_name = competitor_name.lower()
        if "datadog" in norm_name or "dynatrace" in norm_name:
            return CompetitorProfile(
                competitor_name=competitor_name.capitalize(),
                pricing_model="High-tier seat & host-based licensing with steep overage costs",
                feature_gaps=[
                    "Lack of autonomous real-time website personalization",
                    "No integrated 10-phase closed-loop agentic deliberation",
                    "Heavy complex agent deployment vs zero-friction JS SDK",
                ],
                strengths=["Extensive legacy infrastructure APM metric integrations"],
                market_share_tier="dominant",
                battlecard_summary="Emphasize Cortex's sub-100ms real-time autonomous cognitive loops, zero-ops deployment, and integrated AI Universe deliberation without per-seat tax.",
                degraded=reason is not None,
                degraded_reason=reason,
                evidence_citations=[
                    "https://intelx.dev/research/observability-market-2026",
                    "https://intelx.dev/pricing-benchmarks/apm-saas",
                ],
            )
        elif "segment" in norm_name or "heap" in norm_name:
            return CompetitorProfile(
                competitor_name=competitor_name.capitalize(),
                pricing_model="Event-volume tiers with expensive enterprise add-ons",
                feature_gaps=[
                    "Data pipeline only — no autonomous agents acting on telemetry",
                    "Lacks built-in DevSecOps and Sentinel security incident coordination",
                    "No multi-agent adversarial debate deliberation",
                ],
                strengths=["Established CDP destination ecosystem"],
                market_share_tier="established",
                battlecard_summary="Position Cortex not just as telemetry pipe, but as active cognitive brain that autonomously intervenes and closes conversions.",
                evidence_citations=["https://intelx.dev/research/cdp-evolution-agentic"],
            )
        else:
            return CompetitorProfile(
                competitor_name=competitor_name.capitalize(),
                pricing_model="Standard SaaS subscription",
                feature_gaps=[
                    "No autonomous 10-phase cognitive action loop",
                    "Static rule engine instead of AI Universe multi-agent debate",
                ],
                strengths=["Broad brand recognition"],
                market_share_tier="challenger",
                battlecard_summary=f"Highlight Cortex's full closed-loop learning and explainable predictive scoring over {competitor_name}.",
                evidence_citations=[f"https://intelx.dev/research/{norm_name}-comparison"],
                degraded=reason is not None,
                degraded_reason=reason,
            )

    # ── live IntelX (FRIDAY delegation contract) ─────────────────────────────
    async def _delegate_research(
        self,
        question: str,
        domain_hint: str = "competitive",
        depth: str = "quick_scan",
        max_sources: int = 10,
        timeout_seconds: float = 30.0,
    ) -> tuple[str | None, str | None]:
        """Submit a research delegation and return (run_id, error).

        Sends the full FRIDAY research contract IntelX validates: query_scope, source_policy,
        time_budget and document_budget are mandatory, not optional extras.
        """
        payload = {
            "friday_request_id": f"cortex_{uuid.uuid4().hex[:12]}",
            "question": question,
            "action": "research",
            "context": {"requesting_system": "friday", "priority": "normal", "domain_hint": domain_hint},
            "depth": depth,
            "budget": {"max_sources": max_sources, "max_time_minutes": max(1, int(timeout_seconds // 60))},
            "query_scope": {"query": question, "domain": domain_hint, "depth": depth, "time_horizon": "1y"},
            "source_policy": {
                "allowed_tiers": ["TIER_1", "TIER_2", "TIER_3", "STANDARD", "HIGH"],
                "block_low_reliability": True,
                "min_credibility_score": 0.4,
            },
            "time_budget": {"max_time_minutes": max(1, int(timeout_seconds // 60))},
            "document_budget": {"max_documents": max_sources, "max_chunks_per_doc": 3},
        }
        response = await self.transport.post("/api/v1/friday/delegate", payload)
        if not response.ok:
            return None, response.detail
        run_id = response.body.get("intelx_run_id") or response.body.get("run_id")
        if not run_id:
            return None, f"peer accepted the delegation but returned no run id: {response.body}"
        return str(run_id), None

    async def _await_run(self, run_id: str, timeout_seconds: float = 30.0) -> tuple[dict[str, Any] | None, str | None]:
        """Poll a research run until it reaches a terminal state."""
        deadline = asyncio.get_event_loop().time() + timeout_seconds
        terminal = {"COMPLETED", "FAILED", "CANCELLED", "PARTIAL", "BLOCKED"}
        last_status = "UNKNOWN"
        while asyncio.get_event_loop().time() < deadline:
            response = await self.transport.get(f"/api/v1/friday/research/{run_id}")
            if not response.ok:
                return None, response.detail
            last_status = str(response.body.get("status", "")).upper()
            if last_status in terminal:
                return response.body, None
            await asyncio.sleep(1.0)
        return None, f"research run {run_id} did not finish within {timeout_seconds:.0f}s (last status {last_status})"

    async def _live_competitor_intelligence(self, competitor_name: str) -> CompetitorProfile | None:
        question = (
            f"What is the pricing model, feature gaps and market positioning of {competitor_name} "
            f"for a website operations intelligence platform in 2026?"
        )
        run_id, error = await self._delegate_research(question, domain_hint="competitive")
        if run_id is None:
            logger.warning("IntelX delegation failed (%s); using the deterministic fallback", error)
            return self._offline_competitor_intelligence(competitor_name, reason=f"intelx delegation failed: {error}")

        status, error = await self._await_run(run_id)
        if status is None:
            logger.warning("IntelX run %s unusable (%s); using the deterministic fallback", run_id, error)
            return self._offline_competitor_intelligence(competitor_name, reason=f"intelx run {run_id}: {error}")

        findings_response = await self.transport.get(f"/api/v1/friday/research/{run_id}/findings")
        findings = findings_response.body.get("findings", []) if findings_response.ok else []
        statements = [str(f.get("statement", "")).strip() for f in findings if f.get("statement")]
        citations = [c for f in findings for c in (f.get("citations") or [])]
        confidences = [float(f.get("confidence_score") or 0.0) for f in findings]
        confidence = round(max(confidences), 3) if confidences else 0.0

        report_text = ""
        report_response = await self.transport.get(f"/api/v1/friday/research/{run_id}/report")
        if report_response.ok:
            report_text = str(
                report_response.body.get("markdown")
                or report_response.body.get("report")
                or report_response.body.get("summary")
                or ""
            )

        evidenced = [f for f in findings if int(f.get("evidence_count") or 0) > 0]
        # "Insufficient evidence to answer ..." is an honest answer from IntelX, but it is not
        # competitor intelligence. Presenting it as a battlecard would be worse than saying we
        # fell back, so require at least one evidenced finding (or a real confidence score).
        if not statements or (not evidenced and (max(confidences) if confidences else 0.0) < 0.3):
            return self._offline_competitor_intelligence(
                competitor_name,
                reason=(
                    f"intelx run {run_id} produced no evidenced findings "
                    f"(status={status.get('status')}, best confidence={confidence})"
                ),
            )

        return CompetitorProfile(
            competitor_name=competitor_name,
            pricing_model=self._extract_pricing(statements) or "Not disclosed in retrieved evidence",
            feature_gaps=[s for s in statements[:5]],
            strengths=[],
            market_share_tier="established",
            battlecard_summary=(report_text or statements[0])[:1200],
            evidence_citations=[self._citation_label(c) for c in citations[:10]],
            source="intelx",
            degraded=confidence < 0.4,
            degraded_reason=None if confidence >= 0.4 else f"low evidence confidence ({confidence})",
            research_run_id=run_id,
            findings_confidence=confidence,
        )

    @staticmethod
    def _citation_label(citation: Any) -> str:
        """Render an IntelX citation for humans.

        IntelX returns citation objects (``{"url": ..., "title": ...}``), not bare strings;
        ``str(dict)`` produces a Python repr and a list[str] field rejected them outright,
        which crashed the live path as soon as a run had one real citation.
        """
        if isinstance(citation, dict):
            title = str(citation.get("title") or "").strip()
            url = str(citation.get("url") or citation.get("source_url") or "").strip()
            if title and url:
                return f"{title} — {url}"
            return title or url or str(citation)
        return str(citation)

    @staticmethod
    def _extract_pricing(statements: list[str]) -> str | None:
        for statement in statements:
            lowered = statement.lower()
            if any(term in lowered for term in ("pricing", "price", "per seat", "subscription", "$")):
                return statement[:400]
        return None

    async def fetch_market_signals(self, industry: str = "saas_devops") -> list[MarketSignal]:
        """Industry signals from IntelX when deployed; deterministic fallback otherwise."""
        if self.live:
            live = await self._live_market_signals(industry)
            if live is not None:
                return live
        return self._offline_market_signals(industry)

    async def _live_market_signals(self, industry: str) -> list[MarketSignal] | None:
        question = f"What are the dominant market trends and buyer priorities in {industry} for 2026?"
        run_id, error = await self._delegate_research(question, domain_hint="market")
        if run_id is None:
            logger.warning("IntelX market delegation failed (%s); using the deterministic fallback", error)
            return None
        status, error = await self._await_run(run_id)
        if status is None:
            logger.warning("IntelX market run %s unusable (%s)", run_id, error)
            return None
        findings_response = await self.transport.get(f"/api/v1/friday/research/{run_id}/findings")
        findings = findings_response.body.get("findings", []) if findings_response.ok else []
        signals: list[MarketSignal] = []
        for index, finding in enumerate(findings):
            statement = str(finding.get("statement", "")).strip()
            if not statement:
                continue
            confidence = float(finding.get("confidence_score") or 0.0)
            # Same rule as the battlecard path: "Insufficient evidence to answer" is an honest
            # answer, but it is not a market signal. Anything unevidenced and low-confidence is
            # dropped so the caller sees the documented fallback instead.
            if int(finding.get("evidence_count") or 0) == 0 and confidence < 0.3:
                continue
            signals.append(
                MarketSignal(
                    signal_id=str(finding.get("finding_id") or f"sig_{run_id}_{index}"),
                    industry=industry,
                    trend_title=statement[:120],
                    impact_level="high" if confidence >= 0.6 else "medium" if confidence >= 0.4 else "low",
                    summary=statement[:600],
                    recommended_positioning="Validate against Cortex's deterministic-first, closed-loop positioning.",
                    trending_topics=[],
                    citations=[self._citation_label(c) for c in (finding.get("citations") or [])][:5],
                    source="intelx",
                    degraded=confidence < 0.4,
                    degraded_reason=None if confidence >= 0.4 else f"low evidence confidence ({confidence})",
                    research_run_id=run_id,
                )
            )
        return signals or None

    def _offline_market_signals(self, industry: str = "saas_devops") -> list[MarketSignal]:
        """Deterministic, documented fallback."""
        return [
            MarketSignal(
                signal_id="sig_mkt_01",
                industry=industry,
                trend_title="Surge in Autonomous Agentic Operations Adoption",
                impact_level="strategic",
                summary="Enterprises are rapidly moving away from passive APM dashboards toward autonomous agentic intervention systems that close loops in <100ms.",
                recommended_positioning="Lead with 'Deterministic First + AI Universe Multi-Agent Deliberation' in all top-of-funnel CTAs and pricing pages.",
                trending_topics=[
                    "Agentic Workflows",
                    "Closed-Loop Telemetry",
                    "Autonomous Incident Remediation",
                    "Real-Time DevSecOps",
                ],
                citations=["https://intelx.dev/reports/agentic-devops-trend-2026"],
            ),
            MarketSignal(
                signal_id="sig_mkt_02",
                industry=industry,
                trend_title="Heightened Data Sovereignty & GDPR Subject Erasure Audits",
                impact_level="high",
                summary="European and US enterprises require verifiable one-way PII masking and automated Art. 17 hard erasure before installing third-party browser SDKs.",
                recommended_positioning="Highlight Cortex's zero-plaintext PII policy, automated GDPR exports, and 7-year tamper-evident audit logs.",
                trending_topics=[
                    "GDPR Article 17 Automation",
                    "Client-Side PII Redaction",
                    "Tamper-Evident Hash Audit",
                ],
                citations=["https://intelx.dev/compliance/privacy-regulations-2026"],
            ),
        ]

    async def health_check(self) -> dict[str, Any]:
        """Probe the real service when one is configured; report the mode honestly otherwise."""
        if self.transport.configured:
            response = await self.transport.health()
            return {
                "status": "UP" if response.ok else "DOWN",
                # ``mode`` answers "what is Cortex actually using?": a configured-but-unreachable
                # IntelX still serves the deterministic fallback, and saying "live" would be a lie.
                "mode": "live" if response.ok else "deterministic_fallback",
                "peer_reachable": response.ok,
                "service": "intelx",
                "base_url": self.transport.base_url,
                "research_only": True,
                "evidence_citations_enabled": response.ok,
                "detail": response.detail,
                "timestamp": _utcnow().isoformat(),
            }
        return {
            # Not "UP": nothing was probed because no deployment was configured. Reporting UP
            # here is the fake-health pattern this client exists to avoid.
            "status": "NOT_CONFIGURED",
            "service": "intelx",
            "mode": "deterministic_fallback",
            "peer_reachable": False,
            "research_only": True,
            "evidence_citations_enabled": False,
            "detail": "INTELX_BASE_URL is not configured; answers come from documented fixtures",
            "timestamp": _utcnow().isoformat(),
        }
