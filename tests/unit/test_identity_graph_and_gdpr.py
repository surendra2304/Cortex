"""
Unit tests for Identity Graph Disjoint Set and Cascading GDPR Erasure.
"""

import pytest
from cortex_identity.graph_stitcher import (
    IdentityGraphStitcher,
    IdentityNode,
    IdentityCluster,
    GDPRCascadeErasureEngine,
    GDPRErasureReceipt,
)


def test_stitcher_single_node():
    stitcher = IdentityGraphStitcher(tenant_id="tenant_alpha")
    node = IdentityNode(id="vis_123", type="visitor_id", tenant_id="tenant_alpha")
    stitcher.register_node(node)

    cluster = stitcher.get_cluster("vis_123")
    assert isinstance(cluster, IdentityCluster)
    assert cluster.tenant_id == "tenant_alpha"
    assert cluster.total_nodes == 1
    assert cluster.nodes[0].id == "vis_123"


def test_stitcher_cross_tenant_rejection():
    stitcher = IdentityGraphStitcher(tenant_id="tenant_alpha")
    foreign_node = IdentityNode(id="vis_rogue", type="visitor_id", tenant_id="tenant_beta")

    with pytest.raises(PermissionError, match="Cross-tenant identity forbidden"):
        stitcher.register_node(foreign_node)


def test_stitcher_link_identities_transitive():
    stitcher = IdentityGraphStitcher(tenant_id="tenant_alpha")

    # Connect: vis_1 <-> email_1 <-> user_1
    node_vis = IdentityNode(id="vis_1", type="visitor_id", tenant_id="tenant_alpha")
    node_email = IdentityNode(id="alice@example.com", type="email", tenant_id="tenant_alpha")
    node_user = IdentityNode(id="usr_alice", type="user_id", tenant_id="tenant_alpha")
    node_prof = IdentityNode(id="prof_100", type="profile_id", tenant_id="tenant_alpha")

    stitcher.link_identities(node_vis, node_email, confidence=1.0)
    stitcher.link_identities(node_email, node_user, confidence=1.0)
    stitcher.link_identities(node_user, node_prof, confidence=1.0)

    # Any node in the cluster should resolve the complete set
    cluster_from_vis = stitcher.get_cluster("vis_1")
    assert cluster_from_vis.total_nodes == 4
    assert cluster_from_vis.primary_email == "alice@example.com"
    assert cluster_from_vis.canonical_profile_id == "prof_100"

    cluster_from_usr = stitcher.get_cluster("usr_alice")
    assert cluster_from_usr.total_nodes == 4


def test_stitcher_low_confidence_rejection():
    stitcher = IdentityGraphStitcher(tenant_id="tenant_alpha")
    node_a = IdentityNode(id="dev_1", type="device_fingerprint", tenant_id="tenant_alpha")
    node_b = IdentityNode(id="dev_2", type="device_fingerprint", tenant_id="tenant_alpha")

    with pytest.raises(ValueError, match="below minimum threshold"):
        stitcher.link_identities(node_a, node_b, confidence=0.40)


def test_gdpr_cascading_erasure():
    stitcher = IdentityGraphStitcher(tenant_id="tenant_alpha")
    gdpr = GDPRCascadeErasureEngine()

    node_vis = IdentityNode(id="vis_gdpr", type="visitor_id", tenant_id="tenant_alpha")
    node_email = IdentityNode(id="gdpr_user@test.org", type="email", tenant_id="tenant_alpha")
    node_dev = IdentityNode(id="fingerprint_x", type="device_fingerprint", tenant_id="tenant_alpha")

    stitcher.link_identities(node_vis, node_email)
    stitcher.link_identities(node_email, node_dev)

    # Trigger GDPR erasure on the email
    receipt = gdpr.cascade_erase(stitcher, target_identifier="gdpr_user@test.org", tenant_id="tenant_alpha")
    assert isinstance(receipt, GDPRErasureReceipt)
    assert receipt.tenant_id == "tenant_alpha"
    assert receipt.anonymized_node_count == 3
    assert "email" in receipt.anonymized_record_types
    assert "visitor_id" in receipt.anonymized_record_types
    assert len(receipt.compliance_hash) == 64

    # Verify nodes are anonymized
    for n in (node_vis, node_email, node_dev):
        assert n.metadata.get("anonymized") is True
        assert "compliance_hash" in n.metadata


def test_gdpr_tenant_mismatch():
    stitcher = IdentityGraphStitcher(tenant_id="tenant_alpha")
    gdpr = GDPRCascadeErasureEngine()

    with pytest.raises(PermissionError, match="Tenant mismatch"):
        gdpr.cascade_erase(stitcher, target_identifier="some_id", tenant_id="tenant_beta")
