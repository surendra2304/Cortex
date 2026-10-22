"""Sentinel security-posture client (outbound).

Cortex's Sentinel integration was inbound only: Sentinel could push findings into
``POST /v1/sentinel/findings``, but Cortex could never *ask* Sentinel anything, so "Cortex
consults the security shield" was not a real capability. The ``/v1/sentinel/findings``
endpoint then answered from this process's own memory with a hardcoded ``95.0`` posture when
nothing had been pushed — a fabricated number presented as a security metric.

This client reads the real service through the shared :mod:`peer_transport`, and like the
IntelX and Futuris clients it never launders a fallback as live data:

* ``source`` is ``"sentinel"`` only when the deployment answered;
* ``degraded`` with a reason whenever Cortex used its documented baseline instead;
* posture answers are sanity-checked (scores in 0..100, non-negative counts) and an
  impossible combination — a perfect score with open critical findings — is reported as
  degraded rather than repeated as fact.

Read-only by construction: this client issues GETs (posture, assets, health). It never asks
Sentinel to scan, block, or execute anything, so Cortex cannot use it to escape its own
authorization policy.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from cortex_integrations.peer_transport import PeerTransport

logger = logging.getLogger("cortex-sentinel-client")


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


class SecurityPosture(BaseModel):
    """Security posture as reported by Sentinel, or the documented baseline."""

    posture_score: float
    per_domain_scores: dict[str, float] = Field(default_factory=dict)
    open_findings_by_severity: dict[str, int] = Field(default_factory=dict)
    most_critical_finding: dict[str, Any] | None = None
    trend: str = "stable"  # improving | stable | degrading
    source: str = "fallback"  # "sentinel" when read from the real service
    degraded: bool = False
    degraded_reason: str | None = None


class AssetRecord(BaseModel):
    """One asset from Sentinel's inventory."""

    target: str
    asset_type: str
    status: str  # secure | vulnerable | critical | unscanned
    open_finding_count: int = 0
    last_assessed_at: str | None = None
    source: str = "fallback"
    degraded: bool = False
    degraded_reason: str | None = None


class SentinelClient:
    """Read Sentinel's security posture and asset inventory when it is deployed."""

    def __init__(
        self,
        api_key: str | None = None,
        mock_mode: bool | None = None,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ):
        self.api_key = api_key or os.getenv("SENTINEL_API_KEY", "mock_sentinel_key")
        self.transport = PeerTransport("sentinel", base_url=base_url, api_key=api_key, timeout_seconds=timeout_seconds)
        if mock_mode is True:
            self.transport.base_url = None
        self.mock_mode = mock_mode if mock_mode is not None else not self.transport.configured

    @property
    def live(self) -> bool:
        """True when this client will ask a real Sentinel deployment for posture."""
        return self.transport.configured and not self.mock_mode

    async def fetch_security_posture(self) -> SecurityPosture:
        """Current posture from Sentinel when deployed; deterministic baseline otherwise."""
        if self.live:
            response = await self.transport.get("/api/v1/friday/posture")
            if response.ok:
                posture = self._parse_posture(response.body)
                if posture is not None:
                    return posture
                logger.warning("Sentinel returned an impossible posture payload; using the baseline")
                return self._offline_posture(reason=f"sentinel posture failed validation: {response.body}")
            logger.warning("Sentinel posture probe failed (%s); using the baseline", response.detail)
            return self._offline_posture(reason=f"sentinel unreachable: {response.detail}")
        return self._offline_posture(reason="SENTINEL_BASE_URL is not configured")

    @staticmethod
    def _parse_posture(body: dict[str, Any]) -> SecurityPosture | None:
        """Validate a posture payload; return None when it cannot be true."""
        try:
            score = float(body.get("overall_posture_score"))
        except (TypeError, ValueError):
            return None
        if not 0.0 <= score <= 100.0:
            return None

        raw_domains = body.get("per_domain_scores") or {}
        per_domain: dict[str, float] = {}
        for domain, value in raw_domains.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return None
            if not 0.0 <= numeric <= 100.0:
                return None
            per_domain[str(domain)] = numeric

        severity: dict[str, int] = {}
        for level, count in (body.get("open_findings_by_severity") or {}).items():
            try:
                numeric_count = int(count)
            except (TypeError, ValueError):
                return None
            if numeric_count < 0:
                return None
            severity[str(level)] = numeric_count

        degraded_reason = None
        degraded = False
        if score >= 100.0 and (severity.get("critical", 0) > 0 or severity.get("high", 0) > 0):
            # A perfect score with open critical/high findings cannot both be true.
            degraded = True
            degraded_reason = (
                f"sentinel reports posture {score} with open critical/high findings {severity}; treating as degraded"
            )

        return SecurityPosture(
            posture_score=score,
            per_domain_scores=per_domain,
            open_findings_by_severity=severity,
            most_critical_finding=body.get("most_critical_finding"),
            trend=str(body.get("trend") or "stable"),
            source="sentinel",
            degraded=degraded,
            degraded_reason=degraded_reason,
        )

    async def fetch_asset_inventory(self) -> list[AssetRecord]:
        """Assets Sentinel knows about; empty list when nothing can be read."""
        if not self.live:
            return []
        response = await self.transport.get("/api/v1/friday/assets")
        if not response.ok:
            logger.warning("Sentinel asset inventory probe failed (%s)", response.detail)
            return []
        records: list[AssetRecord] = []
        for item in response.body.get("assets") or []:
            if not isinstance(item, dict) or not item.get("target"):
                continue
            try:
                finding_count = int(item.get("open_finding_count") or 0)
            except (TypeError, ValueError):
                finding_count = 0
            records.append(
                AssetRecord(
                    target=str(item["target"]),
                    asset_type=str(item.get("asset_type") or "unknown"),
                    status=str(item.get("status") or "unscanned"),
                    open_finding_count=max(0, finding_count),
                    last_assessed_at=item.get("last_assessed_at"),
                    source="sentinel",
                    degraded=False,
                    degraded_reason=None,
                )
            )
        return records

    def _offline_posture(self, *, reason: str) -> SecurityPosture:
        """Documented baseline: a clean, unattributed posture, explicitly labelled."""
        return SecurityPosture(
            posture_score=100.0,
            per_domain_scores={"web": 100.0, "api": 100.0, "network": 100.0, "cloud": 100.0, "endpoint": 100.0},
            open_findings_by_severity={"critical": 0, "high": 0, "medium": 0, "low": 0},
            most_critical_finding=None,
            trend="stable",
            source="fallback",
            degraded=True,
            degraded_reason=reason,
        )

    async def health_check(self) -> dict[str, Any]:
        """Honest liveness: report exactly what was probed and what Cortex will use."""
        base = {
            "service": "sentinel",
            "read_only": True,
            "timestamp": _utcnow().isoformat(),
        }
        if self.transport.configured:
            response = await self.transport.health()
            return {
                **base,
                "status": "UP" if response.ok else "DOWN",
                "mode": "live" if response.ok else "deterministic_fallback",
                "peer_reachable": response.ok,
                "base_url": self.transport.base_url,
                "detail": response.detail,
            }
        return {
            **base,
            # Not "UP": nothing was probed because no deployment was configured.
            "status": "NOT_CONFIGURED",
            "mode": "deterministic_fallback",
            "peer_reachable": False,
            "detail": "SENTINEL_BASE_URL is not configured; answers come from documented baselines",
        }
