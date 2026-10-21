"""Unit tests for the multi-touch attribution engine (cortex_analytics.attribution)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cortex_analytics.attribution import (
    AttributionEngine,
    AttributionModelType,
    ConversionEvent,
    Touchpoint,
)


def _dt(offset_hours: float = 0.0) -> datetime:
    base = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
    return base + timedelta(hours=offset_hours)


@pytest.fixture
def sample_journey():
    tps = [
        Touchpoint(visitor_id="vis_1", session_id="s1", channel="organic_search", timestamp=_dt(0)),
        Touchpoint(visitor_id="vis_1", session_id="s2", channel="linkedin_ad", timestamp=_dt(24)),
        Touchpoint(visitor_id="vis_1", session_id="s3", channel="email_nurture", timestamp=_dt(48)),
        Touchpoint(visitor_id="vis_1", session_id="s4", channel="direct", timestamp=_dt(72)),
    ]
    conv = ConversionEvent(
        conversion_id="conv_100",
        visitor_id="vis_1",
        revenue=1000.0,
        timestamp=_dt(72),
    )
    return tps, conv


def test_first_touch_attribution(sample_journey):
    tps, conv = sample_journey
    engine = AttributionEngine()
    result = engine.attribute_conversion(conv, tps, model=AttributionModelType.FIRST_TOUCH)

    assert result.model == AttributionModelType.FIRST_TOUCH
    assert result.channel_weights == {"organic_search": 1.0}
    assert result.attributed_revenue == {"organic_search": 1000.0}
    assert result.touchpoint_count == 4


def test_last_touch_attribution(sample_journey):
    tps, conv = sample_journey
    engine = AttributionEngine()
    result = engine.attribute_conversion(conv, tps, model=AttributionModelType.LAST_TOUCH)

    assert result.model == AttributionModelType.LAST_TOUCH
    assert result.channel_weights == {"direct": 1.0}
    assert result.attributed_revenue == {"direct": 1000.0}


def test_linear_attribution(sample_journey):
    tps, conv = sample_journey
    engine = AttributionEngine()
    result = engine.attribute_conversion(conv, tps, model=AttributionModelType.LINEAR)

    assert result.model == AttributionModelType.LINEAR
    for channel in ["organic_search", "linkedin_ad", "email_nurture", "direct"]:
        assert result.channel_weights[channel] == pytest.approx(0.25, abs=1e-3)
        assert result.attributed_revenue[channel] == pytest.approx(250.0, abs=1e-2)


def test_time_decay_attribution(sample_journey):
    tps, conv = sample_journey
    engine = AttributionEngine(default_half_life_days=2.0)  # 48h half-life
    result = engine.attribute_conversion(conv, tps, model=AttributionModelType.TIME_DECAY)

    assert result.model == AttributionModelType.TIME_DECAY
    # Channel at t=72h (direct) must have strictly higher weight than t=0h (organic_search)
    assert result.channel_weights["direct"] > result.channel_weights["organic_search"]
    assert result.channel_weights["direct"] > result.channel_weights["email_nurture"]
    assert sum(result.channel_weights.values()) == pytest.approx(1.0, abs=1e-4)
    assert sum(result.attributed_revenue.values()) == pytest.approx(1000.0, abs=1e-2)


def test_position_based_attribution_multi_touch(sample_journey):
    tps, conv = sample_journey
    engine = AttributionEngine()
    result = engine.attribute_conversion(conv, tps, model=AttributionModelType.POSITION_BASED)

    assert result.model == AttributionModelType.POSITION_BASED
    # 40% first (organic_search), 40% last (direct), 10% each intermediate (linkedin, email)
    assert result.channel_weights["organic_search"] == pytest.approx(0.40, abs=1e-3)
    assert result.channel_weights["direct"] == pytest.approx(0.40, abs=1e-3)
    assert result.channel_weights["linkedin_ad"] == pytest.approx(0.10, abs=1e-3)
    assert result.channel_weights["email_nurture"] == pytest.approx(0.10, abs=1e-3)
    assert result.attributed_revenue["organic_search"] == pytest.approx(400.0, abs=1e-2)


def test_position_based_attribution_two_touch():
    tps = [
        Touchpoint(visitor_id="vis_2", session_id="s1", channel="google_search", timestamp=_dt(0)),
        Touchpoint(visitor_id="vis_2", session_id="s2", channel="direct", timestamp=_dt(10)),
    ]
    conv = ConversionEvent(conversion_id="conv_2", visitor_id="vis_2", revenue=500.0, timestamp=_dt(10))
    engine = AttributionEngine()
    result = engine.attribute_conversion(conv, tps, model=AttributionModelType.POSITION_BASED)

    assert result.channel_weights["google_search"] == pytest.approx(0.50, abs=1e-3)
    assert result.channel_weights["direct"] == pytest.approx(0.50, abs=1e-3)


def test_touchpoint_post_conversion_is_excluded(sample_journey):
    tps, conv = sample_journey
    # Add a touchpoint after conversion
    post_tp = Touchpoint(
        visitor_id="vis_1", session_id="s5", channel="retargeting_ad", timestamp=_dt(100)
    )
    tps_with_post = tps + [post_tp]

    engine = AttributionEngine()
    result = engine.attribute_conversion(conv, tps_with_post, model=AttributionModelType.LAST_TOUCH)
    # Must still attribute to direct at t=72h, ignoring t=100h
    assert result.channel_weights == {"direct": 1.0}
    assert "retargeting_ad" not in result.channel_weights


def test_unattributed_conversion_when_no_touchpoints():
    conv = ConversionEvent(conversion_id="conv_orphan", visitor_id="vis_orphan", revenue=300.0, timestamp=_dt(0))
    engine = AttributionEngine()
    result = engine.attribute_conversion(conv, [], model=AttributionModelType.LINEAR)

    assert result.channel_weights == {"unattributed": 1.0}
    assert result.attributed_revenue == {"unattributed": 300.0}
    assert result.touchpoint_count == 0


def test_generate_report_with_roi_and_top_paths():
    tps = [
        Touchpoint(visitor_id="u1", session_id="s1", channel="seo", timestamp=_dt(0)),
        Touchpoint(visitor_id="u1", session_id="s2", channel="email", timestamp=_dt(24)),
        Touchpoint(visitor_id="u2", session_id="s3", channel="seo", timestamp=_dt(5)),
        Touchpoint(visitor_id="u2", session_id="s4", channel="direct", timestamp=_dt(10)),
    ]
    convs = [
        ConversionEvent(conversion_id="c1", visitor_id="u1", revenue=200.0, timestamp=_dt(24)),
        ConversionEvent(conversion_id="c2", visitor_id="u2", revenue=400.0, timestamp=_dt(10)),
    ]
    costs = {"seo": 50.0, "email": 20.0, "direct": 0.0}

    engine = AttributionEngine()
    report = engine.generate_report(
        tenant_id="tenant_retail",
        conversions=convs,
        touchpoints=tps,
        model=AttributionModelType.LINEAR,
        channel_costs=costs,
    )

    assert report.tenant_id == "tenant_retail"
    assert sum(report.channel_revenue.values()) == pytest.approx(600.0, abs=1e-2)
    assert report.channel_roi["seo"] > 0
    assert report.channel_roi["email"] > 0
    assert len(report.top_paths) == 2


def test_markov_chain_attribution_report():
    tps = [
        Touchpoint(visitor_id="u1", session_id="s1", channel="search", timestamp=_dt(0)),
        Touchpoint(visitor_id="u1", session_id="s2", channel="social", timestamp=_dt(10)),
        Touchpoint(visitor_id="u2", session_id="s3", channel="search", timestamp=_dt(0)),
        Touchpoint(visitor_id="u2", session_id="s4", channel="email", timestamp=_dt(5)),
    ]
    convs = [
        ConversionEvent(conversion_id="c1", visitor_id="u1", revenue=100.0, timestamp=_dt(10)),
        ConversionEvent(conversion_id="c2", visitor_id="u2", revenue=200.0, timestamp=_dt(5)),
    ]

    engine = AttributionEngine()
    report = engine.generate_report(
        tenant_id="tenant_markov",
        conversions=convs,
        touchpoints=tps,
        model=AttributionModelType.MARKOV_CHAIN,
    )

    assert report.model == AttributionModelType.MARKOV_CHAIN
    assert sum(report.channel_revenue.values()) == pytest.approx(300.0, abs=1e-2)
    assert "search" in report.channel_revenue
