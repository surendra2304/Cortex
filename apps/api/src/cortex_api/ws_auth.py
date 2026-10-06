"""WebSocket authentication.

Audit defect C3: both live-stream endpoints decoded the query-string token with
``options={"verify_signature": False}`` and silently fell back to
``tenant_default``, so a forged token could subscribe to another tenant's stream.

Contract implemented here
-------------------------
* The ``token`` query parameter must be a JWT whose signature verifies against
  the configured OIDC JWKS (RS256) when present, otherwise against
  ``JWT_SECRET`` (HS256) — identical to :func:`cortex_api.auth.verify_jwt_token`.
* Any failure closes the socket with code ``1008`` (policy violation). The
  tenant is never taken from an unverified token.
* When no signature material exists at all (no ``JWT_SECRET``, no OIDC) and the
  development bypass is active, the connection is accepted into
  ``tenant_default`` only — unverified claims are ignored, so a forged token can
  never select another tenant even locally. In production this configuration
  rejects the upgrade instead.
"""

from __future__ import annotations

import logging

from fastapi import WebSocket
from jose import JWTError, jwt

from cortex_api import auth as auth_module

logger = logging.getLogger("cortex-ws-auth")

WS_POLICY_VIOLATION = 1008
DEFAULT_DEV_TENANT = "tenant_default"


def _rsa_key_from_jwks(jwks: dict, kid: str | None) -> dict:
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            return {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key.get("use"),
                "n": key["n"],
                "e": key["e"],
            }
    return {}


async def authenticate_websocket(websocket: WebSocket, token: str | None) -> str | None:
    """Validate ``token`` and return the authorised tenant, or ``None`` after closing."""
    if not token:
        if auth_module.DEV_AUTH_BYPASS:
            logger.warning("WebSocket connected without a token under the development auth bypass.")
            return DEFAULT_DEV_TENANT
        await _reject(websocket, "Missing token query parameter.")
        return None

    # 1. RS256 via OIDC JWKS (preferred when configured).
    if auth_module.OIDC_JWKS_URL:
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            rsa_key = _rsa_key_from_jwks(await auth_module.get_jwks(), kid)
            if not rsa_key and kid:
                rsa_key = _rsa_key_from_jwks(await auth_module.get_jwks(force_refresh=True), kid)
            if rsa_key:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=["RS256"],
                    audience=auth_module.OIDC_AUDIENCE,
                    issuer=auth_module.OIDC_ISSUER,
                )
                tenant = payload.get("tenant_id")
                if tenant:
                    return tenant
                await _reject(websocket, "Token has no tenant_id claim.")
                return None
        except JWTError as exc:
            logger.warning("WebSocket RS256 verification failed: %s", exc)
            await _reject(websocket, "Invalid token signature.")
            return None

    # 2. HS256 with the configured shared secret.
    if auth_module.JWT_SECRET:
        try:
            payload = jwt.decode(token, auth_module.JWT_SECRET, algorithms=["HS256"])
        except JWTError as exc:
            logger.warning("WebSocket HS256 verification failed: %s", exc)
            await _reject(websocket, "Invalid token signature.")
            return None
        tenant = payload.get("tenant_id")
        if tenant:
            return tenant
        await _reject(websocket, "Token has no tenant_id claim.")
        return None

    # 3. No verification material configured.
    if auth_module.DEV_AUTH_BYPASS:
        logger.warning(
            "No JWT_SECRET/OIDC configured and DEV_AUTH_BYPASS is active: WebSocket granted the default "
            "development tenant '%s'. Unverified token claims are ignored.",
            DEFAULT_DEV_TENANT,
        )
        return DEFAULT_DEV_TENANT

    await _reject(websocket, "JWT authentication is unavailable until a unique JWT_SECRET is configured.")
    return None


async def _reject(websocket: WebSocket, reason: str) -> None:
    try:
        await websocket.close(code=WS_POLICY_VIOLATION, reason=reason)
    except Exception:  # pragma: no cover - socket may already be closed
        pass


__all__ = ["DEFAULT_DEV_TENANT", "WS_POLICY_VIOLATION", "authenticate_websocket"]
