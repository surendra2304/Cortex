from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Dict, Any, List, Optional
from enum import Enum
import httpx
import os
import logging
from jose import jwt, JWTError

import hmac

logger = logging.getLogger("cortex-auth")
security = HTTPBearer(auto_error=False)

OIDC_JWKS_URL = os.getenv("OIDC_JWKS_URL")
OIDC_ISSUER = os.getenv("OIDC_ISSUER")
OIDC_AUDIENCE = os.getenv("OIDC_AUDIENCE", "cortex-api")
JWT_SECRET = os.getenv("JWT_SECRET", "super_secret_jwt_signing_key_replace_in_production")

# FRIDAY integration shared secret
FRIDAY_API_KEY = os.getenv("FRIDAY_API_KEY", "")


class Role(str, Enum):
    CORTEX_VIEWER = "cortex_viewer"
    CORTEX_OPERATOR = "cortex_operator"
    CORTEX_ADMIN = "cortex_admin"
    FRIDAY_SYSTEM = "friday_system"


# Role hierarchy mapping
ROLE_HIERARCHY = {
    Role.CORTEX_VIEWER: [Role.CORTEX_VIEWER],
    Role.CORTEX_OPERATOR: [Role.CORTEX_VIEWER, Role.CORTEX_OPERATOR],
    Role.CORTEX_ADMIN: [Role.CORTEX_VIEWER, Role.CORTEX_OPERATOR, Role.CORTEX_ADMIN],
    Role.FRIDAY_SYSTEM: [Role.CORTEX_VIEWER, Role.CORTEX_OPERATOR, Role.CORTEX_ADMIN, Role.FRIDAY_SYSTEM],
}

# In-memory cached JWKS keys
_JWKS_CACHE: Dict[str, Any] = {}


async def get_jwks() -> Dict[str, Any]:
    global _JWKS_CACHE
    if _JWKS_CACHE:
        return _JWKS_CACHE
    if not OIDC_JWKS_URL:
        return {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(OIDC_JWKS_URL)
            if resp.status_code == 200:
                _JWKS_CACHE = resp.json()
                return _JWKS_CACHE
    except Exception as exc:
        logger.warning(f"Failed to fetch JWKS from {OIDC_JWKS_URL}: {exc}")
    return {}


async def verify_jwt_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Dict[str, Any]:
    """Validates RS256 JWT tokens via OIDC JWKS or fallback HS256 in development."""
    if not credentials:
        # Development bypass fallback if MOCK_MODE or no auth provided
        if os.getenv("MOCK_MODE", "true").lower() == "true":
            return {
                "sub": "usr_dev_admin",
                "role": Role.CORTEX_ADMIN.value,
                "tenant_id": "tenant_default",
                "email": "admin@cortex.dev"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header."
        )

    token = credentials.credentials

    # 1. Try RS256 validation via JWKS if configured
    if OIDC_JWKS_URL:
        jwks = await get_jwks()
        try:
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = {}
            for key in jwks.get("keys", []):
                if key["kid"] == unverified_header.get("kid"):
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key.get("use"),
                        "n": key["n"],
                        "e": key["e"]
                    }
                    break

            if rsa_key:
                payload = jwt.decode(
                    token,
                    rsa_key,
                    algorithms=["RS256"],
                    audience=OIDC_AUDIENCE,
                    issuer=OIDC_ISSUER
                )
                role = payload.get("role") or payload.get("https://cortex.dev/role") or Role.CORTEX_VIEWER.value
                return {
                    "sub": payload.get("sub"),
                    "role": role,
                    "tenant_id": payload.get("tenant_id", "tenant_default"),
                    "email": payload.get("email")
                }
        except JWTError as e:
            logger.warning(f"RS256 JWT validation failed: {e}")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid JWT signature: {e}")

    # 2. Fallback to HS256 / Symmetric Secret validation
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        role = payload.get("role", Role.CORTEX_VIEWER.value)
        return {
            "sub": payload.get("sub", "usr_dev"),
            "role": role,
            "tenant_id": payload.get("tenant_id", "tenant_default"),
            "email": payload.get("email")
        }
    except JWTError as exc:
        # Check if it's the mock operator token from the frontend
        if token == os.getenv("NEXT_PUBLIC_OPERATOR_TOKEN", "mock_operator_jwt_token_123"):
            return {
                "sub": "usr_operator_123",
                "role": Role.CORTEX_OPERATOR.value,
                "tenant_id": "tenant_default",
                "email": "operator@cortex.dev"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate JWT credentials: {exc}"
        )


def require_role(required_role: Role):
    """Dependency factory enforcing Role-Based Access Control (RBAC)."""
    async def role_checker(user: Dict[str, Any] = Depends(verify_jwt_token)) -> Dict[str, Any]:
        user_role_str = user.get("role", Role.CORTEX_VIEWER.value)
        try:
            user_role = Role(user_role_str)
        except ValueError:
            user_role = Role.CORTEX_VIEWER

        permitted_roles = ROLE_HIERARCHY.get(user_role, [Role.CORTEX_VIEWER])
        if required_role not in permitted_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{required_role.value}' privilege. Current role is '{user_role_str}'."
            )
        return user
    return role_checker


async def verify_friday_token(
    x_friday_api_key: Optional[str] = Header(None, alias="X-Friday-Api-Key")
) -> Dict[str, Any]:
    """
    Validates that the request originates from the FRIDAY general OS by checking
    the X-Friday-Api-Key header against the FRIDAY_API_KEY env var.

    Uses hmac.compare_digest for constant-time comparison to prevent timing attacks.
    In dev (MOCK_MODE=true and no FRIDAY_API_KEY set), the check is bypassed with a
    clear warning log so engineers can test locally without a live FRIDAY instance.
    """
    configured_key = FRIDAY_API_KEY or os.getenv("FRIDAY_API_KEY", "")
    is_mock = os.getenv("MOCK_MODE", "true").lower() in ("true", "1", "yes")

    # Dev bypass: no key configured and mock mode active
    if not configured_key and is_mock:
        logger.warning(
            "[MOCK MODE] FRIDAY_API_KEY not set — bypassing FRIDAY token verification. "
            "DO NOT use this in production."
        )
        return {
            "sub": "friday_system",
            "role": Role.FRIDAY_SYSTEM.value,
            "tenant_id": "system",
            "system": "FRIDAY",
        }

    if not x_friday_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Friday-Api-Key header. FRIDAY service token is required.",
        )

    # Constant-time comparison to prevent timing side-channel attacks
    provided = x_friday_api_key.encode("utf-8")
    expected = configured_key.encode("utf-8")
    if not hmac.compare_digest(provided, expected):
        logger.warning("FRIDAY authentication attempt with invalid API key rejected.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid FRIDAY service token.",
        )

    logger.info("FRIDAY system authenticated successfully.")
    return {
        "sub": "friday_system",
        "role": Role.FRIDAY_SYSTEM.value,
        "tenant_id": "system",
        "system": "FRIDAY",
    }
