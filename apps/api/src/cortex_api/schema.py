"""Database schema lifecycle.

Defect C5 in PHASE0-2_AUDIT_2026-10-05.md: nothing ever created the 13 ORM
tables, so every write path failed on a fresh deployment while the ingestion
endpoints still reported ``accepted``.

Policy implemented here:

* ``development``/``test`` (and any environment with ``AUTO_CREATE_SCHEMA=true``)
  → create missing tables from ORM metadata at startup.
* ``production`` → never mutate the schema implicitly; verify it and report
  precisely which tables are missing so migrations can be applied.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from cortex_api.config import Base, settings

logger = logging.getLogger("cortex-schema")

# Importing db_models registers every table on Base.metadata.
from cortex_api import db_models  # noqa: E402,F401  (side-effect import)


def expected_tables() -> list[str]:
    return sorted(Base.metadata.tables.keys())


async def existing_tables(engine: AsyncEngine) -> list[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(lambda conn: inspect(conn).get_table_names())


async def create_schema(engine: AsyncEngine) -> list[str]:
    """Create any missing tables. Returns the list that was newly created."""
    before = set(await existing_tables(engine))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    after = set(await existing_tables(engine))
    created = sorted(after - before)
    if created:
        logger.info("Created %d missing table(s): %s", len(created), ", ".join(created))
    return created


async def missing_tables(engine: AsyncEngine) -> list[str]:
    present = set(await existing_tables(engine))
    return [name for name in expected_tables() if name not in present]


async def ensure_schema(engine: AsyncEngine, *, allow_create: bool | None = None) -> dict[str, object]:
    """Bootstrap or verify the schema according to the environment policy."""
    if allow_create is None:
        allow_create = settings.auto_create_schema and settings.app_env != "production"

    missing = await missing_tables(engine)

    if allow_create and missing:
        try:
            created = await create_schema(engine)
        except Exception as exc:
            logger.error("Schema creation failed: %s", exc)
            raise
        missing = await missing_tables(engine)
        return {"mode": "create", "created": created, "missing": missing}

    if missing:
        logger.error(
            "Database schema is incomplete (%d missing table(s): %s). "
            "Run `alembic -c infra/alembic.ini upgrade head` or set AUTO_CREATE_SCHEMA=true.",
            len(missing),
            ", ".join(missing),
        )
    else:
        logger.info("Database schema verified (%d tables).", len(expected_tables()))

    return {"mode": "verify", "created": [], "missing": missing}


async def schema_is_ready(engine: AsyncEngine) -> bool:
    """Cheap boolean used by the readiness probe."""
    try:
        return not await missing_tables(engine)
    except Exception:
        return False


__all__ = [
    "create_schema",
    "ensure_schema",
    "existing_tables",
    "expected_tables",
    "missing_tables",
    "schema_is_ready",
    "text",
]
