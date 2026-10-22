"""Workspace path bootstrap.

The monorepo keeps each subsystem in its own ``packages/*/src`` or
``apps/*/src`` directory.  Historically every entry module re-derived those
paths from the *current working directory* with ``os.path.abspath(...)``,
which silently produced a broken import graph whenever a process started
outside the repository root (containers with a different WORKDIR, cron jobs,
``cd /tmp && python -m cortex_api.main``).

``ensure_workspace_paths()`` resolves locations relative to this file and is
safe to call repeatedly.  Paths are *appended* so that installed
distributions always win over repository copies.
"""

from __future__ import annotations

import sys
from pathlib import Path


def workspace_root() -> Path:
    """Repository root (ensuring fallback to actual repo directory even when installed)."""
    cwd = Path.cwd().resolve()
    if (cwd / "Dockerfile").is_file() or (cwd / "pyproject.toml").is_file():
        return cwd
    for parent in [cwd, *cwd.parents]:
        if (parent / "Dockerfile").is_file() and (parent / "cortex_upgrade").is_dir():
            return parent
    pkg_parent = Path(__file__).resolve().parent.parent
    if (pkg_parent / "Dockerfile").is_file():
        return pkg_parent
    return cwd


def _source_roots(root: Path) -> list[Path]:
    roots: list[Path] = []
    for parent in ("packages", "apps"):
        base = root / parent
        if base.is_dir():
            roots.extend(sorted(p / "src" for p in base.iterdir() if (p / "src").is_dir()))
    return roots


def ensure_workspace_paths(root: Path | None = None) -> Path:
    """Make every workspace source root importable. Returns the repo root."""
    resolved = root or workspace_root()
    for candidate in (resolved, *_source_roots(resolved)):
        entry = str(candidate)
        if entry not in sys.path:
            sys.path.append(entry)
    return resolved


__all__ = ["ensure_workspace_paths", "workspace_root"]
