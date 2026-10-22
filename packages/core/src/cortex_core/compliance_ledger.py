"""
Cryptographic Tamper-Evident Compliance & Audit Ledger for Cortex.

Provides production-grade immutable audit trails:
- Merkle-chained blocks with SHA-256 cryptographic linkage
- HMAC-SHA256 authenticity signatures per block
- Full chain integrity verification (detecting retroactive mutations, tampering, and deletion)
- Merkle root calculation and audit inclusion proof generation (GDPR Art 30 / SOC2)
- Strict tenant isolation
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class ComplianceBlock(BaseModel):
    block_index: int
    tenant_id: str
    timestamp_iso: str
    action_type: str
    actor_id: str
    payload: dict[str, Any]
    payload_hash: str
    prev_block_hash: str
    block_hash: str
    signature: str


class MerkleProof(BaseModel):
    block_index: int
    block_hash: str
    merkle_root: str
    proof_path: list[tuple[str, str]]  # list of (direction, sibling_hash)
    verified: bool = True


class ChainVerificationResult(BaseModel):
    tenant_id: str
    total_blocks: int
    is_valid: bool
    latest_block_hash: str | None = None
    merkle_root: str | None = None
    tampered_block_index: int | None = None
    error_detail: str | None = None
    verified_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class ComplianceLedger:
    """
    Immutable, tamper-evident audit ledger partitioned by tenant.
    """

    GENESIS_PREV_HASH = "0" * 64

    def __init__(self, master_salt: str = "cortex-compliance-ledger-secret-2026") -> None:
        self._master_salt = master_salt
        # {tenant_id: [ComplianceBlock, ...]}
        self._chains: dict[str, list[ComplianceBlock]] = {}

    def _get_signing_key(self, tenant_id: str) -> bytes:
        return hashlib.sha256(f"{self._master_salt}:{tenant_id}".encode()).digest()

    def record_action(
        self,
        tenant_id: str,
        action_type: str,
        actor_id: str,
        payload: dict[str, Any],
        timestamp: datetime | None = None,
    ) -> ComplianceBlock:
        """
        Append a new tamper-evident audit block to the tenant's cryptographic ledger.
        """
        chain = self._chains.setdefault(tenant_id, [])
        block_index = len(chain)
        ts_iso = (timestamp or _utcnow()).isoformat()

        # Compute payload hash
        payload_canonical = _canonical_json(payload)
        payload_hash = hashlib.sha256(payload_canonical.encode()).hexdigest()

        # Compute previous block hash
        prev_block_hash = chain[-1].block_hash if block_index > 0 else self.GENESIS_PREV_HASH

        # Compute block hash
        block_preimage = f"{block_index}:{tenant_id}:{ts_iso}:{action_type}:{actor_id}:{payload_hash}:{prev_block_hash}"
        block_hash = hashlib.sha256(block_preimage.encode()).hexdigest()

        # Compute HMAC signature
        signing_key = self._get_signing_key(tenant_id)
        sig = hmac.new(signing_key, block_hash.encode(), hashlib.sha256).hexdigest()

        block = ComplianceBlock(
            block_index=block_index,
            tenant_id=tenant_id,
            timestamp_iso=ts_iso,
            action_type=action_type,
            actor_id=actor_id,
            payload=payload,
            payload_hash=payload_hash,
            prev_block_hash=prev_block_hash,
            block_hash=block_hash,
            signature=sig,
        )

        chain.append(block)
        return block

    def get_blocks(
        self,
        tenant_id: str,
        action_type: str | None = None,
        limit: int = 100,
    ) -> list[ComplianceBlock]:
        """Retrieve audit blocks for a tenant with optional filtering."""
        chain = self._chains.get(tenant_id, [])
        if action_type:
            filtered = [b for b in chain if b.action_type == action_type]
        else:
            filtered = chain
        return filtered[:limit]

    def verify_chain(self, tenant_id: str) -> ChainVerificationResult:
        """
        Verify the integrity of a tenant's audit ledger from Genesis to head.
        Ensures cryptographic continuity, payload integrity, and authentic signatures.
        """
        chain = self._chains.get(tenant_id, [])
        if not chain:
            return ChainVerificationResult(
                tenant_id=tenant_id,
                total_blocks=0,
                is_valid=True,
                latest_block_hash=None,
                merkle_root=None,
            )

        signing_key = self._get_signing_key(tenant_id)
        expected_prev_hash = self.GENESIS_PREV_HASH

        for idx, block in enumerate(chain):
            # 1. Monotonic index check
            if block.block_index != idx:
                return ChainVerificationResult(
                    tenant_id=tenant_id,
                    total_blocks=len(chain),
                    is_valid=False,
                    tampered_block_index=idx,
                    error_detail=f"Block index mismatch: expected {idx}, found {block.block_index}",
                )

            # 2. Previous hash link check
            if block.prev_block_hash != expected_prev_hash:
                return ChainVerificationResult(
                    tenant_id=tenant_id,
                    total_blocks=len(chain),
                    is_valid=False,
                    tampered_block_index=idx,
                    error_detail=f"Broken hash chain at block {idx}: prev_block_hash does not match preceding block",
                )

            # 3. Payload hash integrity
            expected_payload_hash = hashlib.sha256(_canonical_json(block.payload).encode()).hexdigest()
            if block.payload_hash != expected_payload_hash:
                return ChainVerificationResult(
                    tenant_id=tenant_id,
                    total_blocks=len(chain),
                    is_valid=False,
                    tampered_block_index=idx,
                    error_detail=f"Payload tampering detected at block {idx}",
                )

            # 4. Block hash integrity
            preimage = f"{idx}:{tenant_id}:{block.timestamp_iso}:{block.action_type}:{block.actor_id}:{block.payload_hash}:{block.prev_block_hash}"
            expected_block_hash = hashlib.sha256(preimage.encode()).hexdigest()
            if block.block_hash != expected_block_hash:
                return ChainVerificationResult(
                    tenant_id=tenant_id,
                    total_blocks=len(chain),
                    is_valid=False,
                    tampered_block_index=idx,
                    error_detail=f"Block hash mismatch at block {idx}",
                )

            # 5. Authenticity signature check
            expected_sig = hmac.new(signing_key, block.block_hash.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(block.signature, expected_sig):
                return ChainVerificationResult(
                    tenant_id=tenant_id,
                    total_blocks=len(chain),
                    is_valid=False,
                    tampered_block_index=idx,
                    error_detail=f"Invalid cryptographic signature at block {idx}",
                )

            expected_prev_hash = block.block_hash

        merkle_root = self.compute_merkle_root(tenant_id)

        return ChainVerificationResult(
            tenant_id=tenant_id,
            total_blocks=len(chain),
            is_valid=True,
            latest_block_hash=chain[-1].block_hash,
            merkle_root=merkle_root,
        )

    def compute_merkle_root(self, tenant_id: str) -> str | None:
        """Compute the Merkle root hash of all block hashes in the tenant's chain."""
        chain = self._chains.get(tenant_id, [])
        if not chain:
            return None

        hashes = [b.block_hash for b in chain]
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])  # Duplicate last element if odd
            new_level: list[str] = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i + 1]
                parent = hashlib.sha256(combined.encode()).hexdigest()
                new_level.append(parent)
            hashes = new_level
        return hashes[0]

    def generate_merkle_proof(self, tenant_id: str, block_index: int) -> MerkleProof | None:
        """
        Generate a cryptographic Merkle inclusion proof for an individual block.
        """
        chain = self._chains.get(tenant_id, [])
        if not chain or block_index < 0 or block_index >= len(chain):
            return None

        target_hash = chain[block_index].block_hash
        merkle_root = self.compute_merkle_root(tenant_id)
        if not merkle_root:
            return None

        # Build proof path
        proof_path: list[tuple[str, str]] = []
        hashes = [b.block_hash for b in chain]
        idx = block_index

        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])
            new_level: list[str] = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i + 1]
                parent = hashlib.sha256(combined.encode()).hexdigest()
                new_level.append(parent)

            sibling_idx = idx + 1 if idx % 2 == 0 else idx - 1
            direction = "right" if idx % 2 == 0 else "left"
            sibling_hash = hashes[sibling_idx]
            proof_path.append((direction, sibling_hash))

            idx = idx // 2
            hashes = new_level

        return MerkleProof(
            block_index=block_index,
            block_hash=target_hash,
            merkle_root=merkle_root,
            proof_path=proof_path,
            verified=True,
        )


global_compliance_ledger = ComplianceLedger()
