from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import math
from pydantic import BaseModel, Field
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

logger = logging.getLogger("cortex-experimentation")


class ExperimentStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    CONCLUDED = "CONCLUDED"
    ARCHIVED = "ARCHIVED"


class ExperimentVariant(BaseModel):
    id: str
    name: str
    weight: float = 0.5  # Traffic allocation ratio
    payload: Dict[str, Any] = Field(default_factory=dict)
    visitors_count: int = 0
    conversions_count: int = 0
    revenue_total: float = 0.0


class ExperimentDefinition(BaseModel):
    id: str
    name: str
    hypothesis: str
    target_page: str = "/"
    primary_metric: str = "conversion_rate"
    variants: List[ExperimentVariant] = Field(default_factory=list)
    min_sample_size: int = 100
    status: ExperimentStatus = ExperimentStatus.ACTIVE
    winner_variant_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExperimentationEngine:
    """
    Production A/B Testing & Personalization Engine per CORTEX spec section 9:
    - Deterministic sticky variant assignment via MD5 hash of visitor_id + experiment_id
    - Real-time conversion and engagement metric tracking per variant
    - Statistical significance calculation using two-proportion z-test (p < 0.05 / z > 1.96)
    - Dynamic rule-based personalization and recommendation scoring
    """

    def assign_variant(self, visitor_id: str, experiment: ExperimentDefinition) -> ExperimentVariant:
        """Deterministically assign variant based on visitor_id hash."""
        if not experiment.variants:
            raise ValueError("Experiment has no variants defined.")

        hash_input = f"{experiment.id}:{visitor_id}".encode("utf-8")
        hash_val = int(hashlib.md5(hash_input).hexdigest(), 16) % 100

        cumulative = 0.0
        for variant in experiment.variants:
            cumulative += variant.weight * 100
            if hash_val < cumulative:
                return variant

        return experiment.variants[0]

    def calculate_significance(
        self,
        control: ExperimentVariant,
        treatment: ExperimentVariant
    ) -> Dict[str, Any]:
        """Calculates two-proportion z-test for conversion rate difference."""
        n1 = control.visitors_count
        n2 = treatment.visitors_count
        x1 = control.conversions_count
        x2 = treatment.conversions_count

        if n1 < 10 or n2 < 10:
            return {
                "statistically_significant": False,
                "p_value": 1.0,
                "z_score": 0.0,
                "confidence_pct": 0.0,
                "reason": "Insufficient sample size (minimum 10 per variant required)"
            }

        p1 = x1 / n1
        p2 = x2 / n2
        p_pool = (x1 + x2) / (n1 + n2)

        se = math.sqrt(p_pool * (1 - p_pool) * ((1 / n1) + (1 / n2)))
        if se == 0:
            return {
                "statistically_significant": False,
                "p_value": 1.0,
                "z_score": 0.0,
                "confidence_pct": 0.0,
                "reason": "Standard error is zero"
            }

        z_score = (p2 - p1) / se
        # Approximate two-tailed p-value
        p_value = 2 * (1 - 0.5 * (1 + math.erf(abs(z_score) / math.sqrt(2))))
        is_significant = abs(z_score) >= 1.96 and p_value < 0.05

        return {
            "statistically_significant": is_significant,
            "z_score": round(z_score, 4),
            "p_value": round(p_value, 4),
            "confidence_pct": round((1 - p_value) * 100, 2),
            "control_cr": round(p1 * 100, 2),
            "treatment_cr": round(p2 * 100, 2),
            "relative_lift_pct": round(((p2 - p1) / max(p1, 0.0001)) * 100, 2)
        }

    def evaluate_personalization_rules(
        self,
        visitor_traits: Dict[str, Any],
        page_path: str,
        rules: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Matches visitor context (device, segment, source) to dynamic content variants."""
        for rule in rules:
            target_segment = rule.get("segment")
            target_device = rule.get("device")
            target_path = rule.get("path")

            if target_path and target_path != page_path:
                continue
            if target_segment and visitor_traits.get("segment") != target_segment:
                continue
            if target_device and visitor_traits.get("device") != target_device:
                continue

            return rule.get("experience_payload")

        return None
