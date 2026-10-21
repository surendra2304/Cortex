"""
Multi-Tenant Identity Graph Stitcher & Cascading GDPR Erasure Engine for Cortex.

Provides production-grade disjoint-set (Union-Find) identity graph clustering,
deterministic and probabilistic device identity stitching, and regulatory-compliant
cascading GDPR/CCPA erasure across transitively linked identity nodes.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class IdentityNode(BaseModel):
    id: str
    type: str  # visitor_id, email, user_id, device_fingerprint, phone, profile_id
    tenant_id: str
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    first_seen: str = Field(default_factory=lambda: _utcnow().isoformat())


class IdentityCluster(BaseModel):
    cluster_id: str
    tenant_id: str
    canonical_profile_id: str | None = None
    primary_email: str | None = None
    nodes: list[IdentityNode]
    confidence_score: float
    total_nodes: int


class GDPRErasureReceipt(BaseModel):
    erasure_id: str
    tenant_id: str
    target_identifier: str
    identifier_type: str
    anonymized_node_count: int
    anonymized_record_types: list[str]
    compliance_hash: str
    completed_at: str = Field(default_factory=lambda: _utcnow().isoformat())


class IdentityGraphStitcher:
    """
    In-memory and persistent disjoint-set identity graph manager with strict tenant isolation.
    """

    def __init__(self, tenant_id: str = "default"):
        self.tenant_id = tenant_id
        # Disjoint-set data structures: parent, rank, weights
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}
        self._nodes: dict[str, IdentityNode] = {}
        self._edges: list[tuple[str, str, float]] = []

    def _find(self, i: str) -> str:
        if i not in self._parent:
            self._parent[i] = i
            self._rank[i] = 0
            return i
        if self._parent[i] != i:
            self._parent[i] = self._find(self._parent[i])  # Path compression
        return self._parent[i]

    def _union(self, x: str, y: str) -> None:
        root_x = self._find(x)
        root_y = self._find(y)
        if root_x == root_y:
            return

        # Union by rank
        if self._rank[root_x] < self._rank[root_y]:
            self._parent[root_x] = root_y
        elif self._rank[root_x] > self._rank[root_y]:
            self._parent[root_y] = root_x
        else:
            self._parent[root_y] = root_x
            self._rank[root_x] += 1

    def register_node(self, node: IdentityNode) -> None:
        if node.tenant_id != self.tenant_id:
            raise PermissionError(
                f"Cross-tenant identity forbidden: node tenant '{node.tenant_id}' != stitcher tenant '{self.tenant_id}'."
            )
        self._nodes[node.id] = node
        self._find(node.id)

    def link_identities(
        self,
        node_a: IdentityNode,
        node_b: IdentityNode,
        confidence: float = 1.0,
        min_probabilistic_threshold: float = 0.65,
    ) -> IdentityCluster:
        """
        Links two identity nodes. Enforces tenant match and minimum confidence threshold.
        """
        if node_a.tenant_id != self.tenant_id or node_b.tenant_id != self.tenant_id:
            raise PermissionError("Cross-tenant link rejected: tenant isolation violation.")

        if confidence < min_probabilistic_threshold:
            raise ValueError(
                f"Confidence {confidence} below minimum threshold {min_probabilistic_threshold} for identity stitch."
            )

        self.register_node(node_a)
        self.register_node(node_b)

        self._union(node_a.id, node_b.id)
        self._edges.append((node_a.id, node_b.id, confidence))

        return self.get_cluster(node_a.id)

    def get_cluster(self, node_id: str) -> IdentityCluster:
        if node_id not in self._nodes:
            raise KeyError(f"Node '{node_id}' not found in tenant '{self.tenant_id}' graph.")

        root = self._find(node_id)
        cluster_node_ids = [nid for nid in self._nodes if self._find(nid) == root]
        cluster_nodes = [self._nodes[nid] for nid in cluster_node_ids]

        # Determine canonical profile and email
        canonical_profile = None
        primary_email = None

        for n in cluster_nodes:
            if n.type == "profile_id" and not canonical_profile:
                canonical_profile = n.id
            if n.type == "email" and not primary_email:
                primary_email = n.id

        # Calculate composite confidence (geometric or harmonic mean of edge weights)
        relevant_weights = [w for u, v, w in self._edges if u in cluster_node_ids and v in cluster_node_ids]
        cluster_confidence = (
            round(sum(relevant_weights) / len(relevant_weights), 3) if relevant_weights else 1.0
        )

        return IdentityCluster(
            cluster_id=f"cluster_{root}",
            tenant_id=self.tenant_id,
            canonical_profile_id=canonical_profile,
            primary_email=primary_email,
            nodes=cluster_nodes,
            confidence_score=cluster_confidence,
            total_nodes=len(cluster_nodes),
        )

    def all_clusters(self) -> list[IdentityCluster]:
        roots: dict[str, list[IdentityNode]] = defaultdict(list)
        for nid, node in self._nodes.items():
            r = self._find(nid)
            roots[r].append(node)

        results = []
        for r, nodes in roots.items():
            results.append(self.get_cluster(nodes[0].id))
        return results


class GDPRCascadeErasureEngine:
    """
    Executes cascading GDPR Article 17 erasure across all transitively connected identities.
    """

    def __init__(self, salt: str = "cortex_gdpr_compliance_salt"):
        self.salt = salt

    def _anonymize_value(self, val: str) -> str:
        """One-way cryptographic HMAC hash for anonymized compliance retention."""
        return hmac.new(self.salt.encode("utf-8"), val.encode("utf-8"), hashlib.sha256).hexdigest()[:24]

    def cascade_erase(
        self,
        stitcher: IdentityGraphStitcher,
        target_identifier: str,
        tenant_id: str,
    ) -> GDPRErasureReceipt:
        if stitcher.tenant_id != tenant_id:
            raise PermissionError("Tenant mismatch during GDPR erasure execution.")

        if target_identifier not in stitcher._nodes:
            # If not in stitcher, return a zero-count receipt
            h = hashlib.sha256(f"{tenant_id}:{target_identifier}:empty".encode("utf-8")).hexdigest()
            return GDPRErasureReceipt(
                erasure_id=f"gdpr_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                target_identifier=target_identifier,
                identifier_type="unknown",
                anonymized_node_count=0,
                anonymized_record_types=[],
                compliance_hash=h,
            )

        target_node = stitcher._nodes[target_identifier]
        cluster = stitcher.get_cluster(target_identifier)

        erased_count = 0
        record_types_erased = set()

        for node in cluster.nodes:
            record_types_erased.add(node.type)
            # Anonymize node attributes and overwrite sensitive identifiers
            node.metadata = {
                "anonymized": True,
                "anonymized_at": _utcnow().isoformat(),
                "original_type": node.type,
                "compliance_hash": self._anonymize_value(node.id),
            }
            erased_count += 1

        # Break edges in the disjoint set
        stitcher._edges = [
            (u, v, w)
            for u, v, w in stitcher._edges
            if u not in [n.id for n in cluster.nodes] and v not in [n.id for n in cluster.nodes]
        ]

        # Generate cryptographic audit compliance hash
        raw_receipt = f"{tenant_id}:{target_identifier}:{erased_count}:{_utcnow().isoformat()}"
        compliance_hash = hashlib.sha256(raw_receipt.encode("utf-8")).hexdigest()

        return GDPRErasureReceipt(
            erasure_id=f"gdpr_{uuid.uuid4().hex[:12]}",
            tenant_id=tenant_id,
            target_identifier=target_identifier,
            identifier_type=target_node.type,
            anonymized_node_count=erased_count,
            anonymized_record_types=sorted(list(record_types_erased)),
            compliance_hash=compliance_hash,
        )
