"""
Behavioral Audience Segment Builder & Downstream Connector Syncer for Cortex.

Provides production-grade multi-tenant dynamic audience definitions, rule-based
profile filtering, cohort evaluation, and automated schema transformations for
external marketing and CRM sync destinations (HubSpot, SendGrid, Meta CAPI, Google Ads).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SegmentRule(BaseModel):
    field: str
    operator: str  # eq, ne, gt, gte, lt, lte, in, contains
    value: Any


class AudienceSegment(BaseModel):
    id: str = Field(default_factory=lambda: f"seg_{uuid.uuid4().hex[:10]}")
    name: str
    tenant_id: str = "default"
    description: str = ""
    rules: list[SegmentRule] = Field(default_factory=list)
    match_policy: str = "ALL"  # ALL (AND) or ANY (OR)
    created_at: str = Field(default_factory=lambda: _utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class SegmentEvaluationResult(BaseModel):
    segment_id: str
    segment_name: str
    tenant_id: str
    total_profiles_evaluated: int
    matching_profiles_count: int
    match_percentage: float
    matching_profile_ids: list[str]
    evaluated_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class AudienceSegmentEngine:
    """
    Multi-tenant audience segment evaluation and downstream sync generation.
    """

    def __init__(self):
        # (tenant_id, segment_id) -> AudienceSegment
        self._segments: dict[tuple[str, str], AudienceSegment] = {}

    def save_segment(self, segment: AudienceSegment) -> AudienceSegment:
        segment.updated_at = _utcnow().isoformat()
        self._segments[(segment.tenant_id, segment.id)] = segment
        return segment

    def get_segment(self, segment_id: str, tenant_id: str = "default") -> AudienceSegment | None:
        return self._segments.get((tenant_id, segment_id))

    def list_segments(self, tenant_id: str = "default") -> list[AudienceSegment]:
        return [s for (t_id, _), s in self._segments.items() if t_id == tenant_id]

    def delete_segment(self, segment_id: str, tenant_id: str = "default") -> bool:
        if (tenant_id, segment_id) in self._segments:
            del self._segments[(tenant_id, segment_id)]
            return True
        return False

    def _evaluate_rule(self, rule: SegmentRule, profile: dict[str, Any]) -> bool:
        # Check top-level or traits dict
        val = profile.get(rule.field)
        if val is None:
            traits = profile.get("traits", {})
            val = traits.get(rule.field)
        if val is None:
            return False

        op = rule.operator.lower()
        target = rule.value

        try:
            if op == "eq":
                return str(val).lower() == str(target).lower()
            elif op == "ne":
                return str(val).lower() != str(target).lower()
            elif op == "gt":
                return float(val) > float(target)
            elif op == "gte":
                return float(val) >= float(target)
            elif op == "lt":
                return float(val) < float(target)
            elif op == "lte":
                return float(val) <= float(target)
            elif op == "in":
                target_list = target if isinstance(target, list) else [target]
                return str(val) in [str(t) for t in target_list]
            elif op == "contains":
                return str(target).lower() in str(val).lower()
        except Exception:
            return False
        return False

    def evaluate_segment(
        self,
        segment_id: str,
        profiles: list[dict[str, Any]],
        tenant_id: str = "default",
    ) -> SegmentEvaluationResult:
        segment = self.get_segment(segment_id, tenant_id)
        if not segment:
            raise KeyError(f"Audience segment '{segment_id}' not found for tenant '{tenant_id}'.")

        matching_ids: list[str] = []

        for p in profiles:
            p_tenant = p.get("tenant_id")
            if p_tenant and p_tenant != tenant_id:
                raise PermissionError(
                    f"Cross-tenant evaluation blocked: profile tenant '{p_tenant}' != segment tenant '{tenant_id}'."
                )

            pid = str(p.get("id") or p.get("profile_id") or p.get("actor_id") or "unknown")
            if not segment.rules:
                matching_ids.append(pid)
                continue

            if segment.match_policy.upper() == "ANY":
                matches = any(self._evaluate_rule(r, p) for r in segment.rules)
            else:  # ALL
                matches = all(self._evaluate_rule(r, p) for r in segment.rules)

            if matches:
                matching_ids.append(pid)

        total = len(profiles)
        match_count = len(matching_ids)
        pct = round((match_count / total * 100.0), 2) if total > 0 else 0.0

        return SegmentEvaluationResult(
            segment_id=segment.id,
            segment_name=segment.name,
            tenant_id=tenant_id,
            total_profiles_evaluated=total,
            matching_profiles_count=match_count,
            match_percentage=pct,
            matching_profile_ids=matching_ids,
        )

    def export_for_destination(
        self,
        matching_profiles: list[dict[str, Any]],
        destination: str,
    ) -> list[dict[str, Any]]:
        dest = destination.lower()
        results: list[dict[str, Any]] = []

        for p in matching_profiles:
            traits = p.get("traits", {})
            email = p.get("primary_email") or p.get("email") or traits.get("email")
            if not email:
                continue

            if dest == "hubspot":
                results.append(
                    {
                        "email": email,
                        "properties": {
                            "cortex_lead_score": p.get("score") or traits.get("lead_score", 0.0),
                            "cortex_lifecycle_stage": p.get("lifecycle_stage", "lead"),
                            "cortex_tier": traits.get("tier", "prospect"),
                        },
                    }
                )
            elif dest == "sendgrid":
                results.append(
                    {
                        "email": email,
                        "custom_fields": {
                            "lead_score": p.get("score") or traits.get("lead_score", 0.0),
                            "first_seen": p.get("created_at"),
                        },
                    }
                )
            elif dest in ("meta_capi", "facebook"):
                # SHA-256 hashed email per Meta CAPI standard
                h_email = hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
                results.append({"em": h_email, "lead_score": p.get("score", 0.0)})
            else:
                # Standard normalized export
                results.append({"email": email, "id": p.get("id"), "traits": traits})

        return results


global_audience_engine = AudienceSegmentEngine()
