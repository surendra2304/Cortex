"""Turn Cortex's own ingested traffic into forecast telemetry for Futuris.

Why this module exists
----------------------
Cortex asked Futuris to "predict traffic for site X" and never sent Futuris a single
observation about site X. The peer therefore fell back to its own synthetic series, which
Cortex's sanity gate then had to refuse — so the live path could never produce a usable
forecast, and the ``current_rps`` in the API was a fixture number (180.0) rather than
anything about the deployment.

Cortex already stores the deployment's real traffic: every ``POST /v1/events`` row carries
``site_id`` and ``occurred_at``. This adapter buckets those rows into a per-second rate
series, which is exactly the series Futuris's ``telemetry_data`` contract expects, so the
forecast is driven by observed traffic.

Honesty rules (a wrong series is worse than no series):

* Buckets are contiguous and zero-filled — a quiet bucket is a real observation of zero
  traffic, not a gap to be interpolated over.
* The series is only returned when the site *currently* has traffic: at least
  ``MIN_TOTAL_EVENTS`` in the window and at least one event in the most recent
  ``RECENT_ACTIVITY_WINDOW``. Otherwise Cortex has nothing current to forecast and the
  caller must not pretend it does.
* ``MIN_BUCKETS`` mirrors Futuris's own sufficiency floor (it rejects < 5 points), so
  Cortex never sends a series it knows will be refused.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select

DEFAULT_BUCKET_MINUTES = 15
DEFAULT_WINDOW_HOURS = 24
MIN_BUCKETS = 5
MIN_TOTAL_EVENTS = 5
RECENT_ACTIVITY_WINDOW = timedelta(hours=1)


def bucket_traffic(
    occurred_at_values: list[datetime],
    *,
    site_id: str,
    now: datetime | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    bucket_minutes: int = DEFAULT_BUCKET_MINUTES,
) -> list[dict[str, Any]]:
    """Bucket raw event timestamps into a contiguous per-second rate series.

    Pure function so the bucketing rules are testable without a database.
    """
    now = (now or datetime.now(UTC)).astimezone(UTC)
    bucket_seconds = bucket_minutes * 60
    bucket_count = max(1, (window_hours * 3600) // bucket_seconds)
    window_start = now - timedelta(seconds=bucket_seconds * bucket_count)

    counts = [0] * bucket_count
    for raw in occurred_at_values:
        if raw is None:
            continue
        observed = raw if raw.tzinfo else raw.replace(tzinfo=UTC)
        observed = observed.astimezone(UTC)
        if observed < window_start or observed > now:
            continue
        index = min(bucket_count - 1, int((observed - window_start).total_seconds() // bucket_seconds))
        counts[index] += 1

    return [
        {
            "timestamp": (window_start + timedelta(seconds=bucket_seconds * (index + 1)))
            .isoformat()
            .replace("+00:00", "Z"),
            "value": round(count / bucket_seconds, 6),
            "unit": "rps",
            "site_id": site_id,
        }
        for index, count in enumerate(counts)
    ]


def has_current_traffic(
    occurred_at_values: list[datetime], *, now: datetime | None = None, min_events: int = MIN_TOTAL_EVENTS
) -> bool:
    """True when there is enough *current* traffic for a forecast to mean anything."""
    if len(occurred_at_values) < min_events:
        return False
    now = (now or datetime.now(UTC)).astimezone(UTC)
    recent_cutoff = now - RECENT_ACTIVITY_WINDOW
    for raw in occurred_at_values:
        if raw is None:
            continue
        observed = raw if raw.tzinfo else raw.replace(tzinfo=UTC)
        if recent_cutoff <= observed.astimezone(UTC) <= now:
            return True
    return False


async def observed_traffic_telemetry(
    db: Any,
    *,
    tenant_id: str,
    site_id: str,
    now: datetime | None = None,
    window_hours: int = DEFAULT_WINDOW_HOURS,
    bucket_minutes: int = DEFAULT_BUCKET_MINUTES,
    max_rows: int = 20000,
) -> list[dict[str, Any]]:
    """Read this tenant's stored events for a site and return Futuris-ready telemetry.

    Returns ``[]`` when the site has no current traffic or too little history — the caller
    then requests a forecast without telemetry, which is the documented fallback path
    rather than a fabricated series.
    """
    from cortex_api.db_models import EventModel  # local import: avoids an import cycle

    now = (now or datetime.now(UTC)).astimezone(UTC)
    window_start = now - timedelta(hours=window_hours)
    stmt = (
        select(EventModel.occurred_at)
        .where(
            and_(
                EventModel.tenant_id == tenant_id,
                EventModel.site_id == site_id,
                EventModel.occurred_at >= window_start,
                EventModel.occurred_at <= now,
            )
        )
        .limit(max_rows)
    )
    result = await db.execute(stmt)
    timestamps = [row[0] for row in result.all()]

    if not has_current_traffic(timestamps, now=now):
        return []

    series = bucket_traffic(
        timestamps, site_id=site_id, now=now, window_hours=window_hours, bucket_minutes=bucket_minutes
    )
    if len(series) < MIN_BUCKETS:
        return []
    return series


def average_rps(series: list[dict[str, Any]]) -> float:
    """Mean of the observed buckets — a cheap 'where are we now' figure for reporting."""
    values = [float(point["value"]) for point in series if isinstance(point.get("value"), (int, float))]
    return round(sum(values) / len(values), 3) if values else 0.0
