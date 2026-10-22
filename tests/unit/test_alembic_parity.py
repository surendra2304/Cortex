"""Migration/ORM parity (audit finding: 6 of 13 tables had no migration).

The checked-in migrations created only 7 tables, so a deployment that followed
the documented path (`alembic upgrade head`) had a schema the application could
not write to. These tests fail if the two definitions drift again.
"""

from __future__ import annotations

import re
from pathlib import Path

from cortex_api.schema import expected_tables

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "infra" / "alembic" / "versions"


def _tables_declared_in_migrations() -> set[str]:
    declared: set[str] = set()
    for path in VERSIONS_DIR.glob("*.py"):
        declared |= set(re.findall(r"create_table\(\s*[\"']([a-z_]+)[\"']", path.read_text()))
    return declared


def test_every_orm_table_has_a_migration():
    missing = sorted(set(expected_tables()) - _tables_declared_in_migrations())
    assert missing == [], f"ORM tables with no alembic migration: {missing}"


def test_migrations_do_not_create_unknown_tables():
    unknown = sorted(_tables_declared_in_migrations() - set(expected_tables()))
    assert unknown == [], f"migrations create tables the ORM does not know: {unknown}"


def test_alembic_env_targets_real_metadata():
    """`alembic revision --autogenerate` must diff against the ORM, not None."""
    env_py = (VERSIONS_DIR.parent / "env.py").read_text()
    assert "target_metadata = Base.metadata" in env_py
    assert "target_metadata = None" not in env_py
    assert "DATABASE_URL" in env_py, "the DSN must be configurable from the environment"


def test_alembic_ini_has_no_hardcoded_credentials():
    ini = (VERSIONS_DIR.parent.parent / "alembic.ini").read_text()
    assert "nexus:nexus" not in ini, "the stale bundled credential must not remain in alembic.ini"


def test_migration_chain_is_linear():
    """Exactly one head: a branch would leave deployments on an arbitrary revision."""
    revisions: dict[str, str | None] = {}
    for path in VERSIONS_DIR.glob("*.py"):
        text = path.read_text()
        revision = re.search(r"^revision:\s*str\s*=\s*[\"']([^\"']+)", text, re.M)
        down = re.search(r"^down_revision:\s*str\s*\|\s*None\s*=\s*[\"']?([^\"'\n]*)", text, re.M)
        if revision:
            revisions[revision.group(1)] = down.group(1) if down else None

    referenced = {down for down in revisions.values() if down}
    heads = [rev for rev in revisions if rev not in referenced]
    assert len(heads) == 1, f"expected a single migration head, found {sorted(heads)}"
