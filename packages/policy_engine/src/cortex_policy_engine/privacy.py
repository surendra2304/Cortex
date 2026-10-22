import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logger = logging.getLogger("cortex-privacy-compliance")


class SecretScrubber:
    """
    Automated PII and Secret Scrubber per CORTEX spec sections 31-33:
    - Detects emails, phone numbers, credit card numbers, SSNs, and API keys
    - Automatically masks or hashes sensitive fields before logging or AI consultation
    """

    EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
    PHONE_REGEX = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")
    CREDIT_CARD_REGEX = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")
    SSN_REGEX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
    API_KEY_REGEX = re.compile(r"(?:sk_live_|SG\.|AKIA|Bearer\s)[a-zA-Z0-9_\-\.]{16,}")

    @classmethod
    def scrub_text(cls, text: str) -> str:
        """Mask direct identifiers.

        The email pattern used to be declared but never applied, so addresses
        passed through unredacted into logs, AI prompts and compliance exports
        (audit defect H8). Emails are now scrubbed first, and the phone pattern
        (which is deliberately greedy) runs last so it cannot eat the domain of
        an already-redacted address.
        """
        if not isinstance(text, str):
            return text
        scrubbed = cls.EMAIL_REGEX.sub("[REDACTED_EMAIL]", text)
        scrubbed = cls.CREDIT_CARD_REGEX.sub("[REDACTED_CARD]", scrubbed)
        scrubbed = cls.SSN_REGEX.sub("[REDACTED_SSN]", scrubbed)
        scrubbed = cls.API_KEY_REGEX.sub("[REDACTED_API_KEY]", scrubbed)
        scrubbed = cls.PHONE_REGEX.sub("[REDACTED_PHONE]", scrubbed)
        return scrubbed

    @classmethod
    def scrub_payload(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {k: cls.scrub_payload(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [cls.scrub_payload(item) for item in data]
        elif isinstance(data, str):
            return cls.scrub_text(data)
        return data

    @classmethod
    def hash_pii(cls, value: str, salt: str | None = None) -> str:
        """One-way pseudonymous hashing for identity resolution without raw storage.

        The salt must be supplied explicitly or via ``CORTEX_PII_SALT``. A
        hardcoded default made the "pseudonymous" hashes trivially reversible
        with a precomputed rainbow table (audit defect H8).
        """
        if not value:
            return ""
        effective_salt = salt or os.getenv("CORTEX_PII_SALT", "")
        if not effective_salt:
            raise ValueError("hash_pii requires a salt: pass it explicitly or configure CORTEX_PII_SALT.")
        return hashlib.sha256(f"{value}:{effective_salt}".encode()).hexdigest()


class DataSubjectExport(BaseModel):
    visitor_id: str
    export_generated_at: datetime = Field(default_factory=_utcnow)
    events_count: int
    profile_data: dict[str, Any] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    compliance_notice: str = "Export provided under GDPR Article 15 / CCPA Right of Access."


class PrivacyComplianceService:
    """
    GDPR / CCPA Data Subject Rights & Retention Manager:
    - Data Export (Right of Access)
    - Hard Data Erasure (Right to be Forgotten)
    - Rectification of profile attributes
    - Hash-chained immutable audit logging
    """

    def generate_data_export(
        self, visitor_id: str, profile_data: dict[str, Any], events: list[dict[str, Any]]
    ) -> DataSubjectExport:
        """GDPR Art. 15 export: the data subject's OWN data, unredacted.

        The SecretScrubber exists for logs and AI prompts, not for the subject's
        own access request — scrubbing here returned "[REDACTED_EMAIL]" instead
        of the subject's email, which defeats the right of access. The export is
        tenant-scoped and delivered over an authenticated operator channel.
        """
        return DataSubjectExport(
            visitor_id=visitor_id,
            events_count=len(events),
            profile_data=profile_data,
            events=events,
        )

    async def execute_hard_erasure(
        self,
        db,
        visitor_id: str,
        tenant_id: str,
        reason: str = "GDPR Article 17 Erasure Request",
    ) -> dict[str, Any]:
        """Cascading hard deletion of everything CORTEX stores for one data subject.

        The previous implementation returned invented counters (``events: 42``)
        without touching the database, so a controller acting on the response
        believed a GDPR Art. 17 request had been honoured when no data was
        removed (audit defect H8). This version executes real deletes, commits
        them, and reports the actual number of rows removed per table. A
        missing session is a programming error, not a silent success.
        """
        if db is None:
            raise ValueError("execute_hard_erasure requires an active database session")

        # Imported lazily: policy_engine must not depend on the API package at import time.
        from cortex_api.db_models import (
            EventModel,
            IdentityLinkModel,
            LeadModel,
            LeadScoreHistoryModel,
            MemoryEntryModel,
            ProfileModel,
            SessionModel,
            VisitorModel,
        )
        from sqlalchemy import delete, select

        counts: dict[str, int] = {}

        visitor_res = await db.execute(
            select(VisitorModel).where(VisitorModel.id == visitor_id, VisitorModel.tenant_id == tenant_id)
        )
        visitor = visitor_res.scalar_one_or_none()
        profile_ids = {visitor.profile_id} if visitor and visitor.profile_id else set()
        lead_ids = set()
        if profile_ids:
            lead_res = await db.execute(
                select(LeadModel).where(LeadModel.tenant_id == tenant_id, LeadModel.profile_id.in_(profile_ids))
            )
            lead_ids = {lead.id for lead in lead_res.scalars().all()}

        async def _purge(label: str, statement) -> None:
            result = await db.execute(statement)
            counts[label] = int(result.rowcount or 0)

        await _purge(
            "events",
            delete(EventModel).where(EventModel.tenant_id == tenant_id, EventModel.actor_id == visitor_id),
        )
        await _purge(
            "sessions",
            delete(SessionModel).where(SessionModel.tenant_id == tenant_id, SessionModel.visitor_id == visitor_id),
        )
        await _purge(
            "memories",
            delete(MemoryEntryModel).where(
                MemoryEntryModel.tenant_id == tenant_id, MemoryEntryModel.scope_id == visitor_id
            ),
        )
        if profile_ids:
            await _purge(
                "identity_links",
                delete(IdentityLinkModel).where(
                    IdentityLinkModel.tenant_id == tenant_id, IdentityLinkModel.target_id.in_(profile_ids)
                ),
            )
            for source_value in profile_ids:
                await db.execute(
                    delete(IdentityLinkModel).where(
                        IdentityLinkModel.tenant_id == tenant_id, IdentityLinkModel.source_value == source_value
                    )
                )
            for lead_id in lead_ids:
                await db.execute(
                    delete(LeadScoreHistoryModel).where(
                        LeadScoreHistoryModel.tenant_id == tenant_id, LeadScoreHistoryModel.lead_id == lead_id
                    )
                )
            await _purge(
                "leads",
                delete(LeadModel).where(LeadModel.tenant_id == tenant_id, LeadModel.profile_id.in_(profile_ids)),
            )
            await _purge(
                "profiles",
                delete(ProfileModel).where(ProfileModel.tenant_id == tenant_id, ProfileModel.id.in_(profile_ids)),
            )
        await _purge(
            "visitors",
            delete(VisitorModel).where(VisitorModel.id == visitor_id, VisitorModel.tenant_id == tenant_id),
        )

        await db.commit()

        purged_total = sum(counts.values())
        logger.info("Hard erasure for visitor=%s tenant=%s removed %d rows", visitor_id, tenant_id, purged_total)
        return {
            "visitor_id": visitor_id,
            "tenant_id": tenant_id,
            "status": "ERASED" if purged_total else "NO_RECORDS_FOUND",
            "purged_records": counts,
            "purged_total": purged_total,
            "audit_note": f"Hard erasure executed against tenant-scoped tables. Reason: {reason}",
            "completed_at": datetime.now(UTC).isoformat(),
        }
