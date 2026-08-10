"""
Publisher — constructs strictly-typed ``FrameEvent`` Pydantic models and
publishes them to Redis streams ``frames:{camera_id}`` with MAXLEN 1000.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

import redis.asyncio as aioredis

from shared.contracts.enums import FrameProvider
from shared.contracts.frame_event import FrameEvent

logger = logging.getLogger(__name__)


class FramePublisher:
    """
    Serialises ``FrameEvent`` instances and writes them to per-camera
    Redis streams.

    Streams are created implicitly on the first ``XADD`` call — no
    manual initialisation required.
    """

    def __init__(self, redis_client: aioredis.Redis, maxlen: int = 1000) -> None:
        self._redis = redis_client
        self._maxlen = maxlen

    async def publish(
        self,
        camera_id: UUID,
        frame_seq: int,
        frame_reference: str,
        frame_shape: tuple[int, int],
    ) -> str:
        """
        Build a ``FrameEvent``, serialise it, and XADD to the stream.

        Returns the Redis message ID.
        """
        event = FrameEvent(
            camera_id=camera_id,
            frame_seq=frame_seq,
            timestamp=datetime.now(timezone.utc),
            frame_provider=FrameProvider.MINIO,
            frame_reference=frame_reference,
            frame_shape=frame_shape,
        )

        stream_key = f"frames:{camera_id}"
        payload = event.model_dump_json()

        msg_id = await self._redis.xadd(
            stream_key,
            {"data": payload},
            maxlen=self._maxlen,
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
