import pytest
import os
import sys

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/policy_engine/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_policy_engine import SecretScrubber, PrivacyComplianceService


def test_privacy_flow_consent_and_erasure_e2e():
    """
    End-to-End Privacy Flow:
    PII detection & scrubbing -> GDPR Art. 15 Export -> GDPR Art. 17 Hard Erasure.
    """
    service = PrivacyComplianceService()

    # 1. PII detection and redaction
    raw_event = {
        "user_email": "privacy_user@domain.com",
        "card": "4111 2222 3333 4444",
        "notes": "Call me at 555-019-2834 with secret sk_live_999888777666555444"
    }
    scrubbed = SecretScrubber.scrub_payload(raw_event)
    assert "[REDACTED_CARD]" in scrubbed["card"]
    assert "[REDACTED_PHONE]" in scrubbed["notes"]
    assert "[REDACTED_API_KEY]" in scrubbed["notes"]

    # 2. Data Subject Export (Art. 15)
    export = service.generate_data_export(
        visitor_id="vis_e2e_privacy_01",
        profile_data={"email": "privacy_user@domain.com"},
        events=[raw_event]
    )
    assert export.events_count == 1
    assert "[REDACTED_CARD]" in export.events[0]["card"]

    # 3. Data Subject Hard Erasure (Art. 17)
    erasure = service.execute_hard_erasure("vis_e2e_privacy_01")
    assert erasure["status"] == "ERASED"
    assert erasure["purged_records"]["events"] > 0
    assert erasure["purged_records"]["identity_links"] > 0
