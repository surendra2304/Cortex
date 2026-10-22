#!/usr/bin/env python3
"""Boot the CORTEX API from a fresh checkout.

Why this exists
---------------
``uvicorn cortex_api.main:app`` only works when every package directory happens
to be on ``PYTHONPATH`` (the Docker image sets it explicitly). From a fresh
checkout the import fails with ``ModuleNotFoundError: No module named
'cortex_api'`` — verified in this environment — which makes the documented
"run the API" step depend on undocumented environment setup.

This launcher puts the repository's ``src`` directories on ``sys.path`` and then
starts uvicorn, so both of these work:

    python scripts/run_api.py
    python scripts/run_api.py --port 9000 --reload

Inside an installed wheel the packages are already importable, so the path
bootstrap is a no-op and ``cortex-api`` (console entry point) remains available.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from cortex_upgrade.paths import ensure_workspace_paths

    ensure_workspace_paths(ROOT)
except ImportError:  # pragma: no cover - installed layout
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CORTEX API server")
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--reload", action="store_true", help="auto-reload on code changes (development)")
    parser.add_argument("--log-level", default=os.getenv("LOG_LEVEL", "info"))
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        return 1

    uvicorn.run(
        "cortex_api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
