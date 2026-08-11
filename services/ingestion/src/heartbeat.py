"""
Heartbeat — publishes a periodic liveness signal for each camera to the Redis Pub/Sub channel ``heartbeat:ingestion:{camera_id}``.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

async def heartbeat_loop(
    redis_client: aioredis.Redis,
    camera_id: UUID,
    interval_s: float = 5.0,
) -> None:
    """
    Publish a heartbeat every interval_s seconds.
    Runs as a sibling asyncio task alongside the camera ingestion worker. 
    Cancellation is the normal shutdown mechanism.
    """
    channel = f"heartbeat:ingestion:{camera_id}"
    logger.info("heartbeat_started camera_id=%s channel=%s interval=%.1fs", camera_id, channel, interval_s)

    while True:
        payload = json.dumps(
            {
                "camera_id": str(camera_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "online",
            }
        )
        try:
            await redis_client.publish(channel, payload)
        except Exception as exc:
            logger.error("heartbeat_publish_failed camera_id=%s error=%s", camera_id, exc)
        await asyncio.sleep(interval_s)
