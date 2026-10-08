"""Application settings, database engine/session factories and Redis pool."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

import redis.asyncio as aioredis
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool

from cortex_upgrade.auth import INSECURE_DEFAULTS

logger = logging.getLogger("cortex-config")

Base = declarative_base()

DEFAULT_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _workspace_root() -> Path:
    """Repository root, resolved independently of the process CWD."""
    try:  # pragma: no cover - trivial import guard
        from cortex_upgrade.paths import workspace_root

        return workspace_root()
    except Exception:  # pragma: no cover
        return Path(__file__).resolve().parents[4]


def resolve_sqlite_dsn(dsn: str) -> str:
    """Make relative SQLite file paths absolute so the CWD cannot change them.

    The parent directory is created when missing: a fresh clone has no ``data/``
    directory (it is git-ignored), and SQLite refuses to create the file with
    ``unable to open database file`` — which previously left the server running
    with no schema at all (found by booting from a clean checkout).
    """
    if not dsn.startswith("sqlite"):
        return dsn
    head, sep, tail = dsn.partition("///")
    if not sep or not tail or tail.startswith("/") or tail.startswith(":memory:"):
        return dsn
    resolved = (_workspace_root() / tail).resolve()
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:  # pragma: no cover - permission problems surface later with context
        logger.warning("Could not create database directory %s: %s", resolved.parent, exc)
    return f"{head}///{resolved}"


class Settings(BaseSettings):
    app_name: str = "CORTEX API"
    app_env: str = os.getenv("APP_ENV", "development").lower()
    debug: bool = False
    api_v1_prefix: str = "/v1"
    host: str = "0.0.0.0"
    port: int = 8000
    allowed_origins: list[str] = DEFAULT_ALLOWED_ORIGINS

    # Master API key (operator/backend-to-backend)
    cortex_api_key: str | None = os.getenv("CORTEX_API_KEY")

    # Storage and queues (defaults to local SQLite when no external DB is provided)
    postgres_dsn: str = "sqlite+aiosqlite:///./data/cortex.db"
    redis_url: str = "redis://localhost:6379/0"
    redis_event_stream: str = "cortex:events:stream"

    # Ingestion limits (tunable per deployment; defaults match the specification)
    rate_limit_max_requests: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "1000"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))
    max_batch_size: int = int(os.getenv("MAX_BATCH_SIZE", "50"))
    max_event_bytes: int = int(os.getenv("MAX_EVENT_BYTES", str(256 * 1024)))

    # Schema & bootstrap behaviour
    auto_create_schema: bool = True
    bootstrap_dev_api_key: bool = True

    # Optional authentication for operational endpoints
    metrics_token: str | None = None
    webhook_signing_secret: str | None = None

    # Trust X-Forwarded-For only when the app sits behind a known proxy/LB
    trust_proxy_headers: bool = False

    # Public ingestion / webhook surface
    require_public_key: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_origins(cls, value):
        """Accept JSON arrays or comma-separated strings from the environment."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return DEFAULT_ALLOWED_ORIGINS
            if value.startswith("["):
                return json.loads(value)
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


settings = Settings()
settings.postgres_dsn = resolve_sqlite_dsn(settings.postgres_dsn)

IS_PRODUCTION = settings.app_env == "production" or os.getenv("RENDER", "").lower() in {"1", "true", "yes"}


def _warn_about_production_secrets() -> None:
    """Never crash on boot; enforce strictly at the endpoint/readiness layer."""
    if not IS_PRODUCTION:
        return
    unsafe = []
    if not settings.cortex_api_key or settings.cortex_api_key in INSECURE_DEFAULTS or len(settings.cortex_api_key) < 32:
        unsafe.append("CORTEX_API_KEY")
    jwt_key = os.getenv("JWT_SECRET")
    if not jwt_key or jwt_key in INSECURE_DEFAULTS or len(jwt_key) < 32:
        unsafe.append("JWT_SECRET")
    if unsafe:
        logger.warning(
            "[SECURITY WARNING] Insecure/missing production secrets: %s. "
            "Endpoint-level authentication remains active; set these variables.",
            ", ".join(unsafe),
        )
    if "*" in settings.allowed_origins:
        logger.warning(
            "[SECURITY WARNING] Wildcard CORS origin ('*') is set in production. Restrict to your frontend domain."
        )


_warn_about_production_secrets()


# ── Async engine & session pool ──────────────────────────────────────────────
engine_kwargs: dict = {"echo": False}
if "sqlite" in settings.postgres_dsn:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in settings.postgres_dsn:
        engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs["pool_size"] = 20
    engine_kwargs["max_overflow"] = 10
    engine_kwargs["pool_pre_ping"] = True

engine = create_async_engine(settings.postgres_dsn, **engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Async Redis connection pool ──────────────────────────────────────────────
# protocol=2 pins RESP2 explicitly: redis-py 8 defaults to RESP3 (HELLO 3), and
# the bundled development double (scripts/dev_redis.py) plus any RESP2-only
# deployment cannot serve RESP3 replies. Real Redis accepts RESP2 on every
# version, so this is safe in production and deterministic in development.
redis_pool: aioredis.Redis = aioredis.from_url(
    settings.redis_url,
    encoding="utf-8",
    decode_responses=True,
    protocol=2,
)


async def get_redis_client() -> aioredis.Redis:
    return redis_pool


async def close_resources() -> None:
    """Release engine/Redis handles on application shutdown."""
    with_logging = logging.getLogger("cortex-config.shutdown")
    try:
        await redis_pool.aclose()
    except Exception as exc:  # pragma: no cover - best effort
        with_logging.debug("Redis close skipped: %s", exc)
    try:
        await engine.dispose()
    except Exception as exc:  # pragma: no cover - best effort
        with_logging.debug("Engine dispose skipped: %s", exc)
