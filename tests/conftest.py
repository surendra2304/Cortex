"""Shared pytest fixtures.

The suite runs against **real** SQLite-backed sessions (not mocks) so that
schema, constraints, idempotency and tenant scoping are exercised end to end.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

os.environ["APP_ENV"] = "development"
# PyJWT correctly rejects empty HMAC keys. Tests must sign with a test-only key
# rather than relying on python-jose's former acceptance of an empty secret.
TEST_JWT_SECRET = "cortex-pytest-only-signing-key-not-for-deployment-2026"
os.environ["JWT_SECRET"] = TEST_JWT_SECRET

import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ── Workspace path bootstrap (CWD independent) ───────────────────────────────
_root_dir = Path(__file__).resolve().parent.parent
if str(_root_dir) not in sys.path:
    sys.path.insert(0, str(_root_dir))
from cortex_upgrade.paths import ensure_workspace_paths  # noqa: E402

ensure_workspace_paths(_root_dir)

from cortex_api.api_keys import generate_api_key, hash_api_key  # noqa: E402
from cortex_api.config import Base, get_db_session, get_redis_client, settings  # noqa: E402

settings.app_env = "development"
from cortex_api.db_models import ApiKeyModel  # noqa: E402
from cortex_api.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


class FakeRedis:
    """Minimal async Redis double covering the operations the API performs."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.strings: dict[str, str] = {}
        self.streams: list[tuple[str, dict]] = []
        self.fail_incr = False
        self.fail_xadd = False

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool:
        if nx and key in self.strings:
            return False
        self.strings[key] = value
        return True

    async def incr(self, key: str) -> int:
        if self.fail_incr:
            raise ConnectionError("redis unavailable")
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def xadd(self, stream: str, fields: dict) -> str:
        if self.fail_xadd:
            raise ConnectionError("redis unavailable")
        self.streams.append((stream, fields))
        return f"{len(self.streams)}-0"

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def sqlite_engine(tmp_path):
    """File-backed SQLite engine with the full ORM schema created."""
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'cortex_test.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )

    from sqlalchemy import event as _sa_event

    @_sa_event.listens_for(engine.sync_engine, "connect")
    def _sqlite_test_wal(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    async def _create() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(_create())
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def session_factory(sqlite_engine):
    return async_sessionmaker(bind=sqlite_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def fake_redis():
    return FakeRedis()


@pytest.fixture
def api_client(session_factory, fake_redis):
    """TestClient wired to the SQLite session factory and the fake Redis."""

    async def override_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_redis_client] = lambda: fake_redis
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def provisioned_key(session_factory):
    """Provision a public API key and return ``(plaintext, tenant_id, site_id)``."""
    plaintext = generate_api_key()
    tenant_id, site_id = "tenant_test", "site_test"

    async def _insert() -> str:
        async with session_factory() as session:
            session.add(
                ApiKeyModel(
                    id="key_test_fixture",
                    tenant_id=tenant_id,
                    site_id=site_id,
                    key_hash=hash_api_key(plaintext),
                    key_prefix=plaintext[:12],
                    name="pytest-fixture",
                    is_active=True,
                )
            )
            await session.commit()
        return plaintext

    asyncio.run(_insert())
    return plaintext, tenant_id, site_id


def auth_headers(role: str = "cortex_admin", tenant_id: str = "tenant_test", subject: str = "usr_test") -> dict:
    """Mint a signed JWT for API tests.

    Uses the non-empty test-only key loaded by the test configuration. Empty
    HMAC keys are rejected by PyJWT and must never be used as a test shortcut.
    """
    import os

    from cortex_api import auth as auth_module
    import jwt

    secret = auth_module.JWT_SECRET or os.getenv(
        "JWT_SECRET", "cortex-pytest-only-signing-key-not-for-deployment-2026"
    )
    if not secret:
        raise RuntimeError("Cortex tests require a non-empty test JWT_SECRET")
    token = jwt.encode(
        {
            "sub": subject,
            "role": role,
            "tenant_id": tenant_id,
            "exp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            + __import__("datetime").timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


def friday_headers(monkeypatch, key: str = "test-friday-service-key-32chars-min") -> dict:
    """Configure and supply a FRIDAY service key for internal endpoints."""
    monkeypatch.setenv("FRIDAY_API_KEY", key)
    monkeypatch.delenv("FRIDAY_UNIVERSE_API_KEY", raising=False)
    return {"X-Friday-Api-Key": key}


def event_payload(
    event_id: str = "evt_fixture_1", tenant_id: str = "tenant_test", site_id: str = "site_test", **overrides
) -> dict:
    payload = {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "site_id": site_id,
        "type": "page_view",
        "actor": {"type": "visitor", "id": "vis_fixture"},
        "session_id": "sess_fixture",
        "source": "web-sdk",
        "data": {"path": "/pricing"},
        "consent": {"analytics": True},
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def no_dev_auth_bypass():
    """Run the whole suite with the development auth bypass switched off.

    The bypass exists for interactive local use only. Tests must always exercise
    real credentials, otherwise a missing authorization check goes unnoticed
    (audit defect C4). Individual tests that specifically cover the bypass turn it
    back on themselves.
    """
    from cortex_api import auth as auth_module

    original = auth_module.DEV_AUTH_BYPASS
    auth_module.DEV_AUTH_BYPASS = False
    yield
    auth_module.DEV_AUTH_BYPASS = original
