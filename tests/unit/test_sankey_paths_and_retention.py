"""
Unit tests for Sankey Path and Retention Matrix Analytics Engines.
"""

from datetime import UTC, datetime, timedelta
import pytest
from cortex_analytics.sankey_paths import (
    PathAnalysisEngine,
    RetentionMatrixEngine,
    SankeyPathReport,
    RetentionMatrixReport,
)


def _dt(offset_seconds: int = 0) -> str:
    base = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def test_path_analysis_empty_events():
    engine = PathAnalysisEngine()
    report = engine.compute_sankey_paths([])
    assert isinstance(report, SankeyPathReport)
    assert report.total_sessions_analyzed == 0
    assert report.overall_conversion_rate_pct == 0.0
    assert len(report.nodes) == 0
    assert len(report.links) == 0


def test_path_analysis_single_converting_session():
    engine = PathAnalysisEngine()
    events = [
        {"session_id": "s1", "type": "page_view", "data": {"path": "/home"}, "occurred_at": _dt(0)},
        {"session_id": "s1", "type": "page_view", "data": {"path": "/pricing"}, "occurred_at": _dt(30)},
        {"session_id": "s1", "type": "conversion", "data": {"path": "/signup"}, "occurred_at": _dt(90)},
    ]
    report = engine.compute_sankey_paths(events)
    assert report.total_sessions_analyzed == 1
    assert report.overall_conversion_rate_pct == 100.0
    assert len(report.nodes) >= 3

    node_ids = {n.id for n in report.nodes}
    assert "/home" in node_ids
    assert "/pricing" in node_ids
    assert "CONVERSION" in node_ids

    # Verify transitions
    link_pairs = {(l.source, l.target) for l in report.links}
    assert ("/home", "/pricing") in link_pairs
    assert ("/pricing", "CONVERSION") in link_pairs


def test_path_analysis_multi_session_with_dropoff():
    engine = PathAnalysisEngine()
    events = [
        # Session 1: converts
        {"session_id": "s1", "type": "page_view", "data": {"path": "/home"}, "occurred_at": _dt(0)},
        {"session_id": "s1", "type": "page_view", "data": {"path": "/docs"}, "occurred_at": _dt(10)},
        {"session_id": "s1", "type": "purchase", "data": {"amount": 50}, "occurred_at": _dt(20)},
        # Session 2: drops off at docs
        {"session_id": "s2", "type": "page_view", "data": {"path": "/home"}, "occurred_at": _dt(30)},
        {"session_id": "s2", "type": "page_view", "data": {"path": "/docs"}, "occurred_at": _dt(40)},
    ]
    report = engine.compute_sankey_paths(events)
    assert report.total_sessions_analyzed == 2
    assert report.overall_conversion_rate_pct == 50.0

    # Dropoff exit registered for session 2
    dropoff_links = [l for l in report.links if l.target == "DROPOFF_EXIT"]
    assert len(dropoff_links) > 0
    assert any(d["abandonment_node"] == "/docs" for d in report.drop_off_points)


def test_path_analysis_median_duration():
    engine = PathAnalysisEngine()
    events = [
        # Session 1: 10s between home and pricing
        {"session_id": "s1", "type": "page_view", "data": {"path": "/home"}, "occurred_at": _dt(0)},
        {"session_id": "s1", "type": "page_view", "data": {"path": "/pricing"}, "occurred_at": _dt(10)},
        # Session 2: 30s between home and pricing
        {"session_id": "s2", "type": "page_view", "data": {"path": "/home"}, "occurred_at": _dt(100)},
        {"session_id": "s2", "type": "page_view", "data": {"path": "/pricing"}, "occurred_at": _dt(130)},
    ]
    report = engine.compute_sankey_paths(events)
    home_to_pricing = next(l for l in report.links if l.source == "/home" and l.target == "/pricing")
    # Median of [10.0, 30.0] is 20.0
    assert home_to_pricing.median_duration_seconds == 20.0


def test_retention_matrix_empty():
    engine = RetentionMatrixEngine()
    report = engine.compute_retention_matrix([])
    assert isinstance(report, RetentionMatrixReport)
    assert report.total_tracked_users == 0
    assert len(report.cohorts) == 0


def test_retention_matrix_cohort_retention():
    engine = RetentionMatrixEngine()
    base_date = datetime(2026, 10, 1, tzinfo=UTC)

    events = [
        # User 1 active on D0, D1, D3
        {"actor_id": "u1", "occurred_at": base_date.isoformat()},
        {"actor_id": "u1", "occurred_at": (base_date + timedelta(days=1)).isoformat()},
        {"actor_id": "u1", "occurred_at": (base_date + timedelta(days=3)).isoformat()},
        # User 2 active on D0, D1 only
        {"actor_id": "u2", "occurred_at": base_date.isoformat()},
        {"actor_id": "u2", "occurred_at": (base_date + timedelta(days=1)).isoformat()},
        # User 3 active on D0 only
        {"actor_id": "u3", "occurred_at": base_date.isoformat()},
    ]

    report = engine.compute_retention_matrix(events, horizons=[0, 1, 3, 7])
    assert report.total_tracked_users == 3
    assert len(report.cohorts) == 1

    cohort = report.cohorts[0]
    assert cohort.initial_users == 3
    assert cohort.retention_by_day[0] == 100.0
    # 2 out of 3 active on D1 -> 66.67%
    assert round(cohort.retention_by_day[1], 1) == 66.7
    # 1 out of 3 active on D3 -> 33.33%
    assert round(cohort.retention_by_day[3], 1) == 33.3
    # 0 out of 3 active on D7 -> 0.0%
    assert cohort.retention_by_day[7] == 0.0
    # Cumulative churn
    assert report.cumulative_churn_rate_pct == 100.0
