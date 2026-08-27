import asyncio
import json
import logging
import os
import sys
import redis.asyncio as aioredis
from typing import Optional

# Setup package paths
sys.path.insert(0, os.path.abspath("packages/core/src"))
sys.path.insert(0, os.path.abspath("packages/event_schema/src"))
sys.path.insert(0, os.path.abspath("packages/agents/src"))
sys.path.insert(0, os.path.abspath("packages/ai_universe_adapter/src"))
sys.path.insert(0, os.path.abspath("packages/tool_runtime/src"))
sys.path.insert(0, os.path.abspath("packages/integrations/src"))
sys.path.insert(0, os.path.abspath("packages/policy_engine/src"))
sys.path.insert(0, os.path.abspath("packages/workflow_engine/src"))
sys.path.insert(0, os.path.abspath("apps/api/src"))

from nexus_event_schema import EventSchema
from nexus_core.orchestrator import Orchestrator, build_default_tool_bus
from nexus_api.config import AsyncSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("nexus-worker")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STREAM_NAME = os.getenv("REDIS_EVENT_STREAM", "nexus:events:stream")
CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "nexus-worker-group")
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
        # Handle cases where payload might be wrapped
        if "payload" in event_dict and isinstance(event_dict["payload"], str):
            event_dict = json.loads(event_dict["payload"])

        # Parse into typed EventSchema
        event = EventSchema(**event_dict)

        logger.info(
            f"Consuming event [stream_id={event_id}] | type='{event.type}' | actor='{event.actor.id}' | site='{event.site_id}'"
        )

        # Open async DB session for contextualization and audit recording
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


async def run_worker() -> None:
    logger.info(f"Connecting NEXUS autonomous worker to Redis stream at {REDIS_URL}...")
    redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await init_stream_group(redis_client)

    # Initialize tool bus and orchestrator
    tool_bus = build_default_tool_bus(redis_client=redis_client)
    orchestrator = Orchestrator(tool_bus=tool_bus)

    logger.info(f"NEXUS autonomous worker listening on '{STREAM_NAME}' as '{CONSUMER_NAME}'...")

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
                            # Acknowledge processed message in Redis Stream
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
        await redis_client.close()
        logger.info("Worker stopped and Redis connection closed.")


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped via KeyboardInterrupt.")
