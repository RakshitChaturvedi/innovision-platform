# detects camera that stop publishing heartbeats.
from __future__ import annotations

import asyncio
import logging
import redis.asyncio as aioredis

from services.ingestion.src.config import settings

logger = logging.getLogger(__name__)

class OfflineMonitor:
    # centralized monitor for all ingestion cams
    def __init__(self, redis_client: aioredis.Redis, registry_client) -> None:
        self._redis = redis_client
        self._registry_client = registry_client

        self._last_heartbeat: dict[str, float] = {}
        self._offline_cameras: set[str] = set()

    async def run(self) -> None:
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("heartbeat:ingestion:*")

        logger.info("offline_monitor_started")

        heartbeat_task = asyncio.create_task(self._consume_heartbeats(pubsub))

        try:
            while True:
                await asyncio.sleep(2)
                await self._check_timeouts()
        except asyncio.CancelledError:
            logger.info("offline_monitor_stopping")
            raise
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            await pubsub.punsubscribe("heartbeat:ingestion:*")
            await pubsub.aclose()

            logger.info("offline_monitor_stopped")

    async def _consume_heartbeats(self, pubsub) -> None:
        try:
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode()

                camera_id = channel.rsplit(":", 1)[-1]

                is_first_heartbeat = camera_id not in self._last_heartbeat

                self._last_heartbeat[camera_id] = (
                    asyncio.get_running_loop().time()
                )

                if is_first_heartbeat:
                    logger.info(
                        "camera_online_initial camera_id=%s",
                        camera_id,
                    )

                    try:
                        await self._registry_client.update_status(
                            camera_id,
                            "online",
                        )
                    except Exception as exc:
                        logger.error(
                            "camera_initial_online_status_update_failed "
                            "camera_id=%s error=%s",
                            camera_id,
                            exc,
                        )

                elif camera_id in self._offline_cameras:
                    self._offline_cameras.remove(camera_id)

                    logger.info(
                        "camera_back_online camera_id=%s",
                        camera_id,
                    )

                    try:
                        await self._registry_client.update_status(
                            camera_id,
                            "online",
                        )
                    except Exception as exc:
                        logger.error(
                            "camera_online_status_update_failed "
                            "camera_id=%s error=%s",
                            camera_id,
                            exc,
                        )

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            logger.error(
                "heartbeat_consumer_failed error=%s",
                exc,
            )
            raise

    async def _check_timeouts(self) -> None:
        # check every known cam for heartbeat timeout
        now = asyncio.get_running_loop().time()

        for camera_id, last_heartbeat in list(self._last_heartbeat.items()):
            elapsed = now - last_heartbeat
            if elapsed <= settings.camera_offline_timeout_s:
                continue
            if camera_id in self._offline_cameras:
                continue

            logger.warning("camera_offline_detected camera_id=%s elapsed=%.1fs", camera_id, elapsed)
            self._offline_cameras.add(camera_id)

            try:
                await self._registry_client.update_status(camera_id, "offline",)
            except Exception as exc:
                logger.error( "camera_offline_status_update_failed camera_id=%s error=%s", camera_id, exc,)
            try:
                await self._redis.publish(f"camera:offline:{camera_id}",camera_id,)
            except Exception as exc:
                logger.error("camera_offline_event_publish_failed camera_id=%s error=%s",
                    camera_id, exc)

