import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/identity/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from cortex_identity import IdentityResolver


@pytest.mark.asyncio
async def test_identity_chain_and_lifecycle_promotion_e2e():
    """
    End-to-End Identity Chain:
    Anonymous Visitor -> identify() with Consent -> Lead Promotion -> Customer Conversion.
    """
    resolver = IdentityResolver()
    mock_db = AsyncMock()

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_res
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    # Step 1: Anonymous browsing (no email)
    anon_res = await resolver.resolve_identity(
        db=mock_db,
        visitor_id="vis_e2e_anon_01",
        email=None,
        consent_granted=True
    )
    assert anon_res["lifecycle_stage"] == "anonymous"
    assert anon_res["is_identified"] is False

    # Step 2: Form submission / identify() -> Promoted to Lead
    lead_res = await resolver.resolve_identity(
        db=mock_db,
        visitor_id="vis_e2e_anon_01",
        email="buyer@enterprise-corp.com",
        consent_granted=True,
        traits={"company": "Enterprise Corp", "role": "Head of Growth"}
    )
    assert lead_res["lifecycle_stage"] == "lead"
    assert lead_res["is_identified"] is True
    assert lead_res["primary_email"] == "buyer@enterprise-corp.com"
