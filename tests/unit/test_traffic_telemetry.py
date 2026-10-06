"""Unit tests for the telemetry adapter that feeds Cortex's own traffic to Futuris.

These pin the honesty rules, because a wrong series is worse than no series: the forecast
would look researched while describing nothing about the deployment.
"""

import os
import sys
from datetime import UTC, datetime, timedelta

for p in ["apps/api/src", "packages/core/src", "packages/integrations/src"]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_api.traffic_telemetry import (  # noqa: E402
    MIN_BUCKETS,
    average_rps,
    bucket_traffic,
    has_current_traffic,
)

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def test_buckets_are_contiguous_zero_filled_and_expressed_per_second():
    # Two events in the bucket ending 12:00, one in the bucket ending 11:30.
    events = [
        NOW - timedelta(minutes=1),
        NOW - timedelta(minutes=14),
        NOW - timedelta(minutes=45),
    ]
    series = bucket_traffic(events, site_id="site_demo", now=NOW, window_hours=1, bucket_minutes=15)

    assert len(series) == 4, "a one hour window at 15 minute buckets is four points"
    assert all(point["unit"] == "rps" for point in series)
    assert [point["timestamp"] for point in series] == [
        "2026-10-06T11:15:00Z",
        "2026-10-06T11:30:00Z",
        "2026-10-06T11:45:00Z",
        "2026-10-06T12:00:00Z",
    ]
    # 900 second buckets: 2/900 and 1/900 requests per second.
    assert series[3]["value"] == round(2 / 900, 6)
    assert series[1]["value"] == round(1 / 900, 6)
    assert series[0]["value"] == 0.0 and series[2]["value"] == 0.0, "quiet buckets are observed zeros"


def test_events_outside_the_window_are_ignored_not_extrapolated():
    events = [NOW - timedelta(hours=5), NOW + timedelta(minutes=5), NOW - timedelta(minutes=1)]
    series = bucket_traffic(events, site_id="site_demo", now=NOW, window_hours=1, bucket_minutes=15)

    assert sum(point["value"] for point in series) == round(1 / 900, 6), "only the in-window event counts"


def test_naive_timestamps_are_treated_as_utc():
    events = [datetime(2026, 10, 6, 11, 59)]  # naive, as SQLite returns them
    series = bucket_traffic(events, site_id="site_demo", now=NOW, window_hours=1, bucket_minutes=15)

    assert series[-1]["value"] == round(1 / 900, 6)


def test_current_traffic_requires_recent_activity_not_just_history():
    stale = [NOW - timedelta(hours=3, minutes=i) for i in range(20)]
    assert has_current_traffic(stale, now=NOW) is False, "history with no current traffic cannot be forecast"

    mostly_stale = stale + [NOW - timedelta(minutes=10)]
    assert has_current_traffic(mostly_stale, now=NOW) is True

    too_few = [NOW - timedelta(minutes=10), NOW - timedelta(minutes=20)]
    assert has_current_traffic(too_few, now=NOW) is False, "Futuris rejects a series below its sufficiency floor anyway"


def test_average_rps_is_the_mean_of_observed_buckets():
    series = [{"value": 0.0}, {"value": 1.0}, {"value": 2.0}]
    assert average_rps(series) == 1.0
    assert average_rps([]) == 0.0


def test_min_buckets_matches_the_peer_sufficiency_floor():
    # Futuris refuses telemetry with fewer than five points; Cortex must not send a series it
    # knows will be refused and then blame the peer for the empty answer.
    assert MIN_BUCKETS >= 5
