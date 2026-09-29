"""
Redis PubSub Listener for Camera Lifecycle Events.

Listens for:
- `camera:added:*`
- `camera:updated:*`
- `camera:removed:*`
- `camera:offline:*`

Notifies the PipelineManager to spin up, update, or terminate per-camera workers.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Coroutine, Optional

import redis.asyncio as aioredis

logger = logging.getLogger("innovision.uc2.redis.pubsub")


class CameraPubSubListener:
    """
    Subscribes to camera lifecycle channel patterns in Redis PubSub.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        on_camera_added: Optional[Callable[[str], Coroutine]] = None,
        on_camera_updated: Optional[Callable[[str], Coroutine]] = None,
        on_camera_removed: Optional[Callable[[str], Coroutine]] = None,
    ) -> None:
        self.redis = redis_client
        self.on_camera_added = on_camera_added
        self.on_camera_updated = on_camera_updated
        self.on_camera_removed = on_camera_removed
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start pubsub listener background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen_loop())
        logger.info("Camera PubSub listener started")

    async def stop(self) -> None:
        """Stop pubsub listener."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Camera PubSub listener stopped")

    async def _listen_loop(self) -> None:
        pubsub = self.redis.pubsub()
        patterns = ["camera:added:*", "camera:updated:*", "camera:removed:*", "camera:offline:*"]
        await pubsub.psubscribe(*patterns)
        logger.info(f"Subscribed to PubSub patterns: {patterns}")

        try:
            while self._running:
                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message is None:
                        await asyncio.sleep(0.1)
                        continue

                    channel = message.get("channel")
                    if isinstance(channel, bytes):
                        channel = channel.decode("utf-8")

                    parts = channel.split(":")
                    if len(parts) >= 3:
                        action = parts[1]  # added, updated, removed, offline
                        camera_id = parts[2]

                        logger.info(f"Received camera lifecycle event: action={action}, camera_id={camera_id}")

                        if action == "added" and self.on_camera_added:
                            await self.on_camera_added(camera_id)
                        elif action == "updated" and self.on_camera_updated:
                            await self.on_camera_updated(camera_id)
                        elif action in ("removed", "offline") and self.on_camera_removed:
                            await self.on_camera_removed(camera_id)

                except asyncio.CancelledError:
                    break
                except Exception as exc:
                    logger.error(f"Error in PubSub listen loop: {exc}")
                    await asyncio.sleep(1.0)
        finally:
            await pubsub.punsubscribe(*patterns)
            await pubsub.aclose()
