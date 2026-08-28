import pytest
import os
import sys

for p in [
    "packages/core/src",
    "packages/intelligence/src",
    "packages/integrations/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_intelligence import AssetExposureMonitor


def test_exposure_correlation_e2e():
    """
    End-to-End Exposure Correlation Test:
    Vulnerability finding + Public endpoint + Sensitive data -> Critical exposure determination.
    """
    monitor = AssetExposureMonitor()

    # 1. Unauthenticated public endpoint handling sensitive checkout data
    checkout_exp = monitor.evaluate_exposure("site_main", "/checkout")
    assert checkout_exp["is_public"] is True
    assert checkout_exp["requires_auth"] is False
    assert checkout_exp["data_sensitivity"] == "high"
    assert checkout_exp["exposure_level"] == "critical"

    # 2. Authenticated telemetry endpoint
    events_exp = monitor.evaluate_exposure("site_main", "/v1/events")
    assert events_exp["is_public"] is True
    assert events_exp["requires_auth"] is True
    assert events_exp["exposure_level"] == "high"

    # 3. Public static pricing page
    pricing_exp = monitor.evaluate_exposure("site_main", "/pricing")
    assert pricing_exp["data_sensitivity"] == "public"
    assert pricing_exp["exposure_level"] == "standard"
