import os
import sys

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
paths = [
    root_dir,
    os.path.join(root_dir, "packages/core/src"),
    os.path.join(root_dir, "packages/event_schema/src"),
    os.path.join(root_dir, "packages/agents/src"),
    os.path.join(root_dir, "packages/ai_universe_adapter/src"),
    os.path.join(root_dir, "packages/tool_runtime/src"),
    os.path.join(root_dir, "packages/integrations/src"),
    os.path.join(root_dir, "packages/policy_engine/src"),
    os.path.join(root_dir, "packages/workflow_engine/src"),
    os.path.join(root_dir, "packages/identity/src"),
    os.path.join(root_dir, "packages/analytics/src"),
    os.path.join(root_dir, "packages/intelligence/src"),
    os.path.join(root_dir, "packages/memory/src"),
    os.path.join(root_dir, "apps/api/src"),
    os.path.join(root_dir, "apps/worker/src"),
]

for p in paths:
    if p not in sys.path:
        sys.path.insert(0, p)
