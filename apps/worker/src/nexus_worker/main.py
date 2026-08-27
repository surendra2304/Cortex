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


async def process_event(event_id: str, payload_str: str) -> None:
    """Process, decode, and acknowledge an incoming stream event."""
    try:
        event_data = json.loads(payload_str)
        evt_type = event_data.get("type", "unknown")
        tenant_id = event_data.get("tenant_id", "unknown")
        site_id = event_data.get("site_id", "unknown")
        logger.info(
            f"Successfully consumed event [stream_id={event_id}] | type='{evt_type}' | tenant='{tenant_id}' | site='{site_id}'"
        )
    except json.JSONDecodeError as err:
        logger.error(f"Malformed event JSON [stream_id={event_id}]: {err}")
    except Exception as exc:
        logger.error(f"Error processing event [stream_id={event_id}]: {exc}")


async def run_worker() -> None:
    logger.info(f"Connecting NEXUS worker to Redis stream at {REDIS_URL}...")
    redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    await init_stream_group(redis_client)

    logger.info(f"NEXUS background worker listening on '{STREAM_NAME}' as '{CONSUMER_NAME}'...")

    try:
        while True:
            try:
                # Read new messages from stream group with a 2-second block timeout
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
                            await process_event(message_id, payload_str)
                            # Acknowledge processed message in Redis Stream
                            await redis_client.xack(STREAM_NAME, CONSUMER_GROUP, message_id)
                            logger.debug(f"Acknowledged event {message_id}")
                else:
                    # Heartbeat idle wait
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Redis Stream read loop warning: {exc}")
                await asyncio.sleep(2)

    except asyncio.CancelledError:
        logger.info("Worker received termination signal.")
    finally:
        await redis_client.close()
        logger.info("Worker gracefully stopped and Redis connection closed.")


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker stopped via KeyboardInterrupt.")
