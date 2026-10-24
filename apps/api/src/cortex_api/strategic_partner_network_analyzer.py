"""
Cortex/apps/api/src/cortex_api/strategic_partner_network_analyzer.py — Cortex Strategic Partner Network Analyzer.

Partner ecosystem analysis, network graph mapping, relationship optimization,
and strategic alliance recommendations.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class PartnerNode:
    """A partner in the network."""
    partner_id: str
    name: str
    category: str = "vendor"  # vendor, customer, ally, competitor, regulator
    influence: float = 0.5
    trust_score: float = 0.5
    cooperation_level: str = "neutral"  # hostile, neutral, cooperative, strategic
    connections: list[str] = field(default_factory=list)


@dataclass
class NetworkEdge:
    """An edge in the partner network."""
    source: str
    target: str
    relationship_type: str = "supply"  # supply, distribution, co_development, co_marketing
    strength: float = 0.5
    revenue_flow: float = 0.0


@dataclass
class NetworkAnalysis:
    """Analysis of the partner network."""
    analysis_id: str
    total_partners: int = 0
    total_edges: int = 0
    density: float = 0.0
    central_partners: list[str] = field(default_factory=list)
    bottlenecks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    generated_at: float = field(default_factory=time.time)


class StrategicPartnerNetworkAnalyzer:
    """Engine for strategic partner network analysis."""

    def __init__(self) -> None:
        self._partners: dict[str, PartnerNode] = {}
        self._edges: list[NetworkEdge] = []
        self._analyses: list[NetworkAnalysis] = []

    def add_partner(self, name: str, category: str = "vendor",
                    influence: float = 0.5, trust_score: float = 0.5,
                    cooperation_level: str = "neutral") -> PartnerNode:
        """Add a partner to the network."""
        partner_id = f"p_{uuid.uuid4().hex[:12]}"
        partner = PartnerNode(
            partner_id=partner_id, name=name, category=category,
            influence=influence, trust_score=trust_score,
            cooperation_level=cooperation_level,
        )
        self._partners[partner_id] = partner
        return partner

    def add_connection(self, source_id: str, target_id: str,
                       relationship_type: str = "supply",
                       strength: float = 0.5, revenue_flow: float = 0.0) -> NetworkEdge:
        """Add a connection between partners."""
        if source_id not in self._partners or target_id not in self._partners:
            raise HTTPException(status_code=404, detail="Partner not found")

        edge = NetworkEdge(
            source=source_id, target=target_id,
            relationship_type=relationship_type,
            strength=strength, revenue_flow=revenue_flow,
        )
        self._edges.append(edge)
        self._partners[source_id].connections.append(target_id)
        self._partners[target_id].connections.append(source_id)
        return edge

    def analyze_network(self) -> NetworkAnalysis:
        """Analyze the partner network."""
        analysis_id = f"net_{uuid.uuid4().hex[:12]}"
        analysis = NetworkAnalysis(analysis_id=analysis_id)
        analysis.total_partners = len(self._partners)
        analysis.total_edges = len(self._edges)

        # Calculate network density
        max_edges = len(self._partners) * (len(self._partners) - 1) / 2
        analysis.density = len(self._edges) / max(1, max_edges)

        # Find central partners
        centrality = {
            pid: len(p.connections) for pid, p in self._partners.items()
        }
        sorted_central = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
        analysis.central_partners = [
            self._partners[pid].name for pid, _ in sorted_central[:3]
        ]

        # Find bottlenecks (high-influence partners with low cooperation)
        for partner in self._partners.values():
            if partner.influence > 0.7 and partner.cooperation_level in ("neutral", "hostile"):
                analysis.bottlenecks.append(f"{partner.name}: High influence but low cooperation")

        # Generate recommendations
        analysis.recommendations = [
            "Strengthen relationships with central partners",
            "Reduce dependence on bottleneck partners",
            "Add alternative partners for critical connections",
        ]

        self._analyses.append(analysis)
        return analysis

    def get_partners(self, category: str | None = None) -> list[dict[str, Any]]:
        """Get partners."""
        partners = list(self._partners.values())
        if category:
            partners = [p for p in partners if p.category == category]
        return [
            {"name": p.name, "category": p.category, "influence": p.influence,
             "trust_score": p.trust_score, "connections": len(p.connections)}
            for p in partners
        ]

    def get_report(self) -> dict[str, Any]:
        """Get engine report."""
        return {
            "total_partners": len(self._partners),
            "total_edges": len(self._edges),
            "total_analyses": len(self._analyses),
            "engine_status": "operational",
        }


engine = StrategicPartnerNetworkAnalyzer()


@router.post("/cortex/network/partners")
async def add_partner(name: str, category: str = "vendor", influence: float = 0.5,
                      trust_score: float = 0.5, cooperation_level: str = "neutral"):
    """Add a partner to the network."""
    partner = engine.add_partner(name, category, influence, trust_score, cooperation_level)
    return {"partner_id": partner.partner_id, "name": partner.name}


@router.post("/cortex/network/connections")
async def add_connection(source_id: str, target_id: str, relationship_type: str = "supply",
                         strength: float = 0.5, revenue_flow: float = 0.0):
    """Add a connection between partners."""
    edge = engine.add_connection(source_id, target_id, relationship_type, strength, revenue_flow)
    return {"source": edge.source, "target": edge.target, "strength": edge.strength}


@router.post("/cortex/network/analyze")
async def analyze_network():
    """Analyze the partner network."""
    analysis = engine.analyze_network()
    return {
        "analysis_id": analysis.analysis_id,
        "total_partners": analysis.total_partners,
        "density": analysis.density,
        "central_partners": analysis.central_partners,
        "bottlenecks": analysis.bottlenecks,
    }


@router.get("/cortex/network/partners")
async def get_partners(category: str | None = None):
    """Get partners."""
    return {"partners": engine.get_partners(category)}


@router.get("/cortex/network/report")
async def network_report():
    """Get network analyzer report."""
    return engine.get_report()
