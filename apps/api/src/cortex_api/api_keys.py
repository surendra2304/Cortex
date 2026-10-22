"""Public API key authentication and provisioning.

Security contract (see PHASE0-2_AUDIT_2026-10-05.md, defects C1/C4):

1. A tenant identity is **always** derived from a validated credential.
   Payload-supplied ``tenant_id`` values are never authoritative.
2. A missing, unknown, revoked or malformed key is rejected with ``401``.
3. If the key store cannot be queried (database unavailable) the request fails
   closed with ``503`` instead of degrading to anonymous access.

Keys are stored as SHA-256 hashes (``api_keys.key_hash``); the plaintext value
is returned exactly once by the provisioning path.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cortex_api.db_models import ApiKeyModel

logger = logging.getLogger("cortex-api-keys")

PUBLIC_KEY_PREFIX = "pk_live_"
SAFE_PREFIXES = ("pk_", "pub_")


def hash_api_key(api_key: str) -> str:
    """Deterministic SHA-256 digest used for at-rest key comparison."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return f"{PUBLIC_KEY_PREFIX}{secrets.token_hex(16)}"


async def authenticate_public_key(
    public_key: str | None,
    db: AsyncSession,
    site_id: str | None = None,
) -> ApiKeyModel:
    """Resolve a public SDK/webhook key to its :class:`ApiKeyModel`.

    Raises ``HTTPException(401)`` for missing/unknown/inactive keys and
    ``HTTPException(503)`` when the credential store cannot be reached.
    """
    if not public_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Missing X-Cortex-Public-Key header. Event ingestion and webhook "
                "delivery require a provisioned public API key."
            ),
        )

    key_hash = hash_api_key(public_key)
    try:
        stmt = select(ApiKeyModel).where(
            ApiKeyModel.key_hash == key_hash,
            ApiKeyModel.is_active == True,  # noqa: E712 - SQLAlchemy comparison
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none() if hasattr(res, "scalar_one_or_none") else None
    except Exception as exc:  # pragma: no cover - exercised via failure injection
        logger.error("API key store lookup failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Credential store unavailable; refusing to authenticate anonymously.",
        ) from exc

    if record is None:
        logger.warning("Rejected unknown public API key (prefix=%s).", public_key[:8])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or deactivated Public API Key.",
        )

    if site_id and record.site_id != site_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Public API Key is scoped to site '{record.site_id}' and cannot be " f"used for site '{site_id}'."
            ),
        )

    record.last_used_at = datetime.now(UTC)
    try:
        await db.commit()
    except Exception as exc:  # pragma: no cover
        logger.warning("Failed to record last_used_at for key %s: %s", record.id, exc)
        await db.rollback()

    return record


async def provision_api_key(
    db: AsyncSession,
    tenant_id: str,
    site_id: str,
    name: str,
) -> tuple[str, ApiKeyModel]:
    """Create a new active public key. Returns ``(plaintext, record)``."""
    if not tenant_id or not site_id:
        raise ValueError("tenant_id and site_id are required to provision an API key")

    plaintext = generate_api_key()
    model = ApiKeyModel(
        id=f"key_{secrets.token_hex(8)}",
        tenant_id=tenant_id,
        site_id=site_id,
        key_hash=hash_api_key(plaintext),
        key_prefix=plaintext[:12],
        name=name,
        is_active=True,
        created_at=datetime.now(UTC),
    )
    db.add(model)
    await db.commit()
    logger.info("Provisioned API key '%s' for tenant '%s' (site '%s').", name, tenant_id, site_id)
    return plaintext, model
