import asyncio
import json
import logging
import os
import sys
import redis.asyncio as aioredis
from typing import Optional
from datetime import datetime

# Setup package paths
sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))
sys.path.insert(0, os.path.abspath("packages/identity/src"))
sys.path.insert(0, os.path.abspath("packages/analytics/src"))
sys.path.insert(0, os.path.abspath("packages/intelligence/src"))
sys.path.insert(0, os.path.abspath("packages/memory/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from cortex_event_schema import EventSchema
from cortex_core.orchestrator import Orchestrator, build_default_tool_bus
from cortex_api.config import AsyncSessionLocal
from cortex_api.db_models import ApprovalQueueModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("cortex-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STREAM_NAME = os.getenv("REDIS_EVENT_STREAM", "cortex:events:stream")
CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "cortex-worker-group")
CONSUMER_NAME = os.getenv("REDIS_CONSUMER_NAME", f"worker-{os.getpid()}")


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


async def process_event(
    event_id: str,
    payload_str: str,
    orchestrator: Orchestrator
) -> Optional[dict]:
    """Decode event, execute 10-phase Cognitive Loop, and record outcomes."""
    try:
        event_dict = json.loads(payload_str)
        if "payload" in event_dict and isinstance(event_dict["payload"], str):
            event_dict = json.loads(event_dict["payload"])

        event = EventSchema(**event_dict)

        logger.info(
            f"Consuming event [stream_id={event_id}] | type='{event.type}' | actor='{event.actor.id}' | site='{event.site_id}'"
        )

        async with AsyncSessionLocal() as db_session:
            result = await orchestrator.run_cognitive_loop(event=event, db_session=db_session)
            logger.info(
                f"Cognitive Loop complete [loop_id={result['loop_id']}] | agent='{result['agent_id']}' | decision='{result['decision']}' | actions_executed={result['executed_actions']}"
            )
            return result

    except json.JSONDecodeError as err:
        logger.error(f"Malformed event JSON [stream_id={event_id}]: {err}")
        return None
    except Exception as exc:
        logger.error(f"Error processing event through cognitive loop [stream_id={event_id}]: {exc}", exc_info=True)
        return None


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
                from sqlalchemy import select, and_
                # Auto-expire overdue approvals
                stmt = select(ApprovalQueueModel).where(
                    and_(
                        ApprovalQueueModel.status == "pending",
                        ApprovalQueueModel.expires_at <= datetime.utcnow()
                    )
                )
                res = await db.execute(stmt)
                expired_items = res.scalars().all()
                for item in expired_items:
                    item.status = "expired"
                    item.decision_reason = "Auto-rejected by platform safe-default policy upon 24h expiry."
                    item.decided_at = datetime.utcnow()
                    logger.info(f"Auto-expired pending approval item: {item.id}")
                if expired_items:
                    await db.commit()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning(f"Scheduled maintenance task warning: {exc}")


async def run_worker() -> None:
    logger.info(f"Connecting CORTEX autonomous worker to Redis stream at {REDIS_URL}...")
    redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await init_stream_group(redis_client)

    tool_bus = build_default_tool_bus(redis_client=redis_client)
    orchestrator = Orchestrator(tool_bus=tool_bus)

    # Launch background maintenance scheduler
    maintenance_task = asyncio.create_task(run_scheduled_maintenance_tasks())

    logger.info(f"CORTEX autonomous worker listening on '{STREAM_NAME}' as '{CONSUMER_NAME}'...")

    try:
        while True:
            try:
                response = await redis_client.xreadgroup(
                    groupname=CONSUMER_GROUP,
                    consumername=CONSUMER_NAME,
                    streams={STREAM_NAME: ">"},
                    count=10,
                    block=2000
                )

                if response:
                    for stream, messages in response:
                        for message_id, fields in messages:
                            payload_str = fields.get("payload", "{}")
                            await process_event(message_id, payload_str, orchestrator)
                            await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                            logger.debug(f"Acknowledged event {message_id}")
                else:
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Worker read loop warning: {exc}")
                await asyncio.sleep(2)

    except asyncio.CancelledError:
        logger.info("Worker received termination signal.")
    finally:
        maintenance_task.cancel()
        await redis_client.close()
        logger.info("Worker stopped and Redis connection closed.")


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped via KeyboardInterrupt.")
