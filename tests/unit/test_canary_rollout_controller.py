"""Unit tests for the dynamic canary rollout controller (cortex_core.canary_controller)."""

from __future__ import annotations

import pytest
from cortex_core.canary_controller import CanaryPolicy, CanaryRolloutController, CanaryStage


@pytest.fixture
def canary():
    policy = CanaryPolicy(
        max_error_rate_pct=1.0,
        max_p99_latency_ms=500.0,
        max_security_alerts=0,
        min_sample_requests=10,  # low threshold for tests
    )
    return CanaryRolloutController(deployment_id="cortex-test-deploy", policy=policy)


@pytest.mark.asyncio
async def test_canary_advances_through_stages(canary):
    assert canary.current_stage == CanaryStage.BASELINE_0

    # Advance to 5%
    ok, msg = await canary.advance_stage(operator="tester")
    assert ok is True
    assert canary.current_stage == CanaryStage.CANARY_5

    # Record healthy metrics: 20 requests, 0 errors, 50ms latency
    for _ in range(20):
        await canary.record_traffic_metric(is_error=False, latency_ms=50.0)

    # Advance to 25%
    ok2, msg2 = await canary.advance_stage(operator="tester")
    assert ok2 is True
    assert canary.current_stage == CanaryStage.CANARY_25

    # Advance to 50%
    ok3, _ = await canary.advance_stage(operator="tester")
    assert ok3 is True
    assert canary.current_stage == CanaryStage.CANARY_50

    # Advance to 100%
    ok4, _ = await canary.advance_stage(operator="tester")
    assert ok4 is True
    assert canary.current_stage == CanaryStage.PRODUCTION_100

    # Next advance confirms already at 100%
    ok5, msg5 = await canary.advance_stage(operator="tester")
    assert ok5 is True
    assert "already at 100%" in msg5


@pytest.mark.asyncio
async def test_canary_triggers_automated_rollback_on_error_rate_breach(canary):
    # Advance to 5%
    await canary.advance_stage(operator="tester")
    assert canary.current_stage == CanaryStage.CANARY_5

    # Record high error rate: 10 requests, 2 errors (20% > 1.0% max)
    for _ in range(8):
        await canary.record_traffic_metric(is_error=False, latency_ms=40.0)
    for _ in range(2):
        await canary.record_traffic_metric(is_error=True, latency_ms=40.0)

    # Trying to advance must fail and trigger automated rollback!
    ok, msg = await canary.advance_stage(operator="tester")
    assert ok is False
    assert "rolled back to 0%" in msg
    assert canary.current_stage == CanaryStage.BASELINE_0
    assert canary.is_rolled_back is True


@pytest.mark.asyncio
async def test_canary_triggers_automated_rollback_on_p99_latency_breach(canary):
    await canary.advance_stage(operator="tester")
    assert canary.current_stage == CanaryStage.CANARY_5

    # Record 100 requests where latency exceeds 500ms
    for _ in range(98):
        await canary.record_traffic_metric(is_error=False, latency_ms=50.0)
    for _ in range(2):
        await canary.record_traffic_metric(is_error=False, latency_ms=950.0)  # > 500ms

    healthy, reason, metrics = await canary.evaluate_health()
    assert healthy is False
    assert "p99 latency" in reason

    ok, msg = await canary.advance_stage(operator="tester")
    assert ok is False
    assert canary.current_stage == CanaryStage.BASELINE_0
    assert canary.is_rolled_back is True


@pytest.mark.asyncio
async def test_canary_triggers_automated_rollback_on_security_alert(canary):
    await canary.advance_stage(operator="tester")

    # Record security alert
    await canary.record_traffic_metric(is_error=False, latency_ms=50.0, is_security_alert=True)
    for _ in range(15):
        await canary.record_traffic_metric(is_error=False, latency_ms=50.0)

    healthy, reason, metrics = await canary.evaluate_health()
    assert healthy is False
    assert "Security alerts" in reason


@pytest.mark.asyncio
async def test_canary_manual_rollback_and_disallowed_subsequent_advance(canary):
    await canary.advance_stage(operator="tester")
    assert canary.current_stage == CanaryStage.CANARY_5

    rec = await canary.rollback(reason="Manual operator abort", operator="secops_admin")
    assert rec.to_stage == CanaryStage.BASELINE_0
    assert canary.is_rolled_back is True

    # Subsequent advance attempts are rejected
    ok, msg = await canary.advance_stage(operator="tester")
    assert ok is False
    assert "has been rolled back" in msg


@pytest.mark.asyncio
async def test_canary_get_state_and_history(canary):
    await canary.advance_stage(operator="ops_user")
    state = await canary.get_state()

    assert state["deployment_id"] == "cortex-test-deploy"
    assert state["current_stage"] == "5%"
    assert state["traffic_split_pct"] == 5
    assert len(state["history"]) == 1
    assert state["history"][0]["from_stage"] == "0%"
    assert state["history"][0]["to_stage"] == "5%"
