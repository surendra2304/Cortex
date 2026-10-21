"""
Unit tests for External CRM & Commerce Bidirectional Sync Queue Engine.
"""

import pytest
from cortex_integrations.sync_engine import (
    ConflictResolutionPolicy,
    ExternalSyncEngine,
    SyncDirection,
    SyncEntityType,
    SyncJobStatus,
    SyncProvider,
    TokenBucket,
)


@pytest.fixture
def sync_engine() -> ExternalSyncEngine:
    return ExternalSyncEngine()


def test_token_bucket_rate_limiter() -> None:
    bucket = TokenBucket(capacity=5.0, refill_rate_per_sec=2.0)
    # Consume all available capacity
    for _ in range(5):
        assert bucket.consume(1.0) is True
    # Immediate next consumption should fail
    assert bucket.consume(1.0) is False


def test_enqueue_job_idempotency(sync_engine: ExternalSyncEngine) -> None:
    payload = {"email": "alex@enterprise.com", "company": "Acme Corp"}
    job1 = sync_engine.enqueue_job(
        tenant_id="tenant-acme",
        provider=SyncProvider.HUBSPOT,
        entity_type=SyncEntityType.CONTACT,
        external_id="hubspot-101",
        payload=payload,
    )

    assert job1.job_id.startswith("sync-")
    assert job1.status == SyncJobStatus.QUEUED
    assert job1.attempt_count == 0

    # Enqueue same payload again -> returns duplicate identical job
    job2 = sync_engine.enqueue_job(
        tenant_id="tenant-acme",
        provider=SyncProvider.HUBSPOT,
        entity_type=SyncEntityType.CONTACT,
        external_id="hubspot-101",
        payload=payload,
    )
    assert job2.job_id == job1.job_id
    assert len(sync_engine.list_jobs("tenant-acme")) == 1


def test_cursor_lifecycle(sync_engine: ExternalSyncEngine) -> None:
    cursor = sync_engine.get_cursor(
        tenant_id="tenant-stripe",
        provider=SyncProvider.STRIPE,
        entity_type=SyncEntityType.SUBSCRIPTION,
    )
    assert cursor.cursor_token == "epoch-start"
    assert cursor.records_synced == 0

    advanced = sync_engine.update_cursor(
        tenant_id="tenant-stripe",
        provider=SyncProvider.STRIPE,
        entity_type=SyncEntityType.SUBSCRIPTION,
        next_cursor_token="sub_tok_999",
        synced_count=10,
    )
    assert advanced.cursor_token == "sub_tok_999"
    assert advanced.records_synced == 10


def test_conflict_resolution_strategies(sync_engine: ExternalSyncEngine) -> None:
    local_data = {"email": "bob@domain.com", "tier": "free", "updated_at": "2026-10-20T10:00:00Z"}
    remote_data = {"email": "bob@domain.com", "tier": "pro", "updated_at": "2026-10-21T10:00:00Z"}

    # Last write wins
    resolved_lww = sync_engine.resolve_conflict(
        local_data, remote_data, policy=ConflictResolutionPolicy.LAST_WRITE_WINS
    )
    assert resolved_lww["tier"] == "pro"

    # Source of truth wins (remote is SOT)
    resolved_sot = sync_engine.resolve_conflict(
        local_data, remote_data, policy=ConflictResolutionPolicy.SOURCE_OF_TRUTH_WINS, source_of_truth="remote"
    )
    assert resolved_sot["tier"] == "pro"

    # Manual reconciliation
    resolved_manual = sync_engine.resolve_conflict(
        local_data, remote_data, policy=ConflictResolutionPolicy.MANUAL_RECONCILIATION
    )
    assert resolved_manual["_conflict_flag"] is True
    assert resolved_manual["_remote_version"]["tier"] == "pro"


@pytest.mark.asyncio
async def test_process_pending_jobs_success_and_quarantine(sync_engine: ExternalSyncEngine) -> None:
    # 1. Successful job
    sync_engine.enqueue_job(
        tenant_id="tenant-corp",
        provider=SyncProvider.SALESFORCE,
        entity_type=SyncEntityType.LEAD,
        external_id="lead-888",
        payload={"name": "Alice Smith"},
    )

    # 2. Poison job that triggers retry & quarantine
    sync_engine.enqueue_job(
        tenant_id="tenant-corp",
        provider=SyncProvider.SALESFORCE,
        entity_type=SyncEntityType.LEAD,
        external_id="lead-poison",
        payload={"name": "Malicious Payload", "force_fail": True},
        max_retries=1,
    )

    receipts = await sync_engine.process_pending_jobs("tenant-corp", max_jobs=10)
    assert len(receipts) == 2

    # Verify first completed
    assert receipts[0].status == SyncJobStatus.COMPLETED
    assert receipts[0].records_affected == 1

    # Verify second quarantined
    assert receipts[1].status == SyncJobStatus.QUARANTINED
    assert "Simulated external provider error" in str(receipts[1].error_message)


def test_tenant_isolation_sync(sync_engine: ExternalSyncEngine) -> None:
    sync_engine.enqueue_job(
        tenant_id="tenant-A",
        provider=SyncProvider.HUBSPOT,
        entity_type=SyncEntityType.CONTACT,
        external_id="ext-1",
        payload={"foo": "bar"},
    )

    assert len(sync_engine.list_jobs("tenant-A")) == 1
    assert len(sync_engine.list_jobs("tenant-B")) == 0
