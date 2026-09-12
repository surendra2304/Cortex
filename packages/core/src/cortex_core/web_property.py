from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import copy
import logging

logger = logging.getLogger("cortex-web-property")


class PropertyGovernanceError(Exception):
    """Base exception for web property governance violations."""
    pass


class UnauthorizedPropertyError(PropertyGovernanceError):
    """Raised when an operation targets an unregistered website or web application."""
    pass


class OperationNotAllowedError(PropertyGovernanceError):
    """Raised when a requested operation is not in the property's allowed operations list."""
    pass


class EnvironmentMismatchError(PropertyGovernanceError):
    """Raised when the target environment does not match the property's registered environment."""
    pass


@dataclass
class WebProperty:
    """
    Explicitly registered website or web application governed by Cortex.
    Cortex operates strictly within registered properties.
    """
    property_id: str
    name: str
    allowed_domains: List[str]
    allowed_operations: List[str]
    target_environment: str = "production"  # production, staging, development
    approval_policy: Dict[str, Any] = field(default_factory=lambda: {
        "high_impact_requires_approval": True,
        "auto_approved_operations": ["analytics_query", "session_inspect", "cache_flush"],
        "max_risk_score_auto_approve": 0.3
    })
    rollback_policy: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "snapshot_strategy": "state_snapshot",
        "auto_rollback_on_error": True,
        "max_rollback_window_seconds": 3600
    })
    state_snapshot: Dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_operation_allowed(self, operation: str) -> bool:
        """Checks if operation is explicitly permitted on this property."""
        op_norm = operation.lower().strip()
        return op_norm in [o.lower().strip() for o in self.allowed_operations]

    def is_domain_allowed(self, domain_or_url: str) -> bool:
        """Checks if domain or URL matches allowed domains for this property."""
        target = domain_or_url.lower().strip()
        for allowed in self.allowed_domains:
            allowed_clean = allowed.lower().strip().replace("https://", "").replace("http://", "").rstrip("/")
            if allowed_clean in target:
                return True
        return False


class PropertyRegistry:
    """
    In-memory registry of websites and web applications under Cortex governance.
    Scopes Cortex strictly to authorized properties.
    """
    def __init__(self) -> None:
        self._properties: Dict[str, WebProperty] = {}
        self._seed_default_properties()

    def _seed_default_properties(self) -> None:
        """Seeds standard FRIDAY Universe web properties."""
        self.register(WebProperty(
            property_id="site_storefront",
            name="E-Commerce Storefront",
            allowed_domains=["https://storefront.example.com", "storefront.example.com", "localhost:3000"],
            allowed_operations=[
                "analytics_query", "session_inspect", "banner_injection",
                "experiment_mutate", "content_publish", "cache_flush",
                "config_update", "payment_initiate", "email_dispatch", "account_update",
                "recommend_intervention"
            ],
            target_environment="production",
            approval_policy={
                "high_impact_requires_approval": True,
                "auto_approved_operations": ["analytics_query", "session_inspect", "cache_flush"],
                "max_risk_score_auto_approve": 0.3
            },
            rollback_policy={
                "enabled": True,
                "snapshot_strategy": "state_snapshot",
                "auto_rollback_on_error": True
            },
            state_snapshot={
                "active_banner": "default_welcome",
                "theme": "light",
                "featured_collection": "summer_2026",
                "rate_limit_rpm": 1200
            }
        ))

        self.register(WebProperty(
            property_id="site_main",
            name="Corporate Marketing Portal",
            allowed_domains=["https://example.com", "example.com", "localhost:8000"],
            allowed_operations=[
                "analytics_query", "session_inspect", "banner_injection",
                "experiment_mutate", "content_publish", "deployment_traffic_switch",
                "config_update", "payment_initiate", "email_dispatch", "account_update",
                "recommend_intervention"
            ],
            target_environment="production",
            approval_policy={
                "high_impact_requires_approval": True,
                "auto_approved_operations": ["analytics_query", "session_inspect"],
                "max_risk_score_auto_approve": 0.2
            },
            rollback_policy={
                "enabled": True,
                "snapshot_strategy": "state_snapshot",
                "auto_rollback_on_error": True
            },
            state_snapshot={
                "routing_version": "v2.1.0",
                "traffic_split_pct": 100,
                "active_experiments": ["hero_headline_a"]
            }
        ))

        self.register(WebProperty(
            property_id="app_dashboard",
            name="SaaS Web Application Dashboard",
            allowed_domains=["https://app.example.com", "app.example.com", "localhost:5173"],
            allowed_operations=[
                "analytics_query", "session_inspect", "account_update",
                "payment_initiate", "email_dispatch", "sms_dispatch",
                "billing_update", "recommend_intervention"
            ],
            target_environment="production",
            approval_policy={
                "high_impact_requires_approval": True,
                "auto_approved_operations": ["analytics_query", "session_inspect"],
                "max_risk_score_auto_approve": 0.1
            },
            rollback_policy={
                "enabled": True,
                "snapshot_strategy": "state_snapshot",
                "auto_rollback_on_error": True
            },
            state_snapshot={
                "subscription_tier": "enterprise",
                "allowed_seats": 50,
                "billing_currency": "USD"
            }
        ))

        self.register(WebProperty(
            property_id="site_staging",
            name="Staging Testing Environment",
            allowed_domains=["https://staging.example.com", "staging.example.com"],
            allowed_operations=[
                "analytics_query", "session_inspect", "banner_injection",
                "experiment_mutate", "content_publish", "config_update",
                "recommend_intervention"
            ],
            target_environment="staging",
            approval_policy={
                "high_impact_requires_approval": False,
                "auto_approved_operations": ["analytics_query", "session_inspect", "banner_injection", "content_publish"],
                "max_risk_score_auto_approve": 0.8
            },
            rollback_policy={
                "enabled": True,
                "snapshot_strategy": "state_snapshot",
                "auto_rollback_on_error": True
            },
            state_snapshot={
                "build_hash": "stg_99a8b7",
                "test_mode": True
            }
        ))

    def register(self, prop: WebProperty) -> WebProperty:
        """Registers a web property."""
        self._properties[prop.property_id] = prop
        logger.info(f"Registered web property: {prop.property_id} ({prop.name}) in {prop.target_environment}")
        return prop

    def get(self, property_id: str) -> Optional[WebProperty]:
        """Fetches property by ID."""
        return self._properties.get(property_id)

    def list_properties(self) -> List[WebProperty]:
        """Lists all registered web properties."""
        return list(self._properties.values())

    def validate_property_access(
        self,
        property_id: str,
        operation: Optional[str] = None,
        environment: Optional[str] = None
    ) -> WebProperty:
        """
        Validates that a property is registered and authorized for the requested operation.
        Raises typed exceptions fail-closed.
        """
        prop = self.get(property_id)
        if not prop:
            raise UnauthorizedPropertyError(
                f"Cortex is strictly scoped to registered websites and web applications. "
                f"Property '{property_id}' is not registered."
            )

        if environment and environment.lower() != prop.target_environment.lower():
            raise EnvironmentMismatchError(
                f"Property '{property_id}' target environment is '{prop.target_environment}', "
                f"requested environment '{environment}' does not match."
            )

        if operation and not prop.is_operation_allowed(operation):
            raise OperationNotAllowedError(
                f"Operation '{operation}' is not permitted on property '{property_id}'. "
                f"Allowed operations: {prop.allowed_operations}"
            )

        return prop

    def capture_snapshot(self, property_id: str) -> Dict[str, Any]:
        """Captures a deep copy snapshot of property state."""
        prop = self.validate_property_access(property_id)
        return copy.deepcopy(prop.state_snapshot)

    def restore_snapshot(self, property_id: str, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Restores property state from snapshot."""
        prop = self.validate_property_access(property_id)
        prop.state_snapshot = copy.deepcopy(snapshot)
        logger.info(f"Restored state snapshot for property '{property_id}'.")
        return prop.state_snapshot


# Global default registry instance
global_property_registry = PropertyRegistry()
