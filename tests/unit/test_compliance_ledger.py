"""
Unit tests for Cryptographic Tamper-Evident Compliance & Audit Ledger.
"""

import copy
import pytest
from cortex_core.compliance_ledger import (
    ChainVerificationResult,
    ComplianceBlock,
    ComplianceLedger,
    MerkleProof,
)


@pytest.fixture
def ledger() -> ComplianceLedger:
    return ComplianceLedger(master_salt="test-audit-salt-999")


def test_genesis_block_and_chaining(ledger: ComplianceLedger) -> None:
    block0 = ledger.record_action(
        tenant_id="tenant-sec",
        action_type="OPERATOR_APPROVAL_EXECUTION",
        actor_id="admin-01",
        payload={"action_id": "act-123", "target": "payment-gateway"},
    )

    assert block0.block_index == 0
    assert block0.prev_block_hash == ComplianceLedger.GENESIS_PREV_HASH
    assert len(block0.block_hash) == 64
    assert len(block0.signature) == 64

    block1 = ledger.record_action(
        tenant_id="tenant-sec",
        action_type="FEATURE_FLAG_MUTATION",
        actor_id="admin-02",
        payload={"flag": "checkout_v2", "enabled": True},
    )

    assert block1.block_index == 1
    assert block1.prev_block_hash == block0.block_hash
    assert block1.block_hash != block0.block_hash


def test_chain_verification_clean_success(ledger: ComplianceLedger) -> None:
    for i in range(5):
        ledger.record_action(
            tenant_id="tenant-audit",
            action_type="AUDIT_EVENT",
            actor_id=f"actor-{i}",
            payload={"step": i, "details": f"Execution step {i}"},
        )

    res = ledger.verify_chain("tenant-audit")
    assert isinstance(res, ChainVerificationResult)
    assert res.is_valid is True
    assert res.total_blocks == 5
    assert res.latest_block_hash is not None
    assert res.merkle_root is not None
    assert res.tampered_block_index is None


def test_detect_payload_tampering(ledger: ComplianceLedger) -> None:
    for i in range(3):
        ledger.record_action(
            tenant_id="tenant-tamper",
            action_type="AUDIT_EVENT",
            actor_id="admin",
            payload={"value": i},
        )

    # Maliciously mutate block 1's payload without recalculating hashes
    ledger._chains["tenant-tamper"][1].payload["value"] = 9999

    res = ledger.verify_chain("tenant-tamper")
    assert res.is_valid is False
    assert res.tampered_block_index == 1
    assert "Payload tampering detected" in str(res.error_detail)


def test_detect_broken_hash_link(ledger: ComplianceLedger) -> None:
    for i in range(4):
        ledger.record_action(
            tenant_id="tenant-tamper2",
            action_type="AUDIT_EVENT",
            actor_id="admin",
            payload={"step": i},
        )

    # Maliciously alter prev_block_hash of block 2
    ledger._chains["tenant-tamper2"][2].prev_block_hash = "deadbeef" * 8

    res = ledger.verify_chain("tenant-tamper2")
    assert res.is_valid is False
    assert res.tampered_block_index == 2
    assert "Broken hash chain" in str(res.error_detail)


def test_merkle_root_and_inclusion_proof(ledger: ComplianceLedger) -> None:
    for i in range(4):
        ledger.record_action(
            tenant_id="tenant-merkle",
            action_type="GDPR_ARTICLE_17_ERASURE",
            actor_id="compliance-officer",
            payload={"erasure_receipt_id": f"receipt-{i}"},
        )

    root = ledger.compute_merkle_root("tenant-merkle")
    assert root is not None
    assert len(root) == 64

    # Generate inclusion proof for block index 2
    proof = ledger.generate_merkle_proof("tenant-merkle", 2)
    assert proof is not None
    assert isinstance(proof, MerkleProof)
    assert proof.block_index == 2
    assert proof.merkle_root == root
    assert len(proof.proof_path) > 0


def test_tenant_isolation_ledger(ledger: ComplianceLedger) -> None:
    ledger.record_action("tenant-A", "ACT_A", "user-A", {"secret": 123})

    blocks_a = ledger.get_blocks("tenant-A")
    blocks_b = ledger.get_blocks("tenant-B")

    assert len(blocks_a) == 1
    assert len(blocks_b) == 0

    res_b = ledger.verify_chain("tenant-B")
    assert res_b.is_valid is True
    assert res_b.total_blocks == 0
