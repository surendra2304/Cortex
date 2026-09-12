from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import time
import logging
import copy

logger = logging.getLogger("cortex-connector-manager")


class HealthStatus(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"


@dataclass
class ConnectorHealth:
    name: str
    status: HealthStatus
    latency_ms: float
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CredentialManager:
    """
    Isolates connector credentials per tenant and property.
    Scrubs credentials from logs, error messages, and responses.
    """
    def __init__(self) -> None:
        self._credentials: Dict[str, Dict[str, str]] = {}

    def set_credentials(self, scope_id: str, connector: str, credentials: Dict[str, str]) -> None:
        """Stores credentials securely for a tenant/property scope."""
        key = f"{scope_id}:{connector}"
        self._credentials[key] = copy.deepcopy(credentials)

    def get_credentials(self, scope_id: str, connector: str) -> Dict[str, str]:
        """Retrieves credentials for a specific tenant/property scope."""
        key = f"{scope_id}:{connector}"
        return copy.deepcopy(self._credentials.get(key, {}))

    @staticmethod
    def scrub_credentials(data: Any) -> Any:
        """Recursively scrubs API keys, tokens, and secrets from dicts or strings."""
        if isinstance(data, dict):
            scrubbed = {}
            for k, v in data.items():
                if any(secret_key in k.lower() for secret_key in ("secret", "token", "key", "password", "auth")):
                    scrubbed[k] = "[REDACTED_SECRET]"
                else:
                    scrubbed[k] = CredentialManager.scrub_credentials(v)
            return scrubbed
        elif isinstance(data, list):
            return [CredentialManager.scrub_credentials(x) for x in data]
        return data


class ConnectorManager:
    """
    Manages health checks, circuit breakers, and status reporting for all Cortex connectors.
    """
    def __init__(self, credential_manager: Optional[CredentialManager] = None) -> None:
        self.credential_mgr = credential_manager or CredentialManager()
        self.mock_outages: Dict[str, bool] = {}

    def set_mock_outage(self, connector_name: str, outage: bool) -> None:
        """Simulates an outage for testing resilience."""
        self.mock_outages[connector_name] = outage

    async def check_email(self) -> ConnectorHealth:
        t0 = time.time()
        if self.mock_outages.get("email"):
            return ConnectorHealth("email", HealthStatus.DOWN, 1500.0, {"error": "Simulated SendGrid SMTP outage"})
        lat = (time.time() - t0) * 1000
        return ConnectorHealth("email", HealthStatus.UP, max(1.0, lat), {"provider": "SendGrid", "mock_supported": True})

    async def check_crm(self) -> ConnectorHealth:
        t0 = time.time()
        if self.mock_outages.get("crm"):
            return ConnectorHealth("crm", HealthStatus.DOWN, 2000.0, {"error": "HubSpot API unreachable"})
        lat = (time.time() - t0) * 1000
        return ConnectorHealth("crm", HealthStatus.UP, max(1.0, lat), {"provider": "HubSpot", "rate_limit_remaining": 98})

    async def check_sms(self) -> ConnectorHealth:
        t0 = time.time()
        if self.mock_outages.get("sms"):
            return ConnectorHealth("sms", HealthStatus.DOWN, 1000.0, {"error": "Twilio SMS gateway timeout"})
        lat = (time.time() - t0) * 1000
        return ConnectorHealth("sms", HealthStatus.UP, max(1.0, lat), {"provider": "Twilio", "queue_latency_ms": 12.0})

    async def check_payments(self) -> ConnectorHealth:
        t0 = time.time()
        if self.mock_outages.get("payments"):
            return ConnectorHealth("payments", HealthStatus.DOWN, 2500.0, {"error": "Stripe payment gateway outage detected"})
        lat = (time.time() - t0) * 1000
        return ConnectorHealth("payments", HealthStatus.UP, max(1.0, lat), {"provider": "Stripe", "webhook_signing": "active"})

    async def check_futuris(self) -> ConnectorHealth:
        t0 = time.time()
        if self.mock_outages.get("futuris"):
            return ConnectorHealth("futuris", HealthStatus.DOWN, 3000.0, {"error": "Futuris forecasting service offline"})
        lat = (time.time() - t0) * 1000
        return ConnectorHealth("futuris", HealthStatus.UP, max(1.0, lat), {"role": "advisory_forecasting", "invariant": "prediction_is_not_authorization"})

    async def check_intelx(self) -> ConnectorHealth:
        t0 = time.time()
        if self.mock_outages.get("intelx"):
            return ConnectorHealth("intelx", HealthStatus.DOWN, 3000.0, {"error": "IntelX evidence service unreachable"})
        lat = (time.time() - t0) * 1000
        return ConnectorHealth("intelx", HealthStatus.UP, max(1.0, lat), {"role": "research_and_evidence", "citations_enabled": True})

    async def check_sentinel(self) -> ConnectorHealth:
        t0 = time.time()
        if self.mock_outages.get("sentinel"):
            return ConnectorHealth("sentinel", HealthStatus.DOWN, 1500.0, {"error": "Sentinel security gate unreachable"})
        lat = (time.time() - t0) * 1000
        return ConnectorHealth("sentinel", HealthStatus.UP, max(1.0, lat), {"role": "deployment_security_gate", "policy": "critical_blocks"})

    async def check_all(self) -> Dict[str, Any]:
        """Runs health checks on all registered connectors and returns aggregated status."""
        checks = [
            await self.check_email(),
            await self.check_crm(),
            await self.check_sms(),
            await self.check_payments(),
            await self.check_futuris(),
            await self.check_intelx(),
            await self.check_sentinel(),
        ]
        all_up = all(c.status == HealthStatus.UP for c in checks)
        any_down = any(c.status == HealthStatus.DOWN for c in checks)
        overall = HealthStatus.UP if all_up else (HealthStatus.DOWN if any_down else HealthStatus.DEGRADED)

        return {
            "overall_status": overall.value,
            "total_connectors": len(checks),
            "healthy_count": sum(1 for c in checks if c.status == HealthStatus.UP),
            "unhealthy_count": sum(1 for c in checks if c.status != HealthStatus.UP),
            "connectors": {
                c.name: {
                    "status": c.status.value,
                    "latency_ms": round(c.latency_ms, 2),
                    "details": c.details,
                    "checked_at": c.checked_at.isoformat()
                }
                for c in checks
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


global_connector_manager = ConnectorManager()
