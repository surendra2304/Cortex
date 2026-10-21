"""
Sankey Path & Multi-Horizon Retention Analytics Engine for Cortex.

Provides production-grade customer journey path mapping, transition graph analysis,
Sankey flow generation, top conversion path ranking, drop-off anomaly detection,
and multi-horizon retention matrix calculation (D0, D1, D3, D7, D14, D30).
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(dt_val: Any) -> datetime:
    if isinstance(dt_val, datetime):
        return dt_val if dt_val.tzinfo else dt_val.replace(tzinfo=UTC)
    if isinstance(dt_val, str):
        try:
            cleaned = dt_val.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(cleaned)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except Exception:
            return _utcnow()
    return _utcnow()


class SankeyNode(BaseModel):
    id: str
    name: str
    stage_index: int
    count: int = 0
    category: str = "step"  # entry, step, conversion, exit, bounce


class SankeyLink(BaseModel):
    source: str
    target: str
    value: int
    conversion_rate_pct: float
    median_duration_seconds: float = 0.0


class SankeyPathReport(BaseModel):
    nodes: list[SankeyNode]
    links: list[SankeyLink]
    top_paths: list[dict[str, Any]]
    drop_off_points: list[dict[str, Any]]
    total_sessions_analyzed: int
    overall_conversion_rate_pct: float
    generated_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class RetentionCohortRow(BaseModel):
    cohort_date: str
    initial_users: int
    retention_by_day: dict[int, float]  # day horizon -> retention percentage
    active_by_day: dict[int, int]  # day horizon -> active user count


class RetentionMatrixReport(BaseModel):
    cohorts: list[RetentionCohortRow]
    horizons: list[int]
    average_retention: dict[int, float]
    cumulative_churn_rate_pct: float
    total_tracked_users: int
    generated_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class PathAnalysisEngine:
    """
    Computes transition flows and path-to-conversion Sankey graphs from event streams.
    """

    def compute_sankey_paths(
        self,
        events: list[dict[str, Any]],
        conversion_event_types: list[str] | None = None,
        max_path_length: int = 6,
    ) -> SankeyPathReport:
        if conversion_event_types is None:
            conversion_event_types = ["conversion", "purchase", "checkout.complete", "lead.submit", "signup"]

        target_set = {t.lower() for t in conversion_event_types}

        # 1. Group events by session (or actor if session missing)
        sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for ev in events:
            sid = str(ev.get("session_id") or ev.get("actor_id") or "anonymous_session")
            sessions[sid].append(ev)

        # Sort each session's events chronologically
        for sid in sessions:
            sessions[sid].sort(key=lambda e: _parse_datetime(e.get("occurred_at")))

        # 2. Extract normalized stage sequences per session
        paths_counter: Counter[tuple[str, ...]] = Counter()
        transitions: dict[tuple[str, str], list[float]] = defaultdict(list)
        node_counts: dict[str, int] = Counter()
        stage_levels: dict[str, int] = {}
        total_sessions = len(sessions)
        converted_sessions = 0

        for sid, ev_list in sessions.items():
            if not ev_list:
                continue

            # Build sequence of distinct step names (collapsing consecutive duplicates)
            raw_path: list[tuple[str, datetime]] = []
            has_converted = False

            for ev in ev_list:
                etype = str(ev.get("type", "unknown")).strip()
                path_name = ev.get("data", {}).get("path")
                step_name = str(path_name) if path_name else etype
                occurred = _parse_datetime(ev.get("occurred_at"))

                if any(conv in etype.lower() or (path_name and conv in str(path_name).lower()) for conv in target_set):
                    has_converted = True
                    step_name = "CONVERSION"

                if not raw_path or raw_path[-1][0] != step_name:
                    raw_path.append((step_name, occurred))

            if has_converted:
                converted_sessions += 1

            # Truncate to max_path_length
            truncated_path = raw_path[:max_path_length]
            step_names = tuple(step for step, _ in truncated_path)
            paths_counter[step_names] += 1

            # Count nodes and assign levels
            for idx, (step, _) in enumerate(truncated_path):
                node_counts[step] += 1
                if step not in stage_levels:
                    stage_levels[step] = idx
                else:
                    stage_levels[step] = min(stage_levels[step], idx)

            # Record transitions with inter-event durations
            for i in range(len(truncated_path) - 1):
                from_step, t0 = truncated_path[i]
                to_step, t1 = truncated_path[i + 1]
                duration = max(0.0, (t1 - t0).total_seconds())
                transitions[(from_step, to_step)].append(duration)

            # If session ended without conversion, register drop-off exit transition
            if not has_converted and truncated_path:
                last_step, _ = truncated_path[-1]
                transitions[(last_step, "DROPOFF_EXIT")].append(0.0)
                node_counts["DROPOFF_EXIT"] += 1
                stage_levels["DROPOFF_EXIT"] = max(stage_levels.get(last_step, 0) + 1, 1)

        # 3. Assemble Sankey Nodes
        nodes: list[SankeyNode] = []
        for step, count in node_counts.items():
            if step == "CONVERSION":
                category = "conversion"
            elif step == "DROPOFF_EXIT":
                category = "exit"
            elif stage_levels.get(step, 0) == 0:
                category = "entry"
            else:
                category = "step"

            nodes.append(
                SankeyNode(
                    id=step,
                    name=step,
                    stage_index=stage_levels.get(step, 0),
                    count=count,
                    category=category,
                )
            )

        # 4. Assemble Sankey Links
        links: list[SankeyLink] = []
        for (from_step, to_step), durations in transitions.items():
            trans_count = len(durations)
            source_total = node_counts.get(from_step, 1)
            conv_pct = round((trans_count / source_total) * 100.0, 2)
            med_duration = round(statistics.median(durations) if durations else 0.0, 2)

            links.append(
                SankeyLink(
                    source=from_step,
                    target=to_step,
                    value=trans_count,
                    conversion_rate_pct=conv_pct,
                    median_duration_seconds=med_duration,
                )
            )

        # Sort links by volume
        links.sort(key=lambda l: l.value, reverse=True)

        # 5. Extract Top Paths
        top_paths = []
        for path_tuple, count in paths_counter.most_common(10):
            path_str = " -> ".join(path_tuple)
            is_conversion = "CONVERSION" in path_tuple
            pct = round((count / total_sessions * 100.0), 2) if total_sessions > 0 else 0.0
            top_paths.append(
                {
                    "path": path_str,
                    "steps": list(path_tuple),
                    "session_count": count,
                    "percentage_of_traffic": pct,
                    "ended_in_conversion": is_conversion,
                }
            )

        # 6. Identify High-Drop-Off Points
        drop_offs = []
        for link in links:
            if link.target == "DROPOFF_EXIT" and link.value > 0:
                drop_offs.append(
                    {
                        "abandonment_node": link.source,
                        "dropped_sessions": link.value,
                        "exit_rate_pct": link.conversion_rate_pct,
                    }
                )
        drop_offs.sort(key=lambda d: d["dropped_sessions"], reverse=True)

        overall_conv_pct = (
            round((converted_sessions / total_sessions * 100.0), 2) if total_sessions > 0 else 0.0
        )

        return SankeyPathReport(
            nodes=nodes,
            links=links,
            top_paths=top_paths,
            drop_off_points=drop_offs,
            total_sessions_analyzed=total_sessions,
            overall_conversion_rate_pct=overall_conv_pct,
        )


class RetentionMatrixEngine:
    """
    Computes cohort retention curves across configured day horizons (e.g. D0, D1, D3, D7, D14, D30).
    """

    def compute_retention_matrix(
        self,
        events: list[dict[str, Any]],
        horizons: list[int] | None = None,
    ) -> RetentionMatrixReport:
        if horizons is None:
            horizons = [0, 1, 3, 7, 14, 30]

        horizons = sorted(list(set(horizons)))
        if 0 not in horizons:
            horizons.insert(0, 0)

        # Group actor first seen date and all active days
        actor_first_dt: dict[str, datetime] = {}
        actor_active_dates: dict[str, set[str]] = defaultdict(set)

        for ev in events:
            aid = str(ev.get("actor_id") or ev.get("actor", {}).get("id") or "anonymous")
            dt = _parse_datetime(ev.get("occurred_at"))
            date_str = dt.strftime("%Y-%m-%d")

            if aid not in actor_first_dt or dt < actor_first_dt[aid]:
                actor_first_dt[aid] = dt

            actor_active_dates[aid].add(date_str)

        # Group actors into cohort date buckets (YYYY-MM-DD of first touch)
        cohort_groups: dict[str, list[str]] = defaultdict(list)
        for aid, first_dt in actor_first_dt.items():
            first_date_str = first_dt.strftime("%Y-%m-%d")
            cohort_groups[first_date_str].append(aid)

        total_tracked_users = len(actor_first_dt)
        cohort_rows: list[RetentionCohortRow] = []

        horizon_sums: dict[int, float] = {h: 0.0 for h in horizons}
        horizon_counts: dict[int, int] = {h: 0 for h in horizons}

        for cohort_date_str in sorted(cohort_groups.keys()):
            members = cohort_groups[cohort_date_str]
            initial_count = len(members)
            if initial_count == 0:
                continue

            cohort_dt = datetime.strptime(cohort_date_str, "%Y-%m-%d").replace(tzinfo=UTC)
            retention_by_day: dict[int, float] = {}
            active_by_day: dict[int, int] = {}

            for h in horizons:
                if h == 0:
                    retention_by_day[0] = 100.0
                    active_by_day[0] = initial_count
                    horizon_sums[0] += 100.0
                    horizon_counts[0] += 1
                    continue

                # Day H target date
                from datetime import timedelta
                target_dt = cohort_dt + timedelta(days=h)
                target_date_str = target_dt.strftime("%Y-%m-%d")

                # Count members active on target date
                active_h = sum(1 for m in members if target_date_str in actor_active_dates[m])
                pct = round((active_h / initial_count) * 100.0, 2)

                retention_by_day[h] = pct
                active_by_day[h] = active_h
                horizon_sums[h] += pct
                horizon_counts[h] += 1

            cohort_rows.append(
                RetentionCohortRow(
                    cohort_date=cohort_date_str,
                    initial_users=initial_count,
                    retention_by_day=retention_by_day,
                    active_by_day=active_by_day,
                )
            )

        # Calculate average retention across all cohorts for each horizon
        avg_retention: dict[int, float] = {}
        for h in horizons:
            denom = horizon_counts.get(h, 0)
            avg_retention[h] = round((horizon_sums.get(h, 0.0) / denom), 2) if denom > 0 else 0.0

        # Cumulative churn rate is 100 - retention at the longest horizon
        longest_h = horizons[-1]
        longest_retention = avg_retention.get(longest_h, 0.0)
        cumulative_churn = round(100.0 - longest_retention, 2)

        return RetentionMatrixReport(
            cohorts=cohort_rows,
            horizons=horizons,
            average_retention=avg_retention,
            cumulative_churn_rate_pct=cumulative_churn,
            total_tracked_users=total_tracked_users,
        )
