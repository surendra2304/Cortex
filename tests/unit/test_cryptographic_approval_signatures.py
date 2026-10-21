"""Unit tests for closed-loop approval cryptographic signing (cortex_upgrade.approval)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from cortex_upgrade.approval import ApprovalQueue, ApprovalSigner
from cortex_upgrade.models import Approval, SideEffect, ToolCall


@pytest.fixture
def sample_approval():
    return Approval(
        approval_id=uuid4(),
        tenant_id="tenant_finance",
        principal_id="user_cfo",
        tool_name="payment_initiate",
        call_id=uuid4(),
        approved=True,
        decided_by="admin_cfo",
    )


def test_signature_generation_and_verification(sample_approval):
    secret = "test-secret-key-at-least-32-bytes-long!!"
    sig = ApprovalSigner.generate_signature(sample_approval, secret=secret)

    assert isinstance(sig, str)
    assert len(sig) == 64  # sha256 hex digest

    # Valid verification
    assert ApprovalSigner.verify_signature(sample_approval, signature=sig, secret=secret) is True


def test_signature_fails_on_tampered_payload(sample_approval):
    secret = "test-secret-key-at-least-32-bytes-long!!"
    sig = ApprovalSigner.generate_signature(sample_approval, secret=secret)

    # Tamper with tenant_id
    tampered_tenant = Approval(
        approval_id=sample_approval.approval_id,
        tenant_id="tenant_attacker",  # Changed!
        principal_id=sample_approval.principal_id,
        tool_name=sample_approval.tool_name,
        call_id=sample_approval.call_id,
        approved=sample_approval.approved,
        decided_by=sample_approval.decided_by,
    )
    assert ApprovalSigner.verify_signature(tampered_tenant, signature=sig, secret=secret) is False

    # Tamper with approved flag
    tampered_flag = Approval(
        approval_id=sample_approval.approval_id,
        tenant_id=sample_approval.tenant_id,
        principal_id=sample_approval.principal_id,
        tool_name=sample_approval.tool_name,
        call_id=sample_approval.call_id,
        approved=False,  # Changed!
        decided_by=sample_approval.decided_by,
    )
    assert ApprovalSigner.verify_signature(tampered_flag, signature=sig, secret=secret) is False


def test_signature_fails_on_wrong_secret(sample_approval):
    sig = ApprovalSigner.generate_signature(sample_approval, secret="secret-one-at-least-32-bytes-long!!")
    assert (
        ApprovalSigner.verify_signature(
            sample_approval, signature=sig, secret="secret-two-at-least-32-bytes-long!!"
        )
        is False
    )


@pytest.mark.asyncio
async def test_approval_queue_decide_signs_record_automatically():
    queue = ApprovalQueue()
    call = ToolCall(
        call_id=uuid4(),
        tool_name="stripe_charge",
        args={"amount": 5000},
        side_effect=SideEffect.HIGH_IMPACT,
    )
    req = await queue.request("tenant_acme", "user_pm", call)
    assert req.approved is False
    assert req.signature == ""

    decided = await queue.decide(req.approval_id, approver="operator_sarah", approved=True, reason="Valid invoice")
    assert decided.approved is True
    assert decided.decided_by == "operator_sarah"
    assert len(decided.signature) == 64

    # Verify signature passes
    assert ApprovalSigner.verify_signature(decided) is True
