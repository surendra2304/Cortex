import os
import sys

import pytest

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/agents/src",
    "packages/ai_universe_adapter/src",
    "packages/tool_runtime/src",
    "packages/integrations/src",
    "packages/policy_engine/src",
    "packages/workflow_engine/src",
    "packages/identity/src",
    "packages/analytics/src",
    "packages/intelligence/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from datetime import UTC

from cortex_policy_engine import PrivacyComplianceService, SecretScrubber


def test_pii_and_secret_scrubber():
    raw_text = "Contact me at user@enterprise.com, phone 555-123-4567, card 4111-2222-3333-4444, api key sk_live_abcdef1234567890abcdef."
    scrubbed = SecretScrubber.scrub_text(raw_text)

    assert "[REDACTED_CARD]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_API_KEY]" in scrubbed
    assert "4111-2222-3333-4444" not in scrubbed
    assert "sk_live_" not in scrubbed


def test_pii_payload_recursive_scrubber():
    payload = {"user_input": "My phone is (555) 019-2834", "nested": {"credit_card": "5500 0000 0000 0004"}}
    scrubbed = SecretScrubber.scrub_payload(payload)
    assert "[REDACTED_PHONE]" in scrubbed["user_input"]
    assert "[REDACTED_CARD]" in scrubbed["nested"]["credit_card"]


def test_privacy_service_export_redacts_identifiers():
    service = PrivacyComplianceService()

    profile = {"email": "ceo@corp.com", "phone": "555-000-1111"}
    events = [{"type": "page_view", "card": "4111-1111-1111-1111"}]
    export = service.generate_data_export("vis_privacy_1", profile, events)
    assert export.events_count == 1
    assert "[REDACTED_CARD]" in export.events[0]["card"]
    # Audit H8: emails are direct identifiers and must be scrubbed too.
    assert export.profile_data["email"] == "[REDACTED_EMAIL]"


def test_scrubber_redacts_email_addresses():
    """Audit H8: EMAIL_REGEX existed but was never applied."""
    scrubbed = SecretScrubber.scrub_text("Contact user@enterprise.com or call 555-123-4567")
    assert "user@enterprise.com" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed


def test_hash_pii_requires_an_explicit_salt(monkeypatch):
    """Audit H8: no hardcoded default salt — pseudonyms must be tenant-specific."""
    monkeypatch.delenv("CORTEX_PII_SALT", raising=False)
    with pytest.raises(ValueError):
        SecretScrubber.hash_pii("user@enterprise.com")

    monkeypatch.setenv("CORTEX_PII_SALT", "tenant-specific-salt")
    first = SecretScrubber.hash_pii("user@enterprise.com")
    assert first != SecretScrubber.hash_pii("user@enterprise.com", salt="another-salt")
    assert len(first) == 64


@pytest.mark.asyncio
async def test_hard_erasure_actually_deletes_and_reports_real_counts(session_factory, sqlite_engine):
    """Audit H8: erasure must touch the database and report actual row counts."""
    from datetime import datetime

    from cortex_api.db_models import EventModel, VisitorModel
    from sqlalchemy import func, select

    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(VisitorModel(id="vis_privacy_1", tenant_id="tenant_test", site_id="site_test", attributes={}))
        session.add(
            EventModel(
                id="evt_privacy_1",
                tenant_id="tenant_test",
                site_id="site_test",
                type="page_view",
                occurred_at=now,
                actor_type="visitor",
                actor_id="vis_privacy_1",
                source="web-sdk",
                data={},
                server_received_at=now,
            )
        )
        # A row belonging to somebody else must survive.
        session.add(
            EventModel(
                id="evt_other",
                tenant_id="tenant_test",
                site_id="site_test",
                type="page_view",
                occurred_at=now,
                actor_type="visitor",
                actor_id="vis_someone_else",
                source="web-sdk",
                data={},
                server_received_at=now,
            )
        )
        await session.commit()

    service = PrivacyComplianceService()
    async with session_factory() as session:
        erasure = await service.execute_hard_erasure(db=session, visitor_id="vis_privacy_1", tenant_id="tenant_test")

    assert erasure["status"] == "ERASED"
    assert erasure["purged_records"]["events"] == 1
    assert erasure["purged_records"]["visitors"] == 1
    assert erasure["purged_total"] == 2

    async with session_factory() as session:
        remaining = (await session.execute(select(func.count()).select_from(EventModel))).scalar_one()
    assert remaining == 1, "erasure must not touch other data subjects"


@pytest.mark.asyncio
async def test_hard_erasure_reports_no_records_found_instead_of_faking_success(session_factory):
    service = PrivacyComplianceService()
    async with session_factory() as session:
        erasure = await service.execute_hard_erasure(db=session, visitor_id="vis_absent", tenant_id="tenant_test")
    assert erasure["status"] == "NO_RECORDS_FOUND"
    assert erasure["purged_total"] == 0
