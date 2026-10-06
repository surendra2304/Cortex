import logging
import uuid
from datetime import UTC, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from cortex_api.db_models import MemoryEntryModel
from pydantic import BaseModel, Field
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_upgrade.audit import redact
from cortex_upgrade.learning import StrategyLearner
from cortex_upgrade.memory import ScopedMemory


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-memory")


class TrustLabel(str, Enum):
    SYSTEM_FACT = "system_fact"
    VERIFIED_TELEMETRY = "verified_telemetry"
    UNTRUSTED_USER_INPUT = "untrusted_user_input"
    INFERRED_PROFILE = "inferred_profile"


class MemoryScope(str, Enum):
    VISITOR = "visitor"
    LEAD = "lead"
    CUSTOMER = "customer"
    SITE = "site"
    STRATEGY = "strategy"


class MemoryEntry(BaseModel):
    id: str
    tenant_id: str = "default"
    scope: str
    scope_id: str
    key: str
    content: dict[str, Any] = Field(default_factory=dict)
    trust_label: str = TrustLabel.VERIFIED_TELEMETRY.value
    source: str = "cognitive_loop"
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = None


class MemoryStore:
    """
    Memory Service per CORTEX spec:
    - Scoped storage: visitor, lead, customer, site, strategy
    - Trust classification defense against prompt injection
    - Outcome memory: records strategy performance (e.g. banner lift)
    """

    def __init__(self):
        self._in_memory: dict[str, list[MemoryEntry]] = {}
        self.scoped_memory = ScopedMemory()

    async def put(
        self,
        db: AsyncSession | None,
        scope: str,
        scope_id: str,
        key: str,
        content: dict[str, Any],
        trust_label: str = TrustLabel.VERIFIED_TELEMETRY.value,
        tenant_id: str = "default",
        source: str = "cognitive_loop",
        ttl_days: int | None = None,
    ) -> MemoryEntry:
        entry_id = f"mem_{uuid.uuid4().hex[:10]}"
        now = datetime.now(UTC)
        expires_at = now + timedelta(days=ttl_days) if ttl_days else None
        safe_content = redact(content)

        entry = MemoryEntry(
            id=entry_id,
            tenant_id=tenant_id,
            scope=scope,
            scope_id=scope_id,
            key=key,
            content=safe_content,
            trust_label=trust_label,
            source=source,
            created_at=now,
            expires_at=expires_at,
        )

        # Store in local fast cache (tenant-scoped key prevents cross-tenant collisions)
        cache_key = f"{tenant_id}:{scope}:{scope_id}"
        self._in_memory.setdefault(cache_key, []).append(entry)

        # Persist to database if session provided
        if db:
            try:
                db_model = MemoryEntryModel(
                    id=entry.id,
                    tenant_id=entry.tenant_id,
                    scope=entry.scope,
                    scope_id=entry.scope_id,
                    key=entry.key,
                    content=entry.content,
                    trust_label=entry.trust_label,
                    source=entry.source,
                    created_at=entry.created_at,
                    expires_at=entry.expires_at,
                )
                db.add(db_model)
                await db.commit()
            except Exception as exc:
                logger.warning(f"Failed to persist memory entry {entry_id}: {exc}")
                await db.rollback()

        return entry

    async def get(
        self, db: AsyncSession | None, scope: str, scope_id: str, key: str | None = None, tenant_id: str | None = None
    ) -> list[MemoryEntry]:
        """Fetch scoped memory entries.

        ``tenant_id`` is mandatory for database reads: without it a caller could
        read another tenant's memory that happens to share a scope identifier
        (audit defect H1).  The in-process cache is keyed by tenant as well.
        """
        if db:
            if not tenant_id:
                raise ValueError("tenant_id is required to read memory from the database")
            try:
                stmt = select(MemoryEntryModel).where(
                    MemoryEntryModel.tenant_id == tenant_id,
                    MemoryEntryModel.scope == scope,
                    MemoryEntryModel.scope_id == scope_id,
                )
                if key:
                    stmt = stmt.where(MemoryEntryModel.key == key)
                stmt = stmt.order_by(desc(MemoryEntryModel.created_at))
                res = await db.execute(stmt)
                records = res.scalars().all()
                return [
                    MemoryEntry(
                        id=r.id,
                        tenant_id=r.tenant_id,
                        scope=r.scope,
                        scope_id=r.scope_id,
                        key=r.key,
                        content=r.content,
                        trust_label=r.trust_label,
                        source=r.source,
                        created_at=r.created_at,
                        expires_at=r.expires_at,
                    )
                    for r in records
                ]
            except Exception as exc:
                logger.warning(f"DB memory fetch failed: {exc}")

        cache_key = f"{tenant_id or 'default'}:{scope}:{scope_id}"
        entries = self._in_memory.get(cache_key, [])
        if key:
            return [e for e in entries if e.key == key]
        return entries

    async def record_strategy_outcome(
        self,
        db: AsyncSession | None,
        strategy_name: str,
        context_features: dict[str, Any],
        action_taken: str,
        outcome_lift_pct: float,
        sample_size: int = 1,
    ) -> MemoryEntry:
        """Records strategy learning in strategy scope memory."""
        content = {
            "strategy": strategy_name,
            "action": action_taken,
            "context_features": context_features,
            "measured_lift_pct": outcome_lift_pct,
            "sample_size": sample_size,
            "recorded_at": _utcnow().isoformat(),
        }
        return await self.put(
            db=db,
            scope=MemoryScope.STRATEGY.value,
            scope_id=strategy_name,
            key="outcome_learning",
            content=content,
            trust_label=TrustLabel.VERIFIED_TELEMETRY.value,
            source="cognitive_loop:measure",
        )

    async def record_outcome(
        self,
        db: AsyncSession | None,
        action_id: str,
        action_type: str,
        context_snapshot: dict[str, Any],
        verdict: str,
        metric_delta: dict[str, Any],
    ) -> MemoryEntry:
        """Records granular outcome measurement and updates strategy rollups."""
        content = {
            "action_id": action_id,
            "action_type": action_type,
            "context_snapshot": context_snapshot,
            "verdict": verdict,
            "metric_delta": metric_delta,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        return await self.put(
            db=db,
            scope=MemoryScope.STRATEGY.value,
            scope_id=action_type,
            key=f"outcome_{action_id}",
            content=content,
            trust_label=TrustLabel.VERIFIED_TELEMETRY.value,
            source="outcome_tracker",
        )

    async def get_strategy_performance(self, strategy_name: str) -> dict[str, Any]:
        """Calculates success rate and auto-promotion/demotion status using StrategyLearner with sample size guard."""
        entries = await self.get(db=None, scope=MemoryScope.STRATEGY.value, scope_id=strategy_name, tenant_id="default")
        outcomes = [e.content for e in entries if "verdict" in e.content]
        total = len(outcomes)
        if total == 0:
            return {"strategy": strategy_name, "total_executions": 0, "success_rate": 0.0, "status": "CANDIDATE"}

        successes = sum(1 for o in outcomes if o.get("verdict") == "SUCCESS")
        rate = successes / total

        learner = StrategyLearner(promote_at=0.60, demote_at=0.30, min_samples=20)
        for o in outcomes:
            learner.observe(strategy_name, won=(o.get("verdict") == "SUCCESS"))
        disp = learner.disposition(strategy_name)

        status = "CANDIDATE"
        if total >= 20 and rate >= 0.60:
            status = "PROVEN"
        elif total >= 10 and rate < 0.30:
            status = "DEMOTED"

        return {
            "strategy": strategy_name,
            "total_executions": total,
            "success_rate": rate,
            "status": status,
            "disposition": disp,
            "min_samples_met": total >= 20,
        }
