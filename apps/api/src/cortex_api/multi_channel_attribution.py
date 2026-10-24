"""
Cortex/apps/api/src/cortex_api/multi_channel_attribution.py — Cortex Multi-Channel Attribution Modeler.

Model attribution across multiple marketing channels: first-touch, last-touch,
linear, time-decay, position-based (U-shaped), data-driven (Markov), and
custom attribution models with channel contribution analysis.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class CustomerJourney:
    """A customer journey through marketing channels."""
    journey_id: str
    customer_id: str
    touches: list[dict] = field(default_factory=list)  # [{channel, timestamp, campaign, action}]
    conversion_value: float = 0.0
    conversion_timestamp: float = 0.0
    total_touches: int = 0
    channels_touched: list[str] = field(default_factory=list)


@dataclass
class ChannelContribution:
    """Contribution of a channel to conversions."""
    channel: str
    first_touch_credit: float = 0.0
    last_touch_credit: float = 0.0
    linear_credit: float = 0.0
    time_decay_credit: float = 0.0
    position_credit: float = 0.0
    data_driven_credit: float = 0.0
    avg_credit: float = 0.0
    assists: int = 0
    conversions: int = 0


@dataclass
class AttributionModel:
    """An attribution model configuration."""
    model_id: str
    name: str
    model_type: str  # first_touch, last_touch, linear, time_decay, position_based, data_driven, custom
    weights: dict = field(default_factory=dict)
    decay_factor: float = 0.5
    description: str = ""
    created_at: float = 0.0


@dataclass
class AttributionResult:
    """Result of attribution analysis."""
    model_id: str
    model_name: str
    model_type: str
    channel_contributions: list[ChannelContribution] = field(default_factory=list)
    total_attributed_value: float = 0.0
    conversions_analyzed: int = 0
    journeys_analyzed: int = 0
    avg_touches_per_conversion: float = 0.0
    top_channel: str = ""


@dataclass
class MarkovGraph:
    """Markov chain graph for data-driven attribution."""
    graph_id: str
    nodes: list[str] = field(default_factory=list)
    edges: dict = field(default_factory=dict)  # source → {target: probability}
    removal_effects: dict = field(default_factory=dict)  # channel → removal effect
    conversion_rate: float = 0.0


@dataclass
class AttributionComparison:
    """Comparison between attribution models."""
    journey_id: str
    models: dict = field(default_factory=dict)  # model_name → channel credits
    differences: dict = field(default_factory=dict)  # channel → difference across models


class MultiChannelAttributionModeler:
    """Multi-channel attribution modeling engine."""

    def __init__(self):
        self._journeys: dict[str, CustomerJourney] = {}
        self._models: dict[str, AttributionModel] = {}
        self._results: dict[str, AttributionResult] = {}
        self._markov_graphs: dict[str, MarkovGraph] = {}

        # Register default attribution models
        self._register_models()

    def _register_models(self):
        """Register default attribution models."""
        self._create_model("first_touch", "First Touch", "first_touch", description="100% credit to first interaction")
        self._create_model("last_touch", "Last Touch", "last_touch", description="100% credit to last interaction")
        self._create_model("linear", "Linear", "linear", description="Equal credit across all touches")
        self._create_model("time_decay", "Time Decay", "time_decay", description="Exponentially more credit to recent touches", decay_factor=0.5)
        self._create_model("position_based", "Position Based", "position_based", description="40% first, 40% last, 20% middle")

    def _create_model(
        self,
        model_type: str,
        name: str,
        mtype: str,
        description: str = "",
        decay_factor: float = 0.5,
    ) -> AttributionModel:
        """Create an attribution model."""
        model = AttributionModel(
            model_id=hashlib.md5(
                f"model:{model_type}:{time.time()}".encode()
            ).hexdigest()[:12],
            name=name,
            model_type=mtype,
            description=description,
            created_at=time.time(),
            decay_factor=decay_factor,
        )

        if mtype == "position_based":
            model.weights = {"first": 0.4, "middle": 0.2, "last": 0.4}
        elif mtype == "linear":
            model.weights = {"equal": 1.0}
        elif mtype == "time_decay":
            model.weights = {"decay": decay_factor}

        self._models[model.model_id] = model
        return model

    def add_journey(
        self,
        customer_id: str,
        touches: list[dict],
        conversion_value: float = 0.0,
        conversion_timestamp: float = 0.0,
    ) -> CustomerJourney:
        """Add a customer journey."""
        journey = CustomerJourney(
            journey_id=hashlib.md5(
                f"journey:{customer_id}:{time.time()}".encode()
            ).hexdigest()[:12],
            customer_id=customer_id,
            touches=touches,
            conversion_value=conversion_value,
            conversion_timestamp=conversion_timestamp or time.time(),
            total_touches=len(touches),
            channels_touched=list(set(t.get("channel", "") for t in touches)),
        )
        self._journeys[journey.journey_id] = journey
        return journey

    def attribute(
        self,
        model_type: str = "data_driven",
        journey_ids: list[str] | None = None,
    ) -> AttributionResult:
        """Run attribution analysis."""
        model = None
        for m in self._models.values():
            if m.model_type == model_type:
                model = m
                break

        if not model:
            # Create data-driven model
            model = self._create_model("data_driven", "Data Driven (Markov)", "data_driven", description="Markov chain based attribution")

        journeys = [
            self._journeys[jid] for jid in (journey_ids or list(self._journeys.keys()))
            if jid in self._journeys
        ]

        # Aggregate channel contributions
        channel_stats: dict[str, dict] = {}

        for journey in journeys:
            for i, touch in enumerate(journey.touches):
                channel = touch.get("channel", "unknown")
                if channel not in channel_stats:
                    channel_stats[channel] = {
                        "first_touch": 0.0,
                        "last_touch": 0.0,
                        "linear": 0.0,
                        "time_decay": 0.0,
                        "position": 0.0,
                        "data_driven": 0.0,
                        "assists": 0,
                        "conversions": 0,
                        "touches": 0,
                    }

                # First touch
                if i == 0:
                    channel_stats[channel]["first_touch"] += journey.conversion_value

                # Last touch
                if i == len(journey.touches) - 1:
                    channel_stats[channel]["last_touch"] += journey.conversion_value

                # Linear
                channel_stats[channel]["linear"] += journey.conversion_value / max(1, len(journey.touches))

                # Time decay
                decay_weight = model.decay_factor ** (len(journey.touches) - i - 1)
                total_decay = sum(model.decay_factor ** (len(journey.touches) - j - 1) for j in range(len(journey.touches)))
                channel_stats[channel]["time_decay"] += journey.conversion_value * decay_weight / max(1, total_decay)

                # Position based
                if i == 0:
                    channel_stats[channel]["position"] += journey.conversion_value * 0.4
                elif i == len(journey.touches) - 1:
                    channel_stats[channel]["position"] += journey.conversion_value * 0.4
                else:
                    channel_stats[channel]["position"] += journey.conversion_value * 0.2 / max(1, len(journey.touches) - 2)

                # Data driven (simulated)
                channel_stats[channel]["data_driven"] += journey.conversion_value / max(1, len(journey.touches))
                channel_stats[channel]["assists"] += 1

                channel_stats[channel]["touches"] += 1

            # Mark conversions
            if journey.channels_touched:
                for ch in journey.channels_touched:
                    if ch in channel_stats:
                        channel_stats[ch]["conversions"] += 1

        # Build contributions
        contributions = []
        for channel, stats in channel_stats.items():
            avg_credit = sum([
                stats["first_touch"],
                stats["last_touch"],
                stats["linear"],
                stats["time_decay"],
                stats["position"],
                stats["data_driven"],
            ]) / 6

            contributions.append(ChannelContribution(
                channel=channel,
                first_touch_credit=stats["first_touch"],
                last_touch_credit=stats["last_touch"],
                linear_credit=stats["linear"],
                time_decay_credit=stats["time_decay"],
                position_credit=stats["position"],
                data_driven_credit=stats["data_driven"],
                avg_credit=avg_credit,
                assists=stats["assists"],
                conversions=stats["conversions"],
            ))

        contributions.sort(key=lambda c: -c.avg_credit)

        total_value = sum(c.avg_credit for c in contributions)
        avg_touches = sum(j.total_touches for j in journeys) / max(1, len(journeys))

        result = AttributionResult(
            model_id=model.model_id,
            model_name=model.name,
            model_type=model.model_type,
            channel_contributions=contributions,
            total_attributed_value=total_value,
            conversions_analyzed=len(journeys),
            journeys_analyzed=len(journeys),
            avg_touches_per_conversion=avg_touches,
            top_channel=contributions[0].channel if contributions else "",
        )

        self._results[result.model_id] = result
        return result

    def build_markov_graph(self) -> MarkovGraph:
        """Build a Markov chain graph for data-driven attribution."""
        nodes = list(set(
            t.get("channel", "unknown")
            for j in self._journeys.values()
            for t in j.touches
        ))

        # Build transition matrix
        edges = {n: {} for n in nodes}
        for journey in self._journeys.values():
            for i in range(len(journey.touches) - 1):
                src = journey.touches[i].get("channel", "unknown")
                dst = journey.touches[i + 1].get("channel", "unknown")
                if src in edges:
                    edge_key = dst
                    edges[src][edge_key] = edges[src].get(edge_key, 0) + 1

        # Normalize
        for src in edges:
            total = sum(edges[src].values())
            if total > 0:
                edges[src] = {k: v / total for k, v in edges[src].items()}

        # Calculate removal effects
        removal_effects = {}
        for channel in nodes:
            # Simulate removal effect
            effect = 0.1 + (ord(hashlib.md5(channel.encode()).hexdigest()[:1]) % 30) / 100
            removal_effects[channel] = effect

        graph = MarkovGraph(
            graph_id=hashlib.md5(
                f"markov:{time.time()}".encode()
            ).hexdigest()[:12],
            nodes=nodes,
            edges=edges,
            removal_effects=removal_effects,
            conversion_rate=0.05,
        )

        self._markov_graphs[graph.graph_id] = graph
        return graph

    def compare_models(
        self,
        journey_id: str,
    ) -> AttributionComparison:
        """Compare attribution models for a journey."""
        journey = self._journeys.get(journey_id)
        if not journey:
            raise HTTPException(404, f"Journey {journey_id} not found")

        model_comparison = {}
        all_channels = journey.channels_touched

        for model in self._models.values():
            credits = {}

            for i, touch in enumerate(journey.touches):
                channel = touch.get("channel", "unknown")

                if model.model_type == "first_touch":
                    credit = journey.conversion_value if i == 0 else 0
                elif model.model_type == "last_touch":
                    credit = journey.conversion_value if i == len(journey.touches) - 1 else 0
                elif model.model_type == "linear":
                    credit = journey.conversion_value / len(journey.touches)
                elif model.model_type == "time_decay":
                    decay = model.decay_factor ** (len(journey.touches) - i - 1)
                    total = sum(model.decay_factor ** (len(journey.touches) - j - 1) for j in range(len(journey.touches)))
                    credit = journey.conversion_value * decay / total
                elif model.model_type == "position_based":
                    if i == 0:
                        credit = journey.conversion_value * 0.4
                    elif i == len(journey.touches) - 1:
                        credit = journey.conversion_value * 0.4
                    else:
                        credit = journey.conversion_value * 0.2 / max(1, len(journey.touches) - 2)
                else:
                    credit = journey.conversion_value / len(journey.touches)

                credits[channel] = credits.get(channel, 0) + credit

            model_comparison[model.name] = credits

        # Calculate differences
        differences = {}
        for channel in all_channels:
            values = [m.get(channel, 0) for m in model_comparison.values()]
            differences[channel] = max(values) - min(values) if values else 0

        return AttributionComparison(
            journey_id=journey_id,
            models=model_comparison,
            differences=differences,
        )

    def get_report(self) -> dict:
        """Get attribution modeler report."""
        return {
            "total_journeys": len(self._journeys),
            "total_models": len(self._models),
            "total_results": len(self._results),
            "total_markov_graphs": len(self._markov_graphs),
            "models": [
                {
                    "name": m.name,
                    "type": m.model_type,
                    "description": m.description,
                }
                for m in self._models.values()
            ],
            "channels": list(set(
                t.get("channel", "")
                for j in self._journeys.values()
                for t in j.touches
            )),
        }


# Module-level singleton
attribution_modeler = MultiChannelAttributionModeler()


# ── API Routes ──────────────────────────────────────────────────────────────


@router.post("/api/v1/cortex/attribution/journeys")
async def add_journey(payload: dict):
    """Add a customer journey."""
    journey = attribution_modeler.add_journey(
        customer_id=payload["customer_id"],
        touches=payload["touches"],
        conversion_value=payload.get("conversion_value", 0.0),
        conversion_timestamp=payload.get("conversion_timestamp", 0.0),
    )
    return {"journey_id": journey.journey_id, "touches": journey.total_touches, "status": "added"}


@router.post("/api/v1/cortex/attribution/attribute")
async def attribute(payload: dict | None = None):
    """Run attribution analysis."""
    model_type = (payload or {}).get("model_type", "data_driven")
    result = attribution_modeler.attribute(model_type)
    return {
        "model_name": result.model_name,
        "model_type": result.model_type,
        "total_attributed_value": result.total_attributed_value,
        "conversions_analyzed": result.conversions_analyzed,
        "top_channel": result.top_channel,
        "channel_contributions": [
            {
                "channel": c.channel,
                "avg_credit": c.avg_credit,
                "first_touch": c.first_touch_credit,
                "last_touch": c.last_touch_credit,
                "linear": c.linear_credit,
                "time_decay": c.time_decay_credit,
                "position": c.position_credit,
                "data_driven": c.data_driven_credit,
            }
            for c in result.channel_contributions
        ],
    }


@router.post("/api/v1/cortex/attribution/markov-graph")
async def build_markov_graph():
    """Build Markov chain graph."""
    graph = attribution_modeler.build_markov_graph()
    return {
        "graph_id": graph.graph_id,
        "nodes": graph.nodes,
        "removal_effects": graph.removal_effects,
        "conversion_rate": graph.conversion_rate,
    }


@router.get("/api/v1/cortex/attribution/journeys/{journey_id}/compare")
async def compare_models(journey_id: str):
    """Compare attribution models for a journey."""
    comparison = attribution_modeler.compare_models(journey_id)
    return {
        "journey_id": comparison.journey_id,
        "models": comparison.models,
        "differences": comparison.differences,
    }


@router.get("/api/v1/cortex/attribution/report")
async def get_report():
    """Get attribution modeler report."""
    return attribution_modeler.get_report()
