from __future__ import annotations

import logging
import redis.asyncio as aioredis
from services.ingestion.src.config import settings

logger = logging.getLogger(__name__)

class FrameCache:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    @staticmethod
    def _key(camera_id: str, frame_seq: int) -> str:
        return f"frame:{camera_id}:{frame_seq}"

    async def put(self, camera_id: str, frame_seq: int, jpeg_bytes: bytes) -> None:
        key = self._key(camera_id, frame_seq)
        await self._redis.set(key, jpeg_bytes, ex=settings.frame_cache_ttl_s)
        logger.debug("frame_cached camera_id=%s seq=%d ttl=%ss", camera_id, frame_seq, settings.frame_cache_ttl_s)

    async def get(self, camera_id: str, frame_seq:int) -> bytes | None:
        key = self._key(camera_id, frame_seq)
        data = await self._redis.get(key)
        if data is None:
            logger.debug("frame_cache_miss camera_id=%s seq=%d", camera_id, frame_seq)
            return None
        return data

    async def delete(self, camera_id: str, frame_seq: int) -> None:
        await self._redis.delete(self._key(camera_id, frame_seq))