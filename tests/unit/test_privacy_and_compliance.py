import pytest
import os
import sys

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

from nexus_policy_engine import (
    SecretScrubber,
    PrivacyComplianceService
)


def test_pii_and_secret_scrubber():
    raw_text = "Contact me at user@enterprise.com, phone 555-123-4567, card 4111-2222-3333-4444, api key sk_live_abcdef1234567890abcdef."
    scrubbed = SecretScrubber.scrub_text(raw_text)

    assert "[REDACTED_CARD]" in scrubbed
    assert "[REDACTED_PHONE]" in scrubbed
    assert "[REDACTED_API_KEY]" in scrubbed
    assert "4111-2222-3333-4444" not in scrubbed
    assert "sk_live_" not in scrubbed


def test_pii_payload_recursive_scrubber():
    payload = {
        "user_input": "My phone is (555) 019-2834",
        "nested": {
            "credit_card": "5500 0000 0000 0004"
        }
    }
    scrubbed = SecretScrubber.scrub_payload(payload)
    assert "[REDACTED_PHONE]" in scrubbed["user_input"]
    assert "[REDACTED_CARD]" in scrubbed["nested"]["credit_card"]


def test_privacy_service_export_and_erasure():
    service = PrivacyComplianceService()

    # 1. Export
    profile = {"email": "ceo@corp.com", "phone": "555-000-1111"}
    events = [{"type": "page_view", "card": "4111-1111-1111-1111"}]
    export = service.generate_data_export("vis_privacy_1", profile, events)
    assert export.events_count == 1
    assert "[REDACTED_CARD]" in export.events[0]["card"]

    # 2. Erasure
    erasure = service.execute_hard_erasure("vis_privacy_1")
    assert erasure["status"] == "ERASED"
    assert erasure["purged_records"]["events"] > 0
