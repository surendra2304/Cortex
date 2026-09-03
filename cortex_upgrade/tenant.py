from __future__ import annotations
from dataclasses import dataclass
from .models import Principal

class TenantBoundaryError(PermissionError):
    pass

@dataclass(frozen=True)
class TenantScope:
    tenant_id: str

    def require(self, principal: Principal) -> None:
        if self.tenant_id != principal.tenant_id:
            raise TenantBoundaryError("cross-tenant access denied")

    def require_resource(self, resource_tenant_id: str, principal: Principal) -> None:
        if resource_tenant_id != principal.tenant_id:
            raise TenantBoundaryError("resource belongs to another tenant")

def scoped_key(tenant_id: str, resource: str) -> str:
    if not tenant_id or not resource:
        raise ValueError("tenant and resource are required")
    return f"tenant:{tenant_id}:{resource}"
