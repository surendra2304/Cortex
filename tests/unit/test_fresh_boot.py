"""Fresh-boot behaviour (audit defect C5).

Phase 2 proved that a default checkout had no database schema at all: the SQLite
file existed but contained zero tables, the application started anyway, and every
write path answered HTTP 200 while persisting nothing.

These tests prove the new contract:
  * a fresh database is created and reported ready on startup,
  * readiness is *false* while a reachable database is missing tables,
  * production never silently creates schema.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from cortex_api import schema as schema_module


def test_ensure_schema_creates_every_expected_table(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    try:
        assert asyncio.run(schema_module.missing_tables(engine)), "a brand new database has no tables"
        result = asyncio.run(schema_module.ensure_schema(engine, allow_create=True))
        assert result["mode"] == "create"
        assert result["created"], "the bootstrap must report the tables it created"
        assert result["missing"] == []
        assert asyncio.run(schema_module.missing_tables(engine)) == []
        assert asyncio.run(schema_module.schema_is_ready(engine)) is True
        # Idempotent: a second boot must not fail on existing tables.
        second = asyncio.run(schema_module.ensure_schema(engine, allow_create=True))
        assert second["created"] == []
        assert second["missing"] == []
    finally:
        asyncio.run(engine.dispose())


def test_production_never_auto_creates_schema(tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'prod.db'}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    try:
        result = asyncio.run(schema_module.ensure_schema(engine, allow_create=False))
        assert result["mode"] == "verify", "production must verify rather than migrate implicitly"
        assert result["created"] == []
        assert result["missing"], "the missing tables are reported so an operator can migrate"
        assert asyncio.run(schema_module.missing_tables(engine)), "the database stays empty"
    finally:
        asyncio.run(engine.dispose())


def test_readiness_reports_an_empty_database_as_not_ready(api_client, monkeypatch):
    """/health/ready must not report UP while the schema is missing."""

    async def _missing(engine):
        return ["events", "visitors"]

    monkeypatch.setattr("cortex_api.schema.missing_tables", _missing)
    response = api_client.get("/health/ready")
    assert response.json()["dependencies"]["schema"].startswith("DOWN")
    assert response.status_code == 503, "a reachable but unmigrated database is not ready"


def test_fresh_boot_writes_survive_a_restart(tmp_path):
    """End-to-end: boot -> ingest -> restart -> the event is still there."""
    from cortex_api.api_keys import generate_api_key, hash_api_key
    from cortex_api.config import Base, get_db_session, get_redis_client
    from cortex_api.db_models import ApiKeyModel, EventModel
    from cortex_api.main import app
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from tests.conftest import event_payload

    db_path = tmp_path / "boot.db"
    dsn = f"sqlite+aiosqlite:///{db_path}"

    def _engine():
        return create_async_engine(dsn, connect_args={"check_same_thread": False}, poolclass=NullPool)

    # ── boot #1: create schema, provision a key, ingest an event
    engine = _engine()
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def _setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add(
                ApiKeyModel(
                    id="key_boot",
                    tenant_id="tenant_boot",
                    site_id="site_boot",
                    key_hash=hash_api_key(key := generate_api_key()),
                    key_prefix=key[:12],
                    name="fresh-boot",
                    is_active=True,
                )
            )
            await session.commit()
        return key

    key = asyncio.run(_setup())

    class _Redis:
        async def incr(self, *_a, **_k):
            return 1

        async def expire(self, *_a, **_k):
            return True

        async def xadd(self, *_a, **_k):
            return "1-0"

    async def override_db():
        async with factory() as session:
            yield session

    from fastapi.testclient import TestClient

    app.dependency_overrides[get_db_session] = override_db
    app.dependency_overrides[get_redis_client] = lambda: _Redis()
    try:
        client = TestClient(app)
        response = client.post(
            "/v1/events",
            json=event_payload(event_id="evt_boot_1", tenant_id="tenant_boot", site_id="site_boot"),
            headers={"X-Cortex-Public-Key": key},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "accepted"
    finally:
        app.dependency_overrides.clear()
    asyncio.run(engine.dispose())

    # ── boot #2: a brand new engine over the same file must still read the row
    engine2 = _engine()
    factory2 = async_sessionmaker(bind=engine2, class_=AsyncSession, expire_on_commit=False)

    async def _read():
        async with factory2() as session:
            rows = (await session.execute(select(EventModel))).scalars().all()
            return [(row.id, row.tenant_id) for row in rows]

    try:
        assert asyncio.run(_read()) == [("evt_boot_1", "tenant_boot")]
    finally:
        asyncio.run(engine2.dispose())


def test_schema_expected_tables_match_the_orm():
    """The schema checker must know about every ORM table (guards silent drift)."""
    from cortex_api.config import Base

    expected = set(schema_module.expected_tables())
    orm_tables = set(Base.metadata.tables)
    assert orm_tables <= expected, f"ORM tables missing from the schema contract: {orm_tables - expected}"


def test_default_database_path_is_repo_relative(monkeypatch):
    """A relative SQLite DSN must resolve to an absolute path on every OS."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_DSN", raising=False)
    monkeypatch.delenv("SQLITE_DSN", raising=False)
    resolved = schema_module.__file__ and __import__(
        "cortex_api.config", fromlist=["resolve_sqlite_dsn"]
    ).resolve_sqlite_dsn("sqlite+aiosqlite:///data/cortex.db")
    prefix = "sqlite+aiosqlite:///"
    assert resolved.startswith(prefix), resolved
    database_path = Path(resolved.removeprefix(prefix))
    assert database_path.is_absolute(), resolved
    assert database_path.parts[-2:] == ("data", "cortex.db"), resolved
