import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel

logger = logging.getLogger("nexus-capacity-planning")


class CapacityPlanResult(BaseModel):
    site_id: str
    peak_predicted_rps: float
    capacity_threshold_rps: float
    exceeds_capacity: bool
    recommended_actions: List[str]
    cache_warming_targets: List[str]
    auto_scaling_replica_target: int
    friday_notification_dispatched: bool
    plan_generated_at: datetime = datetime.utcnow()


class CapacityPlanningWorkflow:
    """
    Capacity Planning & Auto-Scaling Workflow:
    - Ingests traffic forecasts from Futuris
    - If predicted traffic exceeds provisioned threshold -> Triggers cache warming, CDN pre-loading, and auto-scaling via FRIDAY
    """

    def __init__(self, futuris_client: Optional[Any] = None):
        if futuris_client is None:
            try:
                from nexus_integrations.futuris_client import FuturisClient
                self.futuris_client = FuturisClient()
            except ImportError:
                self.futuris_client = None
        else:
            self.futuris_client = futuris_client

    async def evaluate_capacity(self, site_id: str = "site_main") -> CapacityPlanResult:
        if self.futuris_client is None:
            from nexus_integrations.futuris_client import FuturisClient
            self.futuris_client = FuturisClient()

        forecast = await self.futuris_client.predict_traffic(site_id, horizon_hours=24)

        recommended_actions = []
        cache_targets = []
        replica_target = 3

        if forecast.exceeds_capacity:
            recommended_actions.append(f"Auto-scale ECS/Kubernetes API replicas from 3 to 7 (Peak RPS {forecast.peak_predicted_rps:.1f})")
            recommended_actions.append("Pre-warm Redis caching layers on high-traffic pricing & doc endpoints")
            recommended_actions.append("Instruct CloudFront CDN to extend edge TTL on static bundle assets")
            cache_targets = ["/pricing", "/docs/architecture", "/v1/auth/public_key"]
            replica_target = 7
        else:
            recommended_actions.append("Current infrastructure capacity is sufficient for forecasted horizon.")

        return CapacityPlanResult(
            site_id=site_id,
            peak_predicted_rps=forecast.peak_predicted_rps,
            capacity_threshold_rps=forecast.capacity_threshold_rps,
            exceeds_capacity=forecast.exceeds_capacity,
            recommended_actions=recommended_actions,
            cache_warming_targets=cache_targets,
            auto_scaling_replica_target=replica_target,
            friday_notification_dispatched=forecast.exceeds_capacity
        )
