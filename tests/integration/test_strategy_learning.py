import pytest
import os
import sys
from unittest.mock import AsyncMock, MagicMock

for p in [
    "packages/core/src",
    "packages/event_schema/src",
    "packages/memory/src",
    "apps/api/src",
]:
    sys.path.insert(0, os.path.abspath(p))

from nexus_memory import MemoryStore, MemoryScope


@pytest.mark.asyncio
async def test_strategy_learning_and_performance_feedback_e2e():
    """
    End-to-End Closed-Loop Strategy Learning:
    Track action outcomes -> calculate strategy success rate -> verify auto-promotion and auto-demotion thresholds.
    """
    memory_store = MemoryStore()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock(return_value=None)
    mock_db.rollback = AsyncMock(return_value=None)

    # 1. Simulate 20 high-performing interventions (>60% success rate)
    for i in range(20):
        await memory_store.record_outcome(
            db=mock_db,
            action_id=f"act_high_{i}",
            action_type="banner_injection",
            context_snapshot={"intent_score": 0.85},
            verdict="SUCCESS",
            metric_delta={"conversion_rate": 0.12}
        )

    high_perf = await memory_store.get_strategy_performance("banner_injection")
    assert high_perf["total_executions"] == 20
    assert high_perf["success_rate"] == 1.0
    assert high_perf["status"] == "PROVEN"

    # 2. Simulate 10 failing interventions (<30% success rate)
    for i in range(10):
        await memory_store.record_outcome(
            db=mock_db,
            action_id=f"act_fail_{i}",
            action_type="cold_popup",
            context_snapshot={"intent_score": 0.20},
            verdict="FAILURE",
            metric_delta={"conversion_rate": -0.05}
        )

    fail_perf = await memory_store.get_strategy_performance("cold_popup")
    assert fail_perf["total_executions"] == 10
    assert fail_perf["success_rate"] == 0.0
    assert fail_perf["status"] == "DEMOTED"
