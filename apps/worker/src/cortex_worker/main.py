import asyncio
import json
import logging
import os
import sys
from datetime import UTC, datetime

import redis.asyncio as aioredis

# Resolve packages relative to the repository root, not the current directory,
# so the worker starts the same way from a container, a cron entrypoint or a
# developer shell (audit defect H5).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))
try:  # the monorepo root may not exist when the worker runs from an installed wheel
    from cortex_upgrade.paths import ensure_workspace_paths  # noqa: E402

    ROOT = ensure_workspace_paths()
    sys.path.insert(0, os.path.join(str(ROOT), "apps", "api", "src"))
except ImportError:  # pragma: no cover - installed-wheel layout
    pass

from cortex_api.config import AsyncSessionLocal, settings
from cortex_api.db_models import ApprovalQueueModel
from cortex_core.orchestrator import Orchestrator, build_default_tool_bus
from cortex_event_schema import EventSchema


def _utcnow() -> datetime:
    """Timezone-aware UTC now (never a naive timestamp)."""
    return datetime.now(UTC)


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("cortex-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# The API publishes to settings.redis_event_stream; defaulting the worker to the
# same value keeps the producer/consumer contract in one place.
STREAM_NAME = os.getenv("REDIS_EVENT_STREAM") or settings.redis_event_stream
CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "cortex-worker-group")
CONSUMER_NAME = os.getenv("REDIS_CONSUMER_NAME", f"worker-{os.getpid()}")

# redis-py 8 changed the default wire protocol to RESP3 (HELLO 3). The bundled
# development double (scripts/dev_redis.py) and any RESP2-only deployment expect
# RESP2, and a RESP2-encoded XREADGROUP reply cannot be parsed by a RESP3 client
# — the worker then failed on every read and processed nothing. Pinning the
# protocol keeps the worker wire-compatible with both the dev double and
# production Redis, independent of the installed redis-py major version.
REDIS_PROTOCOL = int(os.getenv("REDIS_PROTOCOL", "2"))

# At-least-once delivery. A message is acknowledged only when it was processed
# successfully or proven poison (unparseable — it can never succeed). A message
# whose cognitive loop raised stays in the pending entries list (PEL) and is
# reclaimed by the PEL recovery loop; after MAX_DELIVERY_ATTEMPTS failed
# deliveries it is acknowledged so one permanently broken event cannot wedge
# the stream forever.
MAX_DELIVERY_ATTEMPTS = int(os.getenv("WORKER_MAX_DELIVERY_ATTEMPTS", "5"))
PEL_RECOVERY_INTERVAL_SECONDS = float(os.getenv("WORKER_PEL_RECOVERY_INTERVAL_SECONDS", "30"))
PEL_MIN_IDLE_MS = int(os.getenv("WORKER_PEL_MIN_IDLE_MS", "60000"))
PEL_RECOVERY_BATCH = int(os.getenv("WORKER_PEL_RECOVERY_BATCH", "100"))


async def init_stream_group(redis_client: aioredis.Redis) -> None:
    """Ensure Redis consumer group exists for the event stream."""
    try:
        await redis_client.xgroup_create(STREAM_NAME, CONSUMER_GROUP, id="0", mkstream=True)
        logger.info(f"Created consumer group '{CONSUMER_GROUP}' on stream '{STREAM_NAME}'.")
    except Exception as exc:
        if "BUSYGROUP" in str(exc):
            logger.debug(f"Consumer group '{CONSUMER_GROUP}' already exists.")
        else:
            logger.warning(f"Error initializing stream group: {exc}")


async def ensure_stream_group(redis_client: aioredis.Redis, exc: Exception) -> bool:
    """Re-create the consumer group when Redis lost it (server restart, FLUSHALL).

    A Redis restart wipes the in-memory double's groups; without this the worker
    would spin on NOGROUP forever and silently stop consuming. Returns True when
    the caller should retry immediately.
    """
    if "NOGROUP" not in str(exc):
        return False
    logger.warning("Consumer group missing (Redis restarted?); re-creating it.")
    await init_stream_group(redis_client)
    return True


async def process_event_with_status(
    event_id: str, payload_str: str, orchestrator: Orchestrator
) -> tuple[str, dict | None]:
    """Decode event, execute 10-phase Cognitive Loop, and report delivery status.

    Returns one of:
      ("ok", result)    — processed; safe to acknowledge
      ("poison", None)  — payload can never validate; acknowledge to stop redelivery
      ("error", None)   — transient failure; leave pending for PEL recovery
    """
    try:
        event_dict = json.loads(payload_str)
        if "payload" in event_dict and isinstance(event_dict["payload"], str):
            event_dict = json.loads(event_dict["payload"])

        event = EventSchema(**event_dict)
    except (json.JSONDecodeError, ValueError, TypeError) as err:
        # Poison: no retry can ever make this payload valid. Acknowledge it (the
        # caller does) so it is not redelivered forever, and record the drop.
        logger.error(f"Poison event [stream_id={event_id}] dropped after failed validation: {err}")
        return "poison", None

    logger.info(
        f"Consuming event [stream_id={event_id}] | type='{event.type}' | actor='{event.actor.id}' | site='{event.site_id}'"
    )

    try:
        async with AsyncSessionLocal() as db_session:
            result = await orchestrator.run_cognitive_loop(event=event, db_session=db_session)
            logger.info(
                f"Cognitive Loop complete [loop_id={result['loop_id']}] | agent='{result['agent_id']}' | decision='{result['decision']}' | actions_executed={result['executed_actions']}"
            )
            return "ok", result
    except Exception as exc:
        logger.error(f"Error processing event through cognitive loop [stream_id={event_id}]: {exc}", exc_info=True)
        return "error", None


async def process_event(event_id: str, payload_str: str, orchestrator: Orchestrator) -> dict | None:
    """Backward-compatible wrapper: returns the loop result (None when it failed)."""
    _status, result = await process_event_with_status(event_id, payload_str, orchestrator)
    return result


async def deliver_message(
    redis_client: aioredis.Redis,
    message_id: str,
    payload_str: str,
    orchestrator: Orchestrator,
    delivery_attempts: dict[str, int],
) -> bool:
    """Process one stream message and apply the acknowledgement policy.

    Returns True when the message was acknowledged (processed or poison),
    False when it must stay pending for PEL recovery.
    """
    status, _result = await process_event_with_status(message_id, payload_str, orchestrator)
    if status in ("ok", "poison"):
        await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
        delivery_attempts.pop(message_id, None)
        logger.debug(f"Acknowledged event {message_id}")
        return True

    attempts = delivery_attempts.get(message_id, 0) + 1
    if attempts >= MAX_DELIVERY_ATTEMPTS:
        logger.error(
            f"Event {message_id} failed {attempts} delivery attempts; acknowledging to stop redelivery."
        )
        await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
        delivery_attempts.pop(message_id, None)
        return True
    delivery_attempts[message_id] = attempts
    logger.warning(
        f"Event {message_id} failed (attempt {attempts}/{MAX_DELIVERY_ATTEMPTS}); left pending for PEL recovery."
    )
    return False


async def run_pel_recovery(
    redis_client: aioredis.Redis,
    orchestrator: Orchestrator,
    delivery_attempts: dict[str, int],
) -> None:
    """Reclaim messages stranded in the pending entries list.

    A worker crash or a cognitive-loop error leaves delivered-but-unacknowledged
    messages in the PEL. XREADGROUP with ">" only hands out never-delivered
    messages, so without recovery those events would be lost forever. Every
    interval we list the PEL, re-claim entries idle past PEL_MIN_IDLE_MS, and
    reprocess them under the same acknowledgement policy as the read loop.
    """
    while True:
        try:
            await asyncio.sleep(PEL_RECOVERY_INTERVAL_SECONDS)
            pending = await redis_client.xpending_range(
                STREAM_NAME, CONSUMER_GROUP, min="-", max="+", count=PEL_RECOVERY_BATCH
            )
            if not pending:
                continue
            logger.info(f"PEL recovery: {len(pending)} pending message(s) found")
            for entry in pending:
                message_id = entry["message_id"]
                if delivery_attempts.get(message_id, 0) >= MAX_DELIVERY_ATTEMPTS:
                    logger.error(
                        f"Event {message_id} exhausted {MAX_DELIVERY_ATTEMPTS} attempts; acknowledging to stop redelivery."
                    )
                    await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                    delivery_attempts.pop(message_id, None)
                    continue
                claimed = await redis_client.xclaim(
                    STREAM_NAME,
                    CONSUMER_GROUP,
                    CONSUMER_NAME,
                    min_idle_time=PEL_MIN_IDLE_MS,
                    message_ids=[message_id],
                )
                if not claimed:
                    continue
                fields = claimed[0][1]
                await deliver_message(
                    redis_client,
                    message_id,
                    fields.get("payload", "{}"),
                    orchestrator,
                    delivery_attempts,
                )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"PEL recovery warning: {exc}")


async def run_scheduled_maintenance_tasks() -> None:
    """
    Scheduled Background Worker Jobs per CORTEX spec section 45:
    - Auto-expire pending approval queue items after 24h
    - Log periodic strategy health check
    """
    while True:
        try:
            await asyncio.sleep(60)  # Runs every minute
            async with AsyncSessionLocal() as db:
                from sqlalchemy import and_, select

                # Auto-expire overdue approvals
                stmt = select(ApprovalQueueModel).where(
                    and_(ApprovalQueueModel.status == "pending", ApprovalQueueModel.expires_at <= _utcnow())
                )
                res = await db.execute(stmt)
                expired_items = res.scalars().all()
                for item in expired_items:
                    item.status = "expired"
                    item.decision_reason = "Auto-rejected by platform safe-default policy upon 24h expiry."
                    item.decided_at = _utcnow()
                    logger.info(f"Auto-expired pending approval item: {item.id}")
                if expired_items:
                    await db.commit()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"Scheduled maintenance task warning: {exc}")


async def run_worker() -> None:
    logger.info(f"Connecting CORTEX autonomous worker to Redis stream at {REDIS_URL}...")
    redis_client = aioredis.from_url(
        REDIS_URL, encoding="utf-8", decode_responses=True, protocol=REDIS_PROTOCOL
    )
    await init_stream_group(redis_client)

    tool_bus = build_default_tool_bus(redis_client=redis_client)
    orchestrator = Orchestrator(tool_bus=tool_bus)

    delivery_attempts: dict[str, int] = {}

    # Launch background maintenance scheduler + PEL recovery loop
    maintenance_task = asyncio.create_task(run_scheduled_maintenance_tasks())
    recovery_task = asyncio.create_task(run_pel_recovery(redis_client, orchestrator, delivery_attempts))

    logger.info(f"CORTEX autonomous worker listening on '{STREAM_NAME}' as '{CONSUMER_NAME}'...")

    try:
        while True:
            try:
                response = await redis_client.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_NAME: ">"},
                    count=10,
                    block=2000,
                )

                if response:
                    for _stream, messages in response:
                        for message_id, fields in messages:
                            payload_str = fields.get("payload", "{}")
                            await deliver_message(
                                redis_client, message_id, payload_str, orchestrator, delivery_attempts
                            )
                else:
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                if await ensure_stream_group(redis_client, exc):
                    continue
                logger.warning(f"Worker read loop warning: {exc}")
                await asyncio.sleep(2)

    except asyncio.CancelledError:
        logger.info("Worker received termination signal.")
    finally:
        maintenance_task.cancel()
        recovery_task.cancel()
        await redis_client.close()
        logger.info("Worker stopped and Redis connection closed.")


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped via KeyboardInterrupt.")
