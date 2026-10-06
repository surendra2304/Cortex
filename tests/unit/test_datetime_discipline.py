"""Timezone discipline (audit defect M4).

The codebase mixed naive ``datetime.utcnow()`` with ``DateTime(timezone=True)``
columns. On PostgreSQL the comparison of a naive value against an aware column
never matches, so the worker's approval-expiry sweep could silently do nothing.
"""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ["apps", "packages", "cortex_upgrade"]
SKIP_PARTS = {"__pycache__", ".venv", "node_modules"}

NAIVE_PATTERNS = (
    re.compile(r"\bdatetime\.utcnow\b"),
    re.compile(r"\bdatetime\.utcfromtimestamp\b"),
)


def _python_files():
    for directory in SCANNED_DIRS:
        for path in (REPO_ROOT / directory).rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            yield path


def test_no_naive_utc_calls_remain():
    offenders = []
    for path in _python_files():
        text = path.read_text()
        for pattern in NAIVE_PATTERNS:
            for match in pattern.finditer(text):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line}")
    assert offenders == [], "naive UTC timestamps must not be used:\n  " + "\n  ".join(offenders)


def test_helper_functions_return_aware_timestamps():
    """The shared ``_utcnow`` helpers must produce aware datetimes."""
    from cortex_analytics.outcomes import _utcnow as analytics_utcnow
    from cortex_core.models import _utcnow as core_utcnow

    for helper in (analytics_utcnow, core_utcnow):
        value = helper()
        assert value.tzinfo is not None, f"{helper.__module__}._utcnow returned a naive datetime"
        assert value.utcoffset() == datetime.now(UTC).utcoffset()


def test_orm_defaults_are_aware_callables():
    """Every DateTime column default must be a callable returning aware datetimes."""
    from cortex_api.db_models import Base

    offenders = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.type.__class__.__name__ != "DateTime":
                continue
            for attr in ("default", "onupdate"):
                candidate = getattr(column, attr, None)
                if candidate is None:
                    continue
                if not getattr(candidate, "is_callable", False) and not callable(candidate):
                    continue
                value = candidate.arg if hasattr(candidate, "arg") else candidate
                if callable(value):
                    produced = value(None) if value.__code__.co_argcount else value()
                    if isinstance(produced, datetime) and produced.tzinfo is None:
                        offenders.append(f"{table.name}.{column.name}:{attr}")
    assert offenders == [], f"naive ORM defaults: {offenders}"


def test_attribution_normalises_naive_and_string_inputs():
    """External callers may still hand over naive values or ISO strings."""
    from cortex_analytics.nl_query import _as_utc

    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert _as_utc(naive).tzinfo is not None
    assert _as_utc("2026-01-01T12:00:00Z").tzinfo is not None
    assert _as_utc("2026-01-01T12:00:00+05:30").utcoffset().total_seconds() == 0
    assert _as_utc(None) is None
    assert _as_utc("not-a-date") is None


def test_source_has_no_naive_datetime_constructors_in_signatures():
    """A syntax-level check that imported modules really are clean."""
    for path in _python_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr in {"utcnow", "utcfromtimestamp"}:
                    raise AssertionError(f"{path.relative_to(REPO_ROOT)}:{node.lineno} uses {node.func.attr}()")
