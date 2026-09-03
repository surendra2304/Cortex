import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("cortex-exposure-monitor")


class AssetExposure(BaseModel):
    asset_id: str
    endpoint: str
    is_public: bool = True
    requires_auth: bool = False
    data_sensitivity: str = "high"  # public, internal, sensitive, high
    traffic_volume_rpm: int = 150
    exposure_level: str = "standard"  # low, standard, high, critical


class AssetExposureMonitor:
    """
    Asset Exposure & Attack Surface Monitor:
    - Maintains live registry of deployed web assets & API routes
    - Assesses actual real-world risk based on accessibility, auth requirements, and data sensitivity
    - Example: An unauthenticated public route handling sensitive telemetry has 'critical' exposure
    """

    def __init__(self):
        self.asset_registry: Dict[str, AssetExposure] = {
            "site_main:/checkout": AssetExposure(
                asset_id="site_main",
                endpoint="/checkout",
                is_public=True,
                requires_auth=False,
                data_sensitivity="high",
                traffic_volume_rpm=450,
                exposure_level="critical"
            ),
            "site_main:/v1/events": AssetExposure(
                asset_id="site_main",
                endpoint="/v1/events",
                is_public=True,
                requires_auth=True,
                data_sensitivity="sensitive",
                traffic_volume_rpm=1200,
                exposure_level="high"
            ),
            "site_main:/pricing": AssetExposure(
                asset_id="site_main",
                endpoint="/pricing",
                is_public=True,
                requires_auth=False,
                data_sensitivity="public",
                traffic_volume_rpm=800,
                exposure_level="standard"
            )
        }

    def register_asset(self, asset: AssetExposure) -> None:
        key = f"{asset.asset_id}:{asset.endpoint}"
        self.asset_registry[key] = asset

    def evaluate_exposure(self, asset_id: str, endpoint: str) -> Dict[str, Any]:
        key = f"{asset_id}:{endpoint}"
        asset = self.asset_registry.get(key)

        if not asset:
            # Dynamically infer exposure
            is_sensitive = any(k in endpoint.lower() for k in ["auth", "login", "checkout", "payment", "user", "billing"])
            exposure_level = "critical" if is_sensitive else "standard"
            return {
                "asset_id": asset_id,
                "endpoint": endpoint,
                "exposure_level": exposure_level,
                "inferred": True
            }

        return {
            "asset_id": asset.asset_id,
            "endpoint": asset.endpoint,
            "is_public": asset.is_public,
            "requires_auth": asset.requires_auth,
            "data_sensitivity": asset.data_sensitivity,
            "traffic_volume_rpm": asset.traffic_volume_rpm,
            "exposure_level": asset.exposure_level
        }

    def list_monitored_assets(self) -> List[Dict[str, Any]]:
        return [a.model_dump() for a in self.asset_registry.values()]
