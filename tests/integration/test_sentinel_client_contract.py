"""Contract tests for the outbound Sentinel security-posture client.

Sentinel used to be inbound only, and the local endpoint answered with a hardcoded 95.0 posture
when nothing had been pushed — a fabricated security metric. These tests pin the replacement
behaviour: read the real service when it is deployed, validate what it says, and label every
baseline answer as a baseline.
"""

import os
import sys
import time

import pytest

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "packages/identity/src",
    "packages/analytics/src",
    "packages/intelligence/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_integrations import SentinelClient
from cortex_integrations.peer_transport import PeerResponse

pytestmark = pytest.mark.asyncio

DEAD_PEER = "http://127.0.0.1:9"


def _stub(client, responses: dict[str, PeerResponse]) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    async def _get(url, params=None, **kw):
        calls.append(("GET", url))
        for suffix, response in responses.items():
            if url.endswith(suffix):
                return response
        return PeerResponse(ok=False, status_code=404, error=f"no stub for {url}", url=url)

    client.transport.get = _get
    return calls


async def test_unconfigured_client_is_labeled_and_never_claims_a_live_posture(monkeypatch):
    monkeypatch.delenv("SENTINEL_BASE_URL", raising=False)
    client = SentinelClient()

    assert client.live is False
    posture = await client.fetch_security_posture()

    assert posture.source == "fallback"
    assert posture.degraded is True
    assert "SENTINEL_BASE_URL is not configured" in (posture.degraded_reason or "")

    health = await client.health_check()
    assert health["status"] == "NOT_CONFIGURED"
    assert health["mode"] == "deterministic_fallback"
    assert health["peer_reachable"] is False


async def test_unreachable_sentinel_degrades_with_a_reason_and_bounded_time():
    client = SentinelClient(base_url=DEAD_PEER, api_key="contract-test-key")
    started = time.perf_counter()
    posture = await client.fetch_security_posture()
    elapsed = time.perf_counter() - started

    assert posture.source == "fallback" and posture.degraded is True
    assert "sentinel unreachable" in (posture.degraded_reason or "")
    assert elapsed < 60, f"a dead peer must not wedge the caller (took {elapsed:.1f}s)"

    health = await client.health_check()
    assert health["status"] == "DOWN" and health["peer_reachable"] is False
    assert health["mode"] == "deterministic_fallback"


async def test_live_posture_is_used_verbatim_when_it_is_internally_consistent():
    body = {
        "overall_posture_score": 82.5,
        "per_domain_scores": {"web": 90.0, "api": 75.0, "network": 100.0},
        "open_findings_by_severity": {"critical": 0, "high": 2, "medium": 5, "low": 11},
        "most_critical_finding": {"finding_id": "f-1", "title": "TLS 1.0 enabled"},
        "trend": "improving",
    }
    client = SentinelClient(base_url="http://sentinel.test", api_key="contract-test-key")
    _stub(client, {"/api/v1/friday/posture": PeerResponse(ok=True, status_code=200, body=body, url="posture")})

    posture = await client.fetch_security_posture()

    assert posture.source == "sentinel"
    assert posture.degraded is False
    assert posture.posture_score == 82.5
    assert posture.per_domain_scores["api"] == 75.0
    assert posture.open_findings_by_severity["high"] == 2
    assert posture.trend == "improving"
    assert posture.most_critical_finding["finding_id"] == "f-1"


async def test_impossible_posture_payloads_are_rejected_not_repeated():
    cases = {
        "score out of range": {"overall_posture_score": 140.0},
        "score missing": {"per_domain_scores": {"web": 90.0}},
        "domain out of range": {"overall_posture_score": 90.0, "per_domain_scores": {"web": -5.0}},
        "negative finding count": {"overall_posture_score": 90.0, "open_findings_by_severity": {"critical": -1}},
    }
    for label, body in cases.items():
        client = SentinelClient(base_url="http://sentinel.test", api_key="contract-test-key")
        _stub(client, {"/api/v1/friday/posture": PeerResponse(ok=True, status_code=200, body=body, url="posture")})

        posture = await client.fetch_security_posture()

        assert posture.source == "fallback", f"{label} must not be presented as a live posture"
        assert posture.degraded is True
        assert "validation" in (posture.degraded_reason or "")


async def test_a_perfect_score_with_open_critical_findings_is_flagged_degraded():
    body = {
        "overall_posture_score": 100.0,
        "per_domain_scores": {"web": 100.0},
        "open_findings_by_severity": {"critical": 3, "high": 4},
        "trend": "degrading",
    }
    client = SentinelClient(base_url="http://sentinel.test", api_key="contract-test-key")
    _stub(client, {"/api/v1/friday/posture": PeerResponse(ok=True, status_code=200, body=body, url="posture")})

    posture = await client.fetch_security_posture()

    assert posture.source == "sentinel", "the answer is real, it is just contradictory"
    assert posture.degraded is True
    assert "cannot both be true" in (posture.degraded_reason or "") or "treating as degraded" in (
        posture.degraded_reason or ""
    )


async def test_asset_inventory_skips_malformed_rows_and_clamps_counts():
    body = {
        "total_assets": 3,
        "assets": [
            {"target": "app.example.com", "asset_type": "domain", "status": "vulnerable", "open_finding_count": 2},
            {"asset_type": "domain", "status": "secure"},  # no target -> skipped
            {"target": "api.example.com", "asset_type": "api", "status": "critical", "open_finding_count": -4},
        ],
    }
    client = SentinelClient(base_url="http://sentinel.test", api_key="contract-test-key")
    _stub(client, {"/api/v1/friday/assets": PeerResponse(ok=True, status_code=200, body=body, url="assets")})

    assets = await client.fetch_asset_inventory()

    assert [a.target for a in assets] == ["app.example.com", "api.example.com"]
    assert assets[0].source == "sentinel" and assets[0].open_finding_count == 2
    assert assets[1].open_finding_count == 0, "a negative finding count is not evidence of anything"


async def test_asset_inventory_is_empty_rather_than_invented_when_unreachable():
    client = SentinelClient(base_url="http://sentinel.test", api_key="contract-test-key")
    _stub(client, {"/api/v1/friday/assets": PeerResponse(ok=False, status_code=503, error="boom", url="assets")})

    assert await client.fetch_asset_inventory() == []


live_only = pytest.mark.skipif(
    os.getenv("CORTEX_PEER_LIVE_TESTS", "") not in {"1", "true", "yes"},
    reason="set CORTEX_PEER_LIVE_TESTS=1 with SENTINEL_BASE_URL to run the live Sentinel round-trip",
)


@live_only
async def test_live_sentinel_round_trip():
    client = SentinelClient()
    assert client.live, "SENTINEL_BASE_URL must be configured for the live round-trip"

    health = await client.health_check()
    assert health["status"] == "UP" and health["mode"] == "live"

    posture = await client.fetch_security_posture()
    assert posture.source == "sentinel"
    assert 0.0 <= posture.posture_score <= 100.0
    assert set(posture.open_findings_by_severity) >= {"critical", "high"}

    assets = await client.fetch_asset_inventory()
    assert isinstance(assets, list)
    assert all(asset.source == "sentinel" for asset in assets)
