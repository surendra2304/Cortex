"""
Unit tests for Audience Segments Engine and Downstream Schema Transformations.
"""

import pytest
from cortex_intelligence.audience_segments import (
    AudienceSegment,
    AudienceSegmentEngine,
    SegmentRule,
)


def test_segment_crud():
    engine = AudienceSegmentEngine()
    seg = AudienceSegment(
        name="High Value Active",
        tenant_id="tenant_acme",
        rules=[
            SegmentRule(field="lead_score", operator="gte", value=0.8),
            SegmentRule(field="lifecycle_stage", operator="eq", value="lead"),
        ],
        match_policy="ALL",
    )
    saved = engine.save_segment(seg)
    assert saved.id.startswith("seg_")

    fetched = engine.get_segment(saved.id, tenant_id="tenant_acme")
    assert fetched is not None
    assert fetched.name == "High Value Active"

    # List
    all_segs = engine.list_segments(tenant_id="tenant_acme")
    assert len(all_segs) == 1

    # Delete
    deleted = engine.delete_segment(saved.id, tenant_id="tenant_acme")
    assert deleted is True
    assert engine.get_segment(saved.id, tenant_id="tenant_acme") is None


def test_segment_evaluation_all_and_any():
    engine = AudienceSegmentEngine()
    # Segment requiring ALL: score >= 0.70 AND tier == "CHAMPION"
    seg_all = AudienceSegment(
        name="Champions Only",
        tenant_id="tenant_acme",
        rules=[
            SegmentRule(field="score", operator="gte", value=0.70),
            SegmentRule(field="tier", operator="eq", value="CHAMPION"),
        ],
        match_policy="ALL",
    )
    engine.save_segment(seg_all)

    # Segment requiring ANY: country in ["US", "CA"] OR tier == "CHAMPION"
    seg_any = AudienceSegment(
        name="North America or Champion",
        tenant_id="tenant_acme",
        rules=[
            SegmentRule(field="country", operator="in", value=["US", "CA"]),
            SegmentRule(field="tier", operator="eq", value="CHAMPION"),
        ],
        match_policy="ANY",
    )
    engine.save_segment(seg_any)

    profiles = [
        # Profile 1: Champion in UK, score 0.85
        {
            "id": "p1",
            "score": 0.85,
            "traits": {"tier": "CHAMPION", "country": "UK"},
            "tenant_id": "tenant_acme",
        },
        # Profile 2: Lost user in US, score 0.30
        {
            "id": "p2",
            "score": 0.30,
            "traits": {"tier": "LOST", "country": "US"},
            "tenant_id": "tenant_acme",
        },
        # Profile 3: Lost user in France, score 0.10
        {
            "id": "p3",
            "score": 0.10,
            "traits": {"tier": "LOST", "country": "FR"},
            "tenant_id": "tenant_acme",
        },
    ]

    # Evaluate ALL
    res_all = engine.evaluate_segment(seg_all.id, profiles, tenant_id="tenant_acme")
    assert res_all.matching_profiles_count == 1
    assert res_all.matching_profile_ids == ["p1"]
    assert res_all.match_percentage == 33.33

    # Evaluate ANY
    res_any = engine.evaluate_segment(seg_any.id, profiles, tenant_id="tenant_acme")
    # p1 matches tier, p2 matches country
    assert res_any.matching_profiles_count == 2
    assert "p1" in res_any.matching_profile_ids
    assert "p2" in res_any.matching_profile_ids


def test_segment_cross_tenant_rejection():
    engine = AudienceSegmentEngine()
    seg = AudienceSegment(
        name="Test Seg",
        tenant_id="tenant_alpha",
    )
    engine.save_segment(seg)

    foreign_profiles = [{"id": "p_rogue", "tenant_id": "tenant_beta"}]
    with pytest.raises(PermissionError, match="Cross-tenant evaluation blocked"):
        engine.evaluate_segment(seg.id, foreign_profiles, tenant_id="tenant_alpha")


def test_export_for_destinations():
    engine = AudienceSegmentEngine()
    profiles = [
        {
            "id": "p1",
            "primary_email": "alice@company.com",
            "score": 0.95,
            "lifecycle_stage": "customer",
            "traits": {"tier": "CHAMPION"},
        }
    ]

    # HubSpot
    hs = engine.export_for_destination(profiles, destination="hubspot")
    assert len(hs) == 1
    assert hs[0]["email"] == "alice@company.com"
    assert hs[0]["properties"]["cortex_lead_score"] == 0.95

    # Meta CAPI (SHA-256 hashed)
    meta = engine.export_for_destination(profiles, destination="meta_capi")
    assert len(meta) == 1
    import hashlib
    expected_hash = hashlib.sha256(b"alice@company.com").hexdigest()
    assert meta[0]["em"] == expected_hash
