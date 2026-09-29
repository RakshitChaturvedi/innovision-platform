"""
Redis Stream Frame Consumer for Per-Camera FrameEvents.

Reads FrameEvent JSON from `frames:{camera_id}`, retrieves the cached or stored JPEG,
and passes it to the detection pipeline.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional, Tuple

import cv2
import numpy as np
import redis.asyncio as aioredis
from pydantic import ValidationError

from shared.contracts.enums import FrameProvider
from shared.contracts.frame_event import FrameEvent
from services.uc2_fire_smoke.src.config import settings
from services.uc2_fire_smoke.src.storage.minio_client import MinIOClient

logger = logging.getLogger("innovision.uc2.redis.frame_consumer")


class RedisFrameConsumer:
    """
    Consumes FrameEvents from `frames:{camera_id}` Redis Stream using consumer groups.
    Fetches raw image bytes from Redis hot cache (`frame:{camera_id}:{seq}`) or MinIO cold store.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        camera_id: str,
        group_name: Optional[str] = None,
        consumer_name: Optional[str] = None,
        minio_client: Optional[MinIOClient] = None,
    ) -> None:
        self.redis = redis_client
        self.camera_id = camera_id
        self.stream_key = f"frames:{camera_id}"
        self.group_name = group_name or settings.stream_consumer_group
        self.consumer_name = consumer_name or f"worker_{camera_id}"
        self.minio = minio_client or MinIOClient()
        self._group_created = False

    async def ensure_consumer_group(self) -> None:
        """Create consumer group on stream if not exists (MKSTREAM)."""
        if self._group_created:
            return
        try:
            await self.redis.xgroup_create(
                name=self.stream_key,
                groupname=self.group_name,
                id="$",
                mkstream=True,
            )
            self._group_created = True
            logger.info(f"Created consumer group '{self.group_name}' on '{self.stream_key}'")
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" in str(exc):
                self._group_created = True
            else:
                logger.error(f"Failed to create consumer group on '{self.stream_key}': {exc}")

    async def fetch_frame_image(self, event: FrameEvent) -> Optional[np.ndarray]:
        """
        Fetch frame image ndarray using hot cache (Redis) or cold storage (MinIO fallback).
        """
        # 1. Hot path: Redis cache
        if event.frame_provider == FrameProvider.REDIS or event.frame_reference.startswith("frame:"):
            try:
                cache_key = event.frame_reference
                raw_bytes = await self.redis.get(cache_key)
                if raw_bytes is not None and len(raw_bytes) > 0:
                    np_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    if frame is not None:
                        return frame
            except Exception as exc:
                logger.debug(f"Hot cache miss/error for {event.frame_reference}: {exc}")

        # 2. Cold path: MinIO fallback
        if self.minio:
            object_key = (
                event.frame_reference
                if event.frame_reference.startswith("frames/")
                else f"frames/{event.camera_id}/{event.frame_seq:08d}.jpg"
            )
            try:
                frame = await self.minio.get_frame(object_key)
                if frame is not None:
                    return frame
            except Exception as exc:
                logger.error(f"Cold storage fetch failed for {object_key}: {exc}")

        return None

    async def read_frames(
        self,
        batch_size: int = 1,
        block_ms: int = 1000,
    ) -> AsyncGenerator[Tuple[str, FrameEvent, Optional[np.ndarray]], None]:
        """
        Generator yielding (message_id, FrameEvent, frame_bgr_image).
        """
        await self.ensure_consumer_group()

        try:
            entries = await self.redis.xreadgroup(
                groupname=self.group_name,
                consumername=self.consumer_name,
                streams={self.stream_key: ">"},
                count=batch_size,
                block=block_ms,
            )

            if not entries:
                return

            for stream, messages in entries:
                for msg_id, fields in messages:
                    # fields is dict of bytes -> bytes or str -> str
                    raw_data = fields.get(b"data") or fields.get("data")
                    if not raw_data:
                        # ACK invalid message
                        await self.ack(msg_id)
                        continue

                    try:
                        if isinstance(raw_data, bytes):
                            raw_data = raw_data.decode("utf-8")
                        event_dict = json.loads(raw_data)
                        frame_event = FrameEvent(**event_dict)
                    except (json.JSONDecodeError, ValidationError) as err:
                        logger.warning(f"Corrupt FrameEvent in {self.stream_key} [{msg_id}]: {err}")
                        await self.ack(msg_id)
                        continue

                    # Load actual image
                    frame_img = await self.fetch_frame_image(frame_event)
                    yield (
                        msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id),
                        frame_event,
                        frame_img,
                    )

        except Exception as exc:
            logger.error(f"Error reading frames from {self.stream_key}: {exc}")

    async def ack(self, msg_id: str) -> None:
        """Acknowledge message processing in Redis stream."""
        try:
            await self.redis.xack(self.stream_key, self.group_name, msg_id)
        except Exception as exc:
            logger.warning(f"Failed to XACK message {msg_id} on {self.stream_key}: {exc}")
