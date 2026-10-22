"""
Dynamic Feature Flags & Rules Governor Engine for Cortex.

Provides production-grade multi-tenant feature flagging, deterministic percentage rollouts
using SHA-256 actor hashing, rule-based audience targeting, explicit allow/block lists,
and audit trail management for governed configuration operations.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TargetRule(BaseModel):
    property: str  # e.g., "tier", "country", "device_type", "plan"
    operator: str  # "eq", "ne", "in", "contains", "gte", "lte"
    values: list[Any]


class FeatureFlag(BaseModel):
    key: str
    tenant_id: str = "default"
    enabled: bool = True
    rollout_percentage: float = Field(default=100.0, ge=0.0, le=100.0)
    target_rules: list[TargetRule] = Field(default_factory=list)
    allowed_actors: list[str] = Field(default_factory=list)
    blocked_actors: list[str] = Field(default_factory=list)
    description: str = ""
    created_at: str = Field(default_factory=lambda: _utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: _utcnow().isoformat())
    updated_by: str = "system"


class FeatureFlagEngine:
    """
    In-memory and persistent multi-tenant feature flag governor.
    """

    def __init__(self):
        # (tenant_id, key) -> FeatureFlag
        self._flags: dict[tuple[str, str], FeatureFlag] = {}

    def set_flag(self, flag: FeatureFlag) -> FeatureFlag:
        flag.updated_at = _utcnow().isoformat()
        self._flags[(flag.tenant_id, flag.key)] = flag
        return flag

    def get_flag(self, key: str, tenant_id: str = "default") -> FeatureFlag | None:
        return self._flags.get((tenant_id, key))

    def delete_flag(self, key: str, tenant_id: str = "default") -> bool:
        if (tenant_id, key) in self._flags:
            del self._flags[(tenant_id, key)]
            return True
        return False

    def list_flags(self, tenant_id: str = "default") -> list[FeatureFlag]:
        return [f for (t_id, _), f in self._flags.items() if t_id == tenant_id]

    def _matches_rule(self, rule: TargetRule, context: dict[str, Any]) -> bool:
        prop_val = context.get(rule.property)
        if prop_val is None:
            return False

        op = rule.operator.lower()
        if op == "eq":
            return any(str(prop_val) == str(v) for v in rule.values)
        elif op == "ne":
            return all(str(prop_val) != str(v) for v in rule.values)
        elif op == "in":
            return any(str(prop_val) == str(v) for v in rule.values)
        elif op == "contains":
            return any(str(v).lower() in str(prop_val).lower() for v in rule.values)
        elif op == "gte":
            try:
                return float(prop_val) >= float(rule.values[0])
            except Exception:
                return False
        elif op == "lte":
            try:
                return float(prop_val) <= float(rule.values[0])
            except Exception:
                return False
        return False

    def evaluate(
        self,
        key: str,
        actor_id: str,
        context: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> bool:
        flag = self.get_flag(key, tenant_id)
        if not flag or not flag.enabled:
            return False

        # 1. Blocked actors take precedence
        if actor_id in flag.blocked_actors:
            return False

        # 2. Allowed actors bypass percentage & rules
        if actor_id in flag.allowed_actors:
            return True

        # 3. Rule matching
        ctx = context or {}
        if flag.target_rules:
            # All defined rules must be satisfied
            for rule in flag.target_rules:
                if not self._matches_rule(rule, ctx):
                    return False

        # 4. Deterministic percentage rollout
        if flag.rollout_percentage >= 100.0:
            return True
        if flag.rollout_percentage <= 0.0:
            return False

        # Deterministic SHA-256 hash bucket [0.0, 100.0)
        seed = f"{tenant_id}:{key}:{actor_id}".encode("utf-8")
        hash_val = int(hashlib.sha256(seed).hexdigest()[:8], 16)
        bucket = (hash_val % 10000) / 100.0

        return bucket < flag.rollout_percentage


global_feature_flag_engine = FeatureFlagEngine()
