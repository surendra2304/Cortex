import os
import sys
import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("apps/worker/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from nexus_core.orchestrator import Orchestrator
from nexus_worker.main import process_event


@pytest.mark.asyncio
async def test_worker_cognitive_loop_pipeline():
    orchestrator = Orchestrator()

    event_payload = {
        "event_id": "evt_worker_100",
        "tenant_id": "tenant_alpha",
        "site_id": "site_store",
        "type": "checkout.completed",
        "occurred_at": datetime.utcnow().isoformat(),
        "actor": {"type": "user", "id": "usr_vip_888"},
        "source": "webhook:stripe",
        "data": {"order_total": 499.0, "currency": "USD"},
        "trace_id": "trc_worker_pipe_1"
    }

    raw_stream_message = json.dumps(event_payload)

    # Execute worker processor directly
    result = await process_event("1724770000001-0", raw_stream_message, orchestrator)

    assert result is not None
    assert result["status"] == "success"
    assert result["agent_id"] == "agent_sales"
    assert result["trace_id"] == "trc_worker_pipe_1"
    assert len(result["trace"]) >= 10
    assert any(t["phase"] == "1.Observe" for t in result["trace"])
    assert any(t["phase"] == "8.Measure" for t in result["trace"])
    assert any(t["phase"] == "9.Learn" for t in result["trace"])
    assert any(t["phase"] == "10.Continue" for t in result["trace"])
