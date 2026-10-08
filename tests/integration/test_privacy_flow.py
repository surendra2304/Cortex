import os
import sys

import pytest

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/policy_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from datetime import UTC

from cortex_policy_engine import PrivacyComplianceService, SecretScrubber


@pytest.mark.asyncio
async def test_privacy_flow_consent_and_erasure_e2e(session_factory):
    """
    End-to-End Privacy Flow:
    PII detection & scrubbing -> GDPR Art. 15 Export -> GDPR Art. 17 Hard Erasure.
    """
    service = PrivacyComplianceService()

    # 1. PII detection and redaction
    raw_event = {
        "user_email": "privacy_user@domain.com",
        "card": "4111 2222 3333 4444",
        "notes": "Call me at 555-019-2834 with secret sk_live_999888777666555444",
    }
    scrubbed = SecretScrubber.scrub_payload(raw_event)
    assert "[REDACTED_CARD]" in scrubbed["card"]
    assert "[REDACTED_PHONE]" in scrubbed["notes"]
    assert "[REDACTED_API_KEY]" in scrubbed["notes"]
    assert "[REDACTED_EMAIL]" in scrubbed["user_email"]

    # 2. Data Subject Export (Art. 15) — the subject's OWN data, unredacted.
    #    The scrubber is for logs/AI prompts; scrubbing the export itself would
    #    defeat the right of access (upgrade 2026-10-07).
    export = service.generate_data_export(
        visitor_id="vis_e2e_privacy_01", profile_data={"email": "privacy_user@domain.com"}, events=[raw_event]
    )
    assert export.events_count == 1
    assert export.events[0]["card"] == "4111 2222 3333 4444"
    assert export.profile_data["email"] == "privacy_user@domain.com"

    # 3. Data Subject Hard Erasure (Art. 17) — executed against a real database.
    from datetime import datetime

    from cortex_api.db_models import EventModel, IdentityLinkModel, ProfileModel, VisitorModel
    from sqlalchemy import func, select

    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(
            ProfileModel(
                id="prof_priv_1",
                tenant_id="tenant_test",
                primary_email="privacy_user@domain.com",
                identities=[],
                traits={},
            )
        )
        session.add(
            VisitorModel(
                id="vis_e2e_privacy_01",
                tenant_id="tenant_test",
                site_id="site_test",
                profile_id="prof_priv_1",
                attributes={},
            )
        )
        session.add(
            IdentityLinkModel(
                id="link_priv_1",
                tenant_id="tenant_test",
                source_type="email",
                source_value="privacy_user@domain.com",
                target_type="profile_id",
                target_id="prof_priv_1",
                confidence=1.0,
            )
        )
        session.add(
            EventModel(
                id="evt_priv_1",
                tenant_id="tenant_test",
                site_id="site_test",
                type="page_view",
                occurred_at=now,
                actor_type="visitor",
                actor_id="vis_e2e_privacy_01",
                source="web-sdk",
                data={},
                server_received_at=now,
            )
        )
        await session.commit()

    async with session_factory() as session:
        erasure = await service.execute_hard_erasure(
            db=session, visitor_id="vis_e2e_privacy_01", tenant_id="tenant_test"
        )

    assert erasure["status"] == "ERASED"
    assert erasure["purged_records"]["events"] == 1
    assert erasure["purged_records"]["identity_links"] == 1
    assert erasure["purged_records"]["visitors"] == 1

    # Nothing may remain for the subject.
    async with session_factory() as session:
        remaining_events = (await session.execute(select(func.count()).select_from(EventModel))).scalar_one()
        remaining_visitors = (await session.execute(select(func.count()).select_from(VisitorModel))).scalar_one()
    assert remaining_events == 0
    assert remaining_visitors == 0
