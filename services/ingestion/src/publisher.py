"""
Publisher — constructs strictly-typed ``FrameEvent`` Pydantic models and
publishes them to Redis streams ``frames:{camera_id}`` with MAXLEN 1000.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis

from shared.contracts.enums import FrameProvider
from shared.contracts.frame_event import FrameEvent
from services.ingestion.src.config import settings

logger = logging.getLogger(__name__)


class FramePublisher:
    """
    Serialises ``FrameEvent`` instances and writes them to per-camera
    Redis streams.

    Streams are created implicitly on the first ``XADD`` call — no
    manual initialisation required.
    """

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def publish(
        self, camera_id: str, frame_seq: int, frame_reference: str, frame_shape: tuple[int, int]
    ) -> str:
        """
        Build a ``FrameEvent``, serialise it, and XADD to the stream.
        """
        event = FrameEvent(
            camera_id=camera_id,
            frame_seq=frame_seq,
            timestamp=datetime.now(timezone.utc),
            frame_provider=FrameProvider.REDIS,
            frame_reference=frame_reference,
            frame_shape=frame_shape,
        )

        stream_key = f"frames:{camera_id}"
        payload = event.model_dump_json()

        msg_id = await self._redis.xadd(
            stream_key,
            {"data": payload},
            maxlen=settings.stream_maxlen,
            approximate=True,
        )

        logger.debug(
            "frame_published camera_id=%s seq=%d stream=%s msg_id=%s",
            camera_id,
            frame_seq,
            stream_key,
            msg_id,
        )
        return msg_id