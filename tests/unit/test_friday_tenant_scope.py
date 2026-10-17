"""FRIDAY service credentials must not imply unrestricted tenant access."""

import pytest
from fastapi import HTTPException

from cortex_api.friday_router import _authorize_command_tenant


def test_friday_service_tenant_allowlist_accepts_only_configured_tenants(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setenv("FRIDAY_ALLOWED_TENANTS", "tenant-a, tenant-b")

    _authorize_command_tenant("tenant-a", {"tenant_id": "system"})
    _authorize_command_tenant("tenant-b", {"tenant_id": "system"})

    with pytest.raises(HTTPException) as exc:
        _authorize_command_tenant("tenant-victim", {"tenant_id": "system"})
    assert exc.value.status_code == 403


def test_production_friday_command_fails_closed_without_tenant_allowlist(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("FRIDAY_ALLOWED_TENANTS", raising=False)

    with pytest.raises(HTTPException) as exc:
        _authorize_command_tenant("tenant-a", {"tenant_id": "system"})
    assert exc.value.status_code == 503


def test_tenant_bound_friday_identity_cannot_override_its_tenant(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("FRIDAY_ALLOWED_TENANTS", raising=False)

    with pytest.raises(HTTPException) as exc:
        _authorize_command_tenant("tenant-b", {"tenant_id": "tenant-a"})
    assert exc.value.status_code == 403
