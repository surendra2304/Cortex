from __future__ import annotations
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit
from .models import Principal, SideEffect, ToolCall

class PolicyDenied(PermissionError):
    pass

@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    approval_required: bool = False

class PolicyEngine:
    def authorize_tool(self, principal: Principal, call: ToolCall, approved: bool) -> PolicyDecision:
        if call.side_effect == SideEffect.FORBIDDEN:
            return PolicyDecision(False, "forbidden capability", True)
        missing = set(call.scopes) - set(principal.scopes)
        if missing:
            return PolicyDecision(False, f"missing scopes: {sorted(missing)}", True)
        needs_approval = call.side_effect in {SideEffect.SENSITIVE, SideEffect.HIGH_IMPACT}
        if needs_approval and not approved:
            return PolicyDecision(False, "explicit approval required", True)
        return PolicyDecision(True, "allowed", False)

    @staticmethod
    def require_tenant(principal: Principal, resource_tenant_id: str) -> None:
        if principal.tenant_id != resource_tenant_id:
            raise PolicyDenied("cross-tenant resource access denied")

    @staticmethod
    def validate_redirect_chain(hops: list[str], max_hops: int = 5) -> None:
        if len(hops) > max_hops:
            raise PolicyDenied("redirect chain exceeds maximum hops")

    @staticmethod
    def validate_url(url: str, allowed_hosts: set[str] | None = None) -> None:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            raise PolicyDenied("invalid URL")
        host = parts.hostname.lower().rstrip(".")
        if allowed_hosts and host not in allowed_hosts:
            raise PolicyDenied("host is not allowlisted")
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise PolicyDenied("DNS resolution failed") from exc
        for info in infos:
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise PolicyDenied(f"unsafe destination: {ip}")
