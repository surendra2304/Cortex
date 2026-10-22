"""Contract tests for the real FRIDAY-Universe peer integrations (IntelX, Futuris).

These tests exist because Cortex's peer clients once had a ``mock_mode`` flag that was
never on any code path which opened a socket: "IntelX integration" could neither fail
nor work. The fixtures below are *captured payloads* from the live peer services
(IntelX on :8102, Futuris on :8101) rather than invented shapes, and they pin the
contract Cortex must honour:

* an unreachable peer degrades to the deterministic fallback and says so;
* a peer that answers with physically impossible numbers is not laundered into a plan;
* a peer that honestly answers INSUFFICIENT_DATA is reported as a fallback, not a forecast;
* a usable peer answer keeps its provenance (remote id, confidence label, per-step intervals);
* the request envelopes Cortex sends satisfy the peers' own validation contracts.

The live round-trips against real deployments are opt-in (``CORTEX_PEER_LIVE_TESTS=1``)
so the suite stays hermetic by default.
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

from cortex_integrations import FuturisClient, IntelXClient
from cortex_integrations.peer_transport import PeerResponse

pytestmark = pytest.mark.asyncio

# A port nothing listens on: connection refused, exercised through the real transport.
DEAD_PEER = "http://127.0.0.1:9"

# ---------------------------------------------------------------------------
# Captured peer payloads (verbatim shapes from the live services).
# ---------------------------------------------------------------------------

# Futuris, no telemetry supplied: it forecasts its own synthetic series and reports
# MEDIUM confidence with a rate interval spanning negative throughput.
FUTURIS_THIN_DATA_RESULT = {
    "futuris_forecast_id": "91655c6b-1111-4222-8333-444455556666",
    "confidence": "MEDIUM",
    "status": "active",
    "calibration_score": 0.042,
    "prediction": {"point_estimate": 1527.11, "lower_bound": -5860.72, "upper_bound": 10886.15},
    "probability_distribution": {"p10": -5860.72, "p90": 10886.15, "exceedance_probability": 0.856},
    "intervals": [{"step": 1.0, "lower": 1377.61, "central": 1819.65, "upper": 2261.69}],
    "prediction_is_not_authorization": True,
    "executable_commands": [],
}

# Futuris, stale telemetry: it refuses rather than guessing.
FUTURIS_BLOCKED_RESULT = {
    "futuris_forecast_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    "confidence": "INSUFFICIENT_DATA",
    "status": "BLOCKED",
    "calibration_score": 0.0,
    "calibration_metrics": {"error": "stale_data", "detail": "69178.6s old (exceeds threshold of 3600.0s)"},
    "prediction": {"point_estimate": 0.0, "lower_bound": 0.0, "upper_bound": 0.0},
    "model_metadata": {"blocked_reason": "stale_data_detected"},
    "intervals": [],
    "prediction_is_not_authorization": True,
    "executable_commands": [],
}


def _capture_transport(client):
    """Patch the transport methods in place, returning the recorded call list."""
    calls: list[tuple[str, str, dict]] = []

    async def _record(method, url, payload=None):
        calls.append((method, url, payload or {}))
        return PeerResponse(ok=False, status_code=503, error="not stubbed", url=url)

    client.transport.post = lambda url, payload=None, **kw: _record("POST", url, payload)
    client.transport.get = lambda url, params=None, **kw: _record("GET", url, params)
    return calls


def _stub(client, responses: dict[str, PeerResponse]):
    """Route transport calls through a {url-suffix: PeerResponse} table."""
    calls: list[tuple[str, str, dict]] = []

    async def _post(url, payload=None, **kw):
        calls.append(("POST", url, payload or {}))
        for suffix, response in responses.items():
            if url.endswith(suffix):
                return response
        return PeerResponse(ok=False, status_code=404, error=f"no stub for POST {url}", url=url)

    async def _get(url, params=None, **kw):
        calls.append(("GET", url, params or {}))
        for suffix, response in responses.items():
            if url.endswith(suffix):
                return response
        return PeerResponse(ok=False, status_code=404, error=f"no stub for GET {url}", url=url)

    client.transport.post = _post
    client.transport.get = _get
    return calls


# ---------------------------------------------------------------------------
# 1. Unconfigured: deterministic behaviour, honestly labelled.
# ---------------------------------------------------------------------------


async def test_clients_without_a_configured_peer_are_explicitly_not_live(monkeypatch):
    for var in ("FUTURIS_BASE_URL", "INTELX_BASE_URL"):
        monkeypatch.delenv(var, raising=False)

    futuris = FuturisClient()
    intelx = IntelXClient()

    assert futuris.live is False and intelx.live is False
    assert futuris.mock_mode is True and intelx.mock_mode is True

    forecast = await futuris.predict_traffic("site_main")
    assert forecast.source == "fallback"
    assert forecast.degraded is False, "a documented deterministic baseline is not a degraded peer call"

    health = await futuris.health_check()
    assert health["mode"] == "deterministic_fallback"
    assert health["status"] == "NOT_CONFIGURED", "an unprobed peer must never be reported UP"
    assert health["peer_reachable"] is False


# ---------------------------------------------------------------------------
# 2. Peer configured but unreachable: fallback, degraded, and a stated reason.
# ---------------------------------------------------------------------------


async def test_futuris_peer_down_degrades_instead_of_pretending():
    client = FuturisClient(base_url=DEAD_PEER, api_key="contract-test-key")
    assert client.live is True

    started = time.perf_counter()
    forecast = await client.predict_traffic("site_load", 24)
    elapsed = time.perf_counter() - started

    assert forecast.source == "fallback"
    assert forecast.degraded is True
    assert forecast.degraded_reason and "futuris" in forecast.degraded_reason.lower()
    assert forecast.forecast_id_remote is None
    assert elapsed < 60, f"a dead peer must not wedge the caller (took {elapsed:.1f}s)"

    baseline = client._offline_traffic("site_load", 24)
    # Shape parity, ignoring the per-call identifiers/timestamps that always differ.
    volatile = {"forecast_id", "data_points", "degraded", "degraded_reason"}
    assert forecast.model_dump(exclude=volatile) == baseline.model_dump(
        exclude=volatile
    ), "degradation must not change the documented fallback numbers"
    assert [dp.predicted_value for dp in forecast.data_points] == [dp.predicted_value for dp in baseline.data_points]

    health = await client.health_check()
    assert health["status"] == "DOWN"
    assert health["peer_reachable"] is False
    assert health["mode"] == "deterministic_fallback", "a down peer means Cortex is using the fallback"


async def test_intelx_peer_down_degrades_instead_of_pretending():
    client = IntelXClient(base_url=DEAD_PEER, api_key="contract-test-key")
    assert client.live is True

    started = time.perf_counter()
    profile = await client.fetch_competitor_intelligence("Datadog")
    signals = await client.fetch_market_signals("saas_devops")
    elapsed = time.perf_counter() - started

    assert profile.source == "fallback" and profile.degraded is True
    assert profile.degraded_reason and "intelx" in profile.degraded_reason.lower()
    assert profile.research_run_id is None
    assert elapsed < 120, f"a dead peer must not wedge the caller (took {elapsed:.1f}s)"
    assert signals and all(s.source != "intelx" for s in signals)

    health = await client.health_check()
    assert health["status"] == "DOWN"
    assert health["peer_reachable"] is False
    assert health["mode"] == "deterministic_fallback", "a down peer means Cortex is using the fallback"


# ---------------------------------------------------------------------------
# 3. Peer answers: impossible numbers are rejected, not laundered.
# ---------------------------------------------------------------------------


async def test_futuris_impossible_bounds_are_rejected_not_presented_as_a_plan():
    client = FuturisClient(base_url="http://futuris.test", api_key="contract-test-key")
    _stub(
        client,
        {
            "/v1/friday/delegate": PeerResponse(
                ok=True,
                status_code=200,
                body={"result": FUTURIS_THIN_DATA_RESULT},
                url="http://futuris.test/v1/friday/delegate",
            )
        },
    )

    forecast = await client.predict_traffic("site_load", 24)

    assert forecast.source == "fallback", "a rate interval spanning -5860 rps is not a forecast"
    assert forecast.degraded is True
    assert "not actionable" in (forecast.degraded_reason or "")
    assert forecast.peak_predicted_rps != 10886.15
    assert forecast.forecast_id_remote is None


async def test_futuris_insufficient_data_is_an_honest_fallback():
    client = FuturisClient(base_url="http://futuris.test", api_key="contract-test-key")
    _stub(
        client,
        {
            "/v1/friday/delegate": PeerResponse(
                ok=True,
                status_code=200,
                body={"result": FUTURIS_BLOCKED_RESULT},
                url="http://futuris.test/v1/friday/delegate",
            )
        },
    )

    forecast = await client.predict_traffic("site_load", 24)

    assert forecast.source == "fallback"
    assert forecast.degraded is True
    assert "INSUFFICIENT_DATA" in (forecast.degraded_reason or "")
    assert forecast.peak_predicted_rps > 0, "the deterministic baseline still produces a usable number"


async def test_futuris_usable_forecast_keeps_every_interval_and_its_provenance():
    intervals = [{"step": float(i), "lower": 200.0 + i, "central": 210.0 + i, "upper": 240.0 + i} for i in range(1, 25)]
    result = {
        "futuris_forecast_id": "11111111-2222-3333-4444-555555555555",
        "confidence": "HIGH",
        "status": "COMPLETED",
        "calibration_score": 0.18,
        "prediction": {"point_estimate": 210.0, "lower_bound": 200.0, "upper_bound": 265.0},
        "intervals": intervals,
        "prediction_is_not_authorization": True,
        "executable_commands": [],
    }
    client = FuturisClient(base_url="http://futuris.test", api_key="contract-test-key")
    _stub(
        client,
        {
            "/v1/friday/delegate": PeerResponse(
                ok=True, status_code=200, body={"result": result}, url="http://futuris.test/v1/friday/delegate"
            )
        },
    )

    forecast = await client.predict_traffic(
        "site_load", 24, telemetry=[{"timestamp": "2026-10-06T00:00:00Z", "value": 205.0}]
    )

    assert forecast.source == "futuris"
    assert forecast.degraded is False and forecast.degraded_reason is None
    assert forecast.confidence_label == "HIGH"
    assert forecast.forecast_id_remote == "11111111-2222-3333-4444-555555555555"
    assert len(forecast.data_points) == 24, "per-step intervals are a better capacity plan than one point"
    assert forecast.data_points[-1].predicted_value == 234.0
    assert forecast.peak_predicted_rps == pytest.approx(
        265.0
    ), "peak must take the most pessimistic of the point estimate, its upper bound and every interval"
    assert forecast.prediction_is_not_authorization is True


async def test_futuris_request_is_an_advisory_forecast_envelope():
    client = FuturisClient(base_url="http://futuris.test", api_key="contract-test-key")
    calls = _stub(
        client,
        {
            "/v1/friday/delegate": PeerResponse(
                ok=True,
                status_code=200,
                body={"result": {**FUTURIS_BLOCKED_RESULT, "status": "INSUFFICIENT_DATA"}},
                url="http://futuris.test/v1/friday/delegate",
            )
        },
    )
    telemetry = [{"timestamp": "2026-10-06T00:00:00Z", "value": 10.0 + i} for i in range(6)]

    await client.predict_traffic("site_load", 24, telemetry=telemetry)

    method, url, payload = calls[-1]
    assert method == "POST" and url.endswith("/v1/friday/delegate")
    assert payload["action"] == "forecast"
    assert payload["source_agent"] == "cortex" and payload["target_agent"] == "futuris"
    assert payload["payload"]["telemetry_data"] == telemetry, "caller telemetry must reach the peer"

    forbidden = {"execute", "mitigate", "scale", "deploy", "run_command", "bash", "command"}
    wire = str(payload).lower()
    assert not any(f'"{token}"' in wire or f"'{token}'" in wire for token in forbidden)


# ---------------------------------------------------------------------------
# 4. IntelX: "insufficient evidence" is not a battlecard.
# ---------------------------------------------------------------------------


async def test_intelx_uncited_findings_are_not_dressed_up_as_intelligence():
    client = IntelXClient(base_url="http://intelx.test", api_key="contract-test-key")
    _stub(
        client,
        {
            "/api/v1/friday/delegate": PeerResponse(
                ok=True,
                status_code=201,
                body={"intelx_run_id": "run-uncited"},
                url="http://intelx.test/api/v1/friday/delegate",
            ),
            "/research/run-uncited": PeerResponse(
                ok=True,
                status_code=200,
                body={"status": "COMPLETED"},
                url="http://intelx.test/api/v1/friday/research/run-uncited",
            ),
            "/findings": PeerResponse(
                ok=True,
                status_code=200,
                body={
                    "findings": [
                        {
                            "statement": "Insufficient evidence to answer objective.",
                            "evidence_count": 0,
                            "confidence_score": 0.1,
                            "citations": [],
                        }
                    ]
                },
                url="http://intelx.test/findings",
            ),
            "/report": PeerResponse(ok=False, status_code=404, error="no report", url="http://intelx.test/report"),
        },
    )

    profile = await client.fetch_competitor_intelligence("Datadog")

    assert profile.source == "fallback"
    assert profile.degraded is True
    assert "no evidenced findings" in (profile.degraded_reason or "")
    assert profile.battlecard_summary != "Insufficient evidence to answer objective."


async def test_intelx_evidenced_findings_are_used_with_citations():
    findings = [
        {
            "statement": "Datadog pricing starts at $15 per host per month with annual billing.",
            "evidence_count": 3,
            "confidence_score": 0.82,
            "citations": [{"url": "https://example.com/pricing", "title": "Datadog Pricing"}],
        },
        {
            "statement": "Datadog's observability bundle includes APM and log management tiers.",
            "evidence_count": 2,
            "confidence_score": 0.74,
            "citations": [{"url": "https://example.com/docs", "title": "Datadog Docs"}],
        },
    ]
    client = IntelXClient(base_url="http://intelx.test", api_key="contract-test-key")
    calls = _stub(
        client,
        {
            "/api/v1/friday/delegate": PeerResponse(
                ok=True,
                status_code=201,
                body={"intelx_run_id": "run-cited"},
                url="http://intelx.test/api/v1/friday/delegate",
            ),
            "/research/run-cited": PeerResponse(
                ok=True,
                status_code=200,
                body={"status": "COMPLETED"},
                url="http://intelx.test/api/v1/friday/research/run-cited",
            ),
            "/findings": PeerResponse(
                ok=True, status_code=200, body={"findings": findings}, url="http://intelx.test/findings"
            ),
            "/report": PeerResponse(
                ok=True, status_code=200, body={"markdown": "# Datadog battlecard"}, url="http://intelx.test/report"
            ),
        },
    )

    profile = await client.fetch_competitor_intelligence("Datadog")

    assert profile.source == "intelx"
    assert profile.degraded is False
    assert profile.research_run_id == "run-cited"
    assert profile.findings_confidence == 0.82
    assert "per host" in profile.pricing_model
    # Citations are normalised to readable strings: IntelX returns objects, and the old
    # list[str] contract crashed the live path the moment a run produced a real citation.
    assert profile.evidence_citations == [
        "Datadog Pricing — https://example.com/pricing",
        "Datadog Docs — https://example.com/docs",
    ]
    assert profile.battlecard_summary == "# Datadog battlecard"

    delegate_payload = next(payload for method, url, payload in calls if url.endswith("/api/v1/friday/delegate"))
    # IntelX rejects delegations missing any of the four mandatory research dimensions (422).
    for dimension in ("query_scope", "source_policy", "time_budget", "document_budget"):
        assert dimension in delegate_payload, f"{dimension} is mandatory in the IntelX research contract"
    assert delegate_payload["context"]["requesting_system"] in {"friday", "sentinel", "nexus", "trading_bot", "forge"}


# ---------------------------------------------------------------------------
# 5. Opt-in live round-trips against real peer deployments.
# ---------------------------------------------------------------------------

live_only = pytest.mark.skipif(
    os.getenv("CORTEX_PEER_LIVE_TESTS", "") not in {"1", "true", "yes"},
    reason="set CORTEX_PEER_LIVE_TESTS=1 with FUTURIS_BASE_URL/INTELX_BASE_URL to run live peer round-trips",
)


@live_only
async def test_live_futuris_round_trip_returns_calibrated_provenance():
    import math
    from datetime import UTC, datetime, timedelta

    client = FuturisClient()
    assert client.live, "FUTURIS_BASE_URL must be configured for the live round-trip"

    now = datetime.now(UTC)

    def sample(value_at) -> list[dict]:
        points = []
        for i in range(96):
            ts = now - timedelta(minutes=15 * (96 - i))
            points.append({"timestamp": ts.isoformat().replace("+00:00", "Z"), "value": round(value_at(ts, i), 2)})
        return points

    telemetry = sample(
        lambda ts, i: 150.0 + 60.0 * math.sin(2 * math.pi * (ts.hour * 60 + ts.minute) / 1440) + (i % 3) * 1.5
    )

    forecast = await client.predict_traffic("site_live_contract", 24, telemetry=telemetry)

    assert forecast.source == "futuris", f"live Futuris must answer, got {forecast.source}: {forecast.degraded_reason}"
    assert forecast.forecast_id_remote
    assert forecast.data_points
    assert forecast.prediction_is_not_authorization is True
    assert (
        forecast.data_points[0].confidence_lower
        <= forecast.data_points[0].predicted_value
        <= forecast.data_points[0].confidence_upper
    )

    # Real-world disagreement: a series with noisy first differences makes Futuris report a 90%
    # interval spanning negative requests/second. Cortex must refuse that, not launder it.
    refused = await client.predict_traffic(
        "site_live_noisy", 24, telemetry=sample(lambda ts, i: 120.0 + (i % 13) * 7.0)
    )
    if refused.source == "fallback":
        assert refused.degraded is True
        assert "not actionable" in (refused.degraded_reason or "")


@live_only
async def test_live_intelx_round_trip_reports_its_own_evidence_quality():
    client = IntelXClient()
    assert client.live, "INTELX_BASE_URL must be configured for the live round-trip"

    health = await client.health_check()
    assert health["status"] == "UP" and health["mode"] == "live"

    profile = await client.fetch_competitor_intelligence("Datadog")
    assert profile.source in {"intelx", "fallback"}
    if profile.source == "intelx":
        assert profile.research_run_id and profile.findings_confidence > 0
    else:
        assert profile.degraded and profile.degraded_reason, "a live peer fallback must explain itself"
