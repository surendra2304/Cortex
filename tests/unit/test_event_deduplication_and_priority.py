"""Unit tests for sliding-window event deduplication and priority routing (cortex_upgrade.event_stream)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from cortex_upgrade.event_stream import EventDeduplicator, PriorityEventRouter, PriorityLevel


@pytest.mark.asyncio
async def test_deduplicator_detects_duplicate_event_id():
    dedup = EventDeduplicator(window_seconds=60.0)

    # First arrival: not a duplicate
    is_dup = await dedup.check_and_record("evt_100")
    assert is_dup is False

    # Second arrival of same event ID: duplicate!
    is_dup2 = await dedup.check_and_record("evt_100")
    assert is_dup2 is True

    # Different event ID: not duplicate
    is_dup3 = await dedup.check_and_record("evt_101")
    assert is_dup3 is False


@pytest.mark.asyncio
async def test_deduplicator_detects_duplicate_payload_hash():
    dedup = EventDeduplicator(window_seconds=60.0)
    payload = {"visitor_id": "vis_1", "action": "checkout_click", "amount": 99.0}
    h = EventDeduplicator.compute_payload_hash(payload)

    # Different event IDs with identical payload content
    assert await dedup.check_and_record("evt_a", payload_hash=h) is False
    assert await dedup.check_and_record("evt_b", payload_hash=h) is True


@pytest.mark.asyncio
async def test_deduplicator_expires_old_records():
    # Very short window: 0.05 seconds
    dedup = EventDeduplicator(window_seconds=0.05)

    assert await dedup.check_and_record("evt_short") is False
    assert await dedup.is_duplicate("evt_short") is True

    # Wait for expiration
    await asyncio.sleep(0.06)

    purged = await dedup.cleanup_expired()
    assert purged >= 1
    assert await dedup.is_duplicate("evt_short") is False


@pytest.mark.asyncio
async def test_deduplicator_caps_max_entries():
    dedup = EventDeduplicator(window_seconds=300.0, max_entries=3)

    for i in range(5):
        await dedup.record(f"evt_{i}")

    id_count, _ = await dedup.size()
    assert id_count == 3
    # evt_0 and evt_1 should have been evicted
    assert await dedup.is_duplicate("evt_0") is False
    assert await dedup.is_duplicate("evt_4") is True


def test_priority_event_router_classifications():
    # P0: Critical incidents, SLO breaches, security
    assert (
        PriorityEventRouter.classify("security_alert", {"threat": "ddos"})
        == PriorityLevel.P0_CRITICAL
    )
    assert (
        PriorityEventRouter.classify("slo_breach_detected", {"p99": 800})
        == PriorityLevel.P0_CRITICAL
    )
    assert (
        PriorityEventRouter.classify("payment_failed", {"amount": 500})
        == PriorityLevel.P0_CRITICAL
    )

    # P1: High intent commercial triggers
    assert (
        PriorityEventRouter.classify("checkout_started", {"cart_id": "c1"})
        == PriorityLevel.P1_HIGH
    )
    assert (
        PriorityEventRouter.classify("demo_request", {"email": "exec@corp.com"})
        == PriorityLevel.P1_HIGH
    )
    assert (
        PriorityEventRouter.classify("pricing_cta_click", {"plan": "enterprise"})
        == PriorityLevel.P1_HIGH
    )

    # P2: Standard telemetry
    assert (
        PriorityEventRouter.classify("page_view", {"path": "/blog/post-1"})
        == PriorityLevel.P2_STANDARD
    )
    assert (
        PriorityEventRouter.classify("button_click", {"button_id": "nav_menu"})
        == PriorityLevel.P2_STANDARD
    )

    # P3: Background health / heartbeat
    assert (
        PriorityEventRouter.classify("worker_heartbeat")
        == PriorityLevel.P3_BACKGROUND
    )
    assert (
        PriorityEventRouter.classify("health_check_ping")
        == PriorityLevel.P3_BACKGROUND
    )
