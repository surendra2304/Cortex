"""Multi-Touch Attribution Engine for CORTEX.

Provides multi-touch marketing and telemetry attribution models:
- First-Touch Attribution (FTA): 100% credit to the earliest discovery channel
- Last-Touch Attribution (LTA): 100% credit to the final converting channel
- Linear Attribution: Uniform credit across all journey touchpoints
- Time-Decay Attribution: Exponential half-life decay prioritizing recent touchpoints
- Position-Based Attribution (U-Shaped): 40% first touch, 40% last touch, 20% intermediate
- Markov Chain Attribution: First-order Markov graph with state removal effects
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AttributionModelType(str, Enum):
    FIRST_TOUCH = "first_touch"
    LAST_TOUCH = "last_touch"
    LINEAR = "linear"
    TIME_DECAY = "time_decay"
    POSITION_BASED = "position_based"
    MARKOV_CHAIN = "markov_chain"


@dataclass(frozen=True)
class Touchpoint:
    visitor_id: str
    session_id: str
    channel: str
    timestamp: datetime
    campaign: str = ""
    cost: float = 0.0


@dataclass(frozen=True)
class ConversionEvent:
    conversion_id: str
    visitor_id: str
    revenue: float
    timestamp: datetime
    conversion_type: str = "sale"


@dataclass
class AttributionResult:
    model: AttributionModelType
    conversion_id: str
    channel_weights: dict[str, float]
    attributed_revenue: dict[str, float]
    total_revenue: float
    touchpoint_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model.value,
            "conversion_id": self.conversion_id,
            "channel_weights": {k: round(v, 4) for k, v in self.channel_weights.items()},
            "attributed_revenue": {k: round(v, 2) for k, v in self.attributed_revenue.items()},
            "total_revenue": round(self.total_revenue, 2),
            "touchpoint_count": self.touchpoint_count,
        }


@dataclass
class AttributionReport:
    tenant_id: str
    model: AttributionModelType
    channel_revenue: dict[str, float]
    channel_conversions: dict[str, float]
    channel_roi: dict[str, float]
    top_paths: list[dict[str, Any]]
    average_latency_days: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "model": self.model.value,
            "channel_revenue": {k: round(v, 2) for k, v in self.channel_revenue.items()},
            "channel_conversions": {k: round(v, 4) for k, v in self.channel_conversions.items()},
            "channel_roi": {k: round(v, 2) for k, v in self.channel_roi.items()},
            "top_paths": self.top_paths,
            "average_latency_days": round(self.average_latency_days, 2),
        }


class AttributionEngine:
    """Computes multi-touch attribution metrics across customer journey paths."""

    def __init__(self, default_half_life_days: float = 7.0) -> None:
        self.default_half_life_days = default_half_life_days

    def _filter_valid_touchpoints(
        self, touchpoints: list[Touchpoint], conversion: ConversionEvent
    ) -> list[Touchpoint]:
        """Keep only touchpoints for the same visitor that occurred prior to or at conversion."""
        conv_ts = conversion.timestamp
        if conv_ts.tzinfo is None:
            conv_ts = conv_ts.replace(tzinfo=UTC)

        valid = []
        for tp in touchpoints:
            if tp.visitor_id != conversion.visitor_id:
                continue
            tp_ts = tp.timestamp
            if tp_ts.tzinfo is None:
                tp_ts = tp_ts.replace(tzinfo=UTC)
            if tp_ts <= conv_ts:
                valid.append(tp)

        # Sort chronologically
        return sorted(valid, key=lambda t: t.timestamp if t.timestamp.tzinfo else t.timestamp.replace(tzinfo=UTC))

    def attribute_conversion(
        self,
        conversion: ConversionEvent,
        touchpoints: list[Touchpoint],
        model: AttributionModelType = AttributionModelType.LINEAR,
        half_life_days: float | None = None,
    ) -> AttributionResult:
        """Compute single-conversion attribution weights and attributed revenue."""
        valid_tps = self._filter_valid_touchpoints(touchpoints, conversion)

        if not valid_tps:
            return AttributionResult(
                model=model,
                conversion_id=conversion.conversion_id,
                channel_weights={"unattributed": 1.0},
                attributed_revenue={"unattributed": conversion.revenue},
                total_revenue=conversion.revenue,
                touchpoint_count=0,
            )

        n = len(valid_tps)
        weights: dict[str, float] = defaultdict(float)

        if model == AttributionModelType.FIRST_TOUCH:
            weights[valid_tps[0].channel] = 1.0

        elif model == AttributionModelType.LAST_TOUCH:
            weights[valid_tps[-1].channel] = 1.0

        elif model == AttributionModelType.LINEAR:
            per_tp = 1.0 / n
            for tp in valid_tps:
                weights[tp.channel] += per_tp

        elif model == AttributionModelType.TIME_DECAY:
            hl = half_life_days or self.default_half_life_days
            conv_ts = conversion.timestamp
            if conv_ts.tzinfo is None:
                conv_ts = conv_ts.replace(tzinfo=UTC)

            raw_weights = []
            for tp in valid_tps:
                tp_ts = tp.timestamp
                if tp_ts.tzinfo is None:
                    tp_ts = tp_ts.replace(tzinfo=UTC)
                delta_days = max(0.0, (conv_ts - tp_ts).total_seconds() / 86400.0)
                # Exponential decay: 2^(-delta_days / half_life)
                raw_weight = math.pow(2.0, -delta_days / hl)
                raw_weights.append((tp.channel, raw_weight))

            total_raw = sum(w for _, w in raw_weights)
            if total_raw > 0:
                for channel, w in raw_weights:
                    weights[channel] += w / total_raw
            else:
                for channel, _ in raw_weights:
                    weights[channel] += 1.0 / n

        elif model == AttributionModelType.POSITION_BASED:
            if n == 1:
                weights[valid_tps[0].channel] = 1.0
            elif n == 2:
                weights[valid_tps[0].channel] += 0.5
                weights[valid_tps[1].channel] += 0.5
            else:
                weights[valid_tps[0].channel] += 0.4
                weights[valid_tps[-1].channel] += 0.4
                intermediate_weight = 0.2 / (n - 2)
                for i in range(1, n - 1):
                    weights[valid_tps[i].channel] += intermediate_weight

        elif model == AttributionModelType.MARKOV_CHAIN:
            # Fallback to linear for single paths when corpus is not provided
            per_tp = 1.0 / n
            for tp in valid_tps:
                weights[tp.channel] += per_tp

        # Normalise weights
        total_w = sum(weights.values())
        norm_weights = {k: v / total_w for k, v in weights.items()}
        attributed_rev = {k: v * conversion.revenue for k, v in norm_weights.items()}

        return AttributionResult(
            model=model,
            conversion_id=conversion.conversion_id,
            channel_weights=norm_weights,
            attributed_revenue=attributed_rev,
            total_revenue=conversion.revenue,
            touchpoint_count=n,
        )

    def _compute_markov_corpus_weights(
        self, journeys: list[list[str]]
    ) -> dict[str, float]:
        """Compute Markov removal effect attribution weights across multi-touch journeys."""
        if not journeys:
            return {}

        transitions: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        all_channels: set[str] = set()

        for path in journeys:
            if not path:
                continue
            states = ["(start)"] + path + ["(conversion)"]
            for i in range(len(states) - 1):
                from_state = states[i]
                to_state = states[i + 1]
                transitions[from_state][to_state] += 1
                if from_state not in {"(start)", "(conversion)"}:
                    all_channels.add(from_state)

        # Calculate transition probabilities
        prob_matrix: dict[str, dict[str, float]] = {}
        for from_state, to_counts in transitions.items():
            total = sum(to_counts.values())
            prob_matrix[from_state] = {to_s: c / total for to_s, c in to_counts.items()}

        def calculate_conversion_prob(removed_channel: str | None = None) -> float:
            """Simulate absorption probability reaching (conversion) using path unrolling."""
            queue = [("(start)", 1.0, 0)]
            total_conv_prob = 0.0

            while queue:
                current_state, path_prob, depth = queue.pop(0)
                if depth > 15 or path_prob < 1e-5:
                    continue
                if current_state == "(conversion)":
                    total_conv_prob += path_prob
                    continue
                if current_state == removed_channel:
                    continue

                for next_state, edge_prob in prob_matrix.get(current_state, {}).items():
                    if next_state == removed_channel:
                        continue
                    queue.append((next_state, path_prob * edge_prob, depth + 1))

            return total_conv_prob

        base_conv_prob = calculate_conversion_prob(None)
        if base_conv_prob <= 0:
            # Uniform fallback
            return {ch: 1.0 / len(all_channels) for ch in all_channels} if all_channels else {}

        removal_effects: dict[str, float] = {}
        for ch in all_channels:
            prob_without = calculate_conversion_prob(ch)
            removal_effect = max(0.0, (base_conv_prob - prob_without) / base_conv_prob)
            removal_effects[ch] = removal_effect

        total_effect = sum(removal_effects.values())
        if total_effect > 0:
            return {ch: eff / total_effect for ch, eff in removal_effects.items()}
        return {ch: 1.0 / len(all_channels) for ch in all_channels}

    def generate_report(
        self,
        tenant_id: str,
        conversions: list[ConversionEvent],
        touchpoints: list[Touchpoint],
        model: AttributionModelType = AttributionModelType.LINEAR,
        channel_costs: dict[str, float] | None = None,
    ) -> AttributionReport:
        """Aggregate attribution across all tenant conversions and produce ROI analysis."""
        channel_revenue: dict[str, float] = defaultdict(float)
        channel_conversions: dict[str, float] = defaultdict(float)
        channel_costs = channel_costs or {}

        journey_latencies: list[float] = []
        path_counts: dict[tuple[str, ...], int] = defaultdict(int)

        if model == AttributionModelType.MARKOV_CHAIN:
            # Build global paths for Markov graph
            corpus_paths: list[list[str]] = []
            for conv in conversions:
                tps = self._filter_valid_touchpoints(touchpoints, conv)
                if tps:
                    corpus_paths.append([t.channel for t in tps])
            markov_weights = self._compute_markov_corpus_weights(corpus_paths)

            for conv in conversions:
                tps = self._filter_valid_touchpoints(touchpoints, conv)
                if not tps:
                    channel_revenue["unattributed"] += conv.revenue
                    channel_conversions["unattributed"] += 1.0
                    continue

                path = tuple(t.channel for t in tps)
                path_counts[path] += 1

                first_ts = tps[0].timestamp if tps[0].timestamp.tzinfo else tps[0].timestamp.replace(tzinfo=UTC)
                conv_ts = conv.timestamp if conv.timestamp.tzinfo else conv.timestamp.replace(tzinfo=UTC)
                journey_latencies.append(max(0.0, (conv_ts - first_ts).total_seconds() / 86400.0))

                # Apportion weights based on Markov corpus weights for the present channels
                path_channels = set(path)
                sub_weights = {ch: markov_weights.get(ch, 0.0) for ch in path_channels}
                sub_total = sum(sub_weights.values())
                if sub_total > 0:
                    sub_weights = {ch: w / sub_total for ch, w in sub_weights.items()}
                else:
                    sub_weights = {ch: 1.0 / len(path_channels) for ch in path_channels}

                for ch, weight in sub_weights.items():
                    channel_revenue[ch] += weight * conv.revenue
                    channel_conversions[ch] += weight
        else:
            for conv in conversions:
                res = self.attribute_conversion(conv, touchpoints, model=model)
                tps = self._filter_valid_touchpoints(touchpoints, conv)
                if tps:
                    path = tuple(t.channel for t in tps)
                    path_counts[path] += 1
                    first_ts = tps[0].timestamp if tps[0].timestamp.tzinfo else tps[0].timestamp.replace(tzinfo=UTC)
                    conv_ts = conv.timestamp if conv.timestamp.tzinfo else conv.timestamp.replace(tzinfo=UTC)
                    journey_latencies.append(max(0.0, (conv_ts - first_ts).total_seconds() / 86400.0))

                for ch, weight in res.channel_weights.items():
                    channel_revenue[ch] += weight * conv.revenue
                    channel_conversions[ch] += weight

        # Compute ROI: (Revenue - Cost) / Cost
        channel_roi: dict[str, float] = {}
        for ch, rev in channel_revenue.items():
            cost = channel_costs.get(ch, 0.0)
            if cost > 0:
                channel_roi[ch] = (rev - cost) / cost
            else:
                channel_roi[ch] = 0.0

        # Top paths
        sorted_paths = sorted(path_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]
        top_paths = [{"path": list(p), "count": count} for p, count in sorted_paths]

        avg_latency = sum(journey_latencies) / len(journey_latencies) if journey_latencies else 0.0

        return AttributionReport(
            tenant_id=tenant_id,
            model=model,
            channel_revenue=dict(channel_revenue),
            channel_conversions=dict(channel_conversions),
            channel_roi=channel_roi,
            top_paths=top_paths,
            average_latency_days=avg_latency,
        )
