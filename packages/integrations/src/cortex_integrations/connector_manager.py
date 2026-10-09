from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger("cortex-connector-manager")


class HealthStatus(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


@dataclass
class ConnectorHealth:
    name: str
    status: HealthStatus
    latency_ms: float | None
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class CredentialManager:
    """
    Isolates connector credentials per tenant and property.
    Scrubs credentials from logs, error messages, and responses.
    """

    def __init__(self) -> None:
        self._credentials: dict[str, dict[str, str]] = {}

    def set_credentials(self, scope_id: str, connector: str, credentials: dict[str, str]) -> None:
        """Stores credentials securely for a tenant/property scope."""
        key = f"{scope_id}:{connector}"
        self._credentials[key] = copy.deepcopy(credentials)

    def get_credentials(self, scope_id: str, connector: str) -> dict[str, str]:
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

    def __init__(self, credential_manager: CredentialManager | None = None) -> None:
        self.credential_mgr = credential_manager or CredentialManager()
        self.mock_outages: dict[str, bool] = {}

    def set_mock_outage(self, connector_name: str, outage: bool) -> None:
        """Simulates an outage for testing resilience."""
        self.mock_outages[connector_name] = outage

    def _health(self, name: str, provider: str) -> ConnectorHealth:
        """Report unknown until an actual provider probe is configured."""
        if self.mock_outages.get(name):
            return ConnectorHealth(
                name,
                HealthStatus.DOWN,
                None,
                {"error": f"Simulated {provider} outage", "simulated": True},
            )
        return ConnectorHealth(
            name,
            HealthStatus.UNKNOWN,
            None,
            {"provider": provider, "reason": "No live health probe is configured"},
        )

    async def check_email(self) -> ConnectorHealth:
        return self._health("email", "SendGrid")

    async def check_crm(self) -> ConnectorHealth:
        return self._health("crm", "HubSpot")

    async def check_sms(self) -> ConnectorHealth:
        return self._health("sms", "Twilio")

    async def check_payments(self) -> ConnectorHealth:
        return self._health("payments", "Stripe")

    async def _peer_health(self, name: str, provider: str) -> ConnectorHealth:
        """Probe a FRIDAY-Universe peer through its real client.

        These three connectors used to answer UNKNOWN ("no live health probe is configured")
        even when the peer was deployed and answering, which made ``/connectors/health``
        useless for exactly the peers Cortex depends on.
        """
        if self.mock_outages.get(name):
            return ConnectorHealth(
                name, HealthStatus.DOWN, None, {"error": f"Simulated {provider} outage", "simulated": True}
            )

        from cortex_integrations.futuris_client import FuturisClient
        from cortex_integrations.intelx_client import IntelXClient
        from cortex_integrations.sentinel_client import SentinelClient

        client = {"futuris": FuturisClient, "intelx": IntelXClient, "sentinel": SentinelClient}[name]()
        detail = await client.health_check()
        status_map = {"UP": HealthStatus.UP, "DOWN": HealthStatus.DOWN, "NOT_CONFIGURED": HealthStatus.UNKNOWN}
        return ConnectorHealth(name, status_map.get(detail["status"], HealthStatus.UNKNOWN), None, detail)

    async def check_futuris(self) -> ConnectorHealth:
        return await self._peer_health("futuris", "Futuris")

    async def check_intelx(self) -> ConnectorHealth:
        return await self._peer_health("intelx", "IntelX")

    async def check_sentinel(self) -> ConnectorHealth:
        return await self._peer_health("sentinel", "Sentinel")

    async def check_all(self) -> dict[str, Any]:
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
        any_degraded = any(c.status == HealthStatus.DEGRADED for c in checks)
        overall = (
            HealthStatus.UP
            if all_up
            else HealthStatus.DOWN if any_down else HealthStatus.DEGRADED if any_degraded else HealthStatus.UNKNOWN
        )

        return {
            "overall_status": overall.value,
            "total_connectors": len(checks),
            "healthy_count": sum(1 for c in checks if c.status == HealthStatus.UP),
            "unhealthy_count": sum(1 for c in checks if c.status in {HealthStatus.DOWN, HealthStatus.DEGRADED}),
            "unverified_count": sum(1 for c in checks if c.status == HealthStatus.UNKNOWN),
            "connectors": {
                c.name: {
                    "status": c.status.value,
                    "latency_ms": round(c.latency_ms, 2) if c.latency_ms is not None else None,
                    "details": c.details,
                    "checked_at": c.checked_at.isoformat(),
                }
                for c in checks
            },
            "timestamp": datetime.now(UTC).isoformat(),
        }


global_connector_manager = ConnectorManager()

_STATUS_LABELS = {
    HealthStatus.UP.value: "HEALTHY",
    HealthStatus.DEGRADED.value: "DEGRADED",
    HealthStatus.DOWN.value: "UNHEALTHY",
    HealthStatus.UNKNOWN.value: "UNVERIFIED",
}


async def get_live_connector_registry() -> list[dict[str, Any]]:
    """Live connector inventory built from real health checks.

    Replaces the old static ``CONNECTOR_HEALTH`` table that reported every
    connector HEALTHY with zero failures — fabricated health that hid real
    outages from operators (audit S10, fixed 2026-10-07). Statuses are honest:
    UNVERIFIED means no live probe is configured, never "healthy".
    """
    report = await global_connector_manager.check_all()
    registry: list[dict[str, Any]] = []
    for name, info in report["connectors"].items():
        status = info["status"]
        registry.append(
            {
                "id": name,
                "name": info["details"].get("provider", name),
                "scope": f"integrations:{name}",
                "status": _STATUS_LABELS.get(status, "UNVERIFIED"),
                "failure_count": 0 if status == HealthStatus.UP.value else 1,
                "last_sync": info["checked_at"],
                "latency_ms": info["latency_ms"],
                "details": info["details"],
            }
        )
    return registry
