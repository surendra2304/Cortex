"""
Cortex/apps/api/src/cortex_api/customer_segmentation_engine.py — Cortex Customer Segmentation Engine.

RFM analysis, cluster segmentation, persona creation, and
customer segment lifecycle management.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

router = APIRouter()


@dataclass
class CustomerProfile:
    """A customer profile for segmentation."""
    customer_id: str
    name: str = ""
    email: str = ""
    recency_days: int = 0
    frequency: int = 0
    monetary: float = 0.0
    segment: str = "unknown"
    persona: str = ""
    value_score: float = 0.0
    last_purchase: float = 0.0


@dataclass
class SegmentDefinition:
    """A customer segment definition."""
    segment_id: str
    name: str
    criteria: dict = field(default_factory=dict)
    customer_count: int = 0
    total_value: float = 0.0
    description: str = ""


@dataclass
class SegmentationResult:
    """Result of segmentation analysis."""
    result_id: str
    segments: list[SegmentDefinition] = field(default_factory=list)
    total_customers: int = 0
    analyzed_at: float = field(default_factory=time.time)


class CustomerSegmentationEngine:
    """Engine for customer segmentation analysis."""

    def __init__(self) -> None:
        self._customers: dict[str, CustomerProfile] = {}
        self._segments: dict[str, SegmentDefinition] = {}
        self._results: list[SegmentationResult] = []

    def add_customer(self, customer_id: str, recency_days: int, frequency: int,
                     monetary: float, name: str = "", email: str = "") -> CustomerProfile:
        """Add a customer for segmentation."""
        customer = CustomerProfile(
            customer_id=customer_id, name=name, email=email,
            recency_days=recency_days, frequency=frequency, monetary=monetary,
            last_purchase=time.time(),
        )
        self._customers[customer_id] = customer
        return customer

    def segment_customers(self) -> SegmentationResult:
        """Perform RFM segmentation on all customers."""
        result_id = f"seg_{uuid.uuid4().hex[:12]}"
        result = SegmentationResult(result_id=result_id, total_customers=len(self._customers))

        segments = {
            "champions": {"criteria": {"recency_max": 30, "frequency_min": 10, "monetary_min": 1000}, "customers": []},
            "loyal": {"criteria": {"recency_max": 90, "frequency_min": 5, "monetary_min": 500}, "customers": []},
            "potential_loyalist": {"criteria": {"recency_max": 90, "frequency_min": 2, "monetary_min": 100}, "customers": []},
            "new_customers": {"criteria": {"recency_max": 30, "frequency_min": 1, "monetary_min": 0}, "customers": []},
            "promising": {"criteria": {"recency_max": 60, "frequency_min": 1, "monetary_min": 50}, "customers": []},
            "at_risk": {"criteria": {"recency_max": 180, "frequency_min": 1, "monetary_min": 0}, "customers": []},
            "cannot_loose": {"criteria": {"recency_max": 365, "frequency_min": 5, "monetary_min": 2000}, "customers": []},
            "hibernating": {"criteria": {"recency_max": 365, "frequency_min": 1, "monetary_min": 0}, "customers": []},
        }

        for customer in self._customers.values():
            assigned = False
            for seg_name, seg_info in segments.items():
                criteria = seg_info["criteria"]
                if customer.recency_days <= criteria.get("recency_max", 9999) and \
                   customer.frequency >= criteria.get("frequency_min", 0) and \
                   customer.monetary >= criteria.get("monetary_min", 0):
                    seg_info["customers"].append(customer)
                    customer.segment = seg_name
                    customer.persona = f"{seg_name}_customer"
                    customer.value_score = (customer.frequency * 0.3 + customer.monetary / 100) * 0.7
                    assigned = True
                    break
            if not assigned:
                customer.segment = "other"
                customer.persona = "general_customer"

        # Create segment definitions
        for seg_name, seg_info in segments.items():
            seg_id = f"segdef_{uuid.uuid4().hex[:8]}"
            seg_def = SegmentDefinition(
                segment_id=seg_id,
                name=seg_name,
                criteria=seg_info["criteria"],
                customer_count=len(seg_info["customers"]),
                total_value=sum(c.monetary for c in seg_info["customers"]),
                description=f"{seg_name} segment with {len(seg_info['customers'])} customers",
            )
            result.segments.append(seg_def)
            self._segments[seg_id] = seg_def

        self._results.append(result)
        return result

    def get_segments(self) -> list[dict[str, Any]]:
        """Get all segment definitions."""
        return [
            {
                "segment_id": s.segment_id,
                "name": s.name,
                "customer_count": s.customer_count,
                "total_value": s.total_value,
                "description": s.description,
            }
            for s in self._segments.values()
        ]

    def get_customers_in_segment(self, segment_name: str) -> list[dict[str, Any]]:
        """Get customers in a specific segment."""
        return [
            {
                "customer_id": c.customer_id,
                "name": c.name,
                "recency_days": c.recency_days,
                "frequency": c.frequency,
                "monetary": c.monetary,
                "persona": c.persona,
            }
            for c in self._customers.values() if c.segment == segment_name
        ]

    def get_report(self) -> dict[str, Any]:
        """Get engine report."""
        return {
            "total_customers": len(self._customers),
            "total_segments": len(self._segments),
            "engine_status": "operational",
        }


engine = CustomerSegmentationEngine()


@router.post("/cortex/segmentation/customers")
async def add_customer(customer_id: str, recency_days: int, frequency: int, monetary: float,
                       name: str = "", email: str = ""):
    """Add a customer for segmentation."""
    customer = engine.add_customer(customer_id, recency_days, frequency, monetary, name, email)
    return {"customer_id": customer.customer_id, "segment": customer.segment}


@router.post("/cortex/segmentation/analyze")
async def segment_customers():
    """Perform customer segmentation."""
    result = engine.segment_customers()
    return {
        "result_id": result.result_id,
        "total_customers": result.total_customers,
        "segment_count": len(result.segments),
        "segments": [
            {"name": s.name, "customers": s.customer_count, "total_value": s.total_value}
            for s in result.segments
        ],
    }


@router.get("/cortex/segmentation/segments")
async def get_segments():
    """Get all segments."""
    return {"segments": engine.get_segments()}


@router.get("/cortex/segmentation/segments/{segment_name}/customers")
async def get_customers_in_segment(segment_name: str):
    """Get customers in a segment."""
    return {"customers": engine.get_customers_in_segment(segment_name)}


@router.get("/cortex/segmentation/report")
async def segmentation_report():
    """Get segmentation report."""
    return engine.get_report()
