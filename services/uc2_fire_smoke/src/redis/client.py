"""
Async Redis Connection Manager and Pool for UC2 Service.
"""
from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as aioredis

from services.uc2_fire_smoke.src.config import settings

logger = logging.getLogger("innovision.uc2.redis.client")


class RedisClientManager:
    """
    Manages shared async Redis client and connection pool.
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        self.host = host or settings.redis_host
        self.port = port or settings.redis_port
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> aioredis.Redis:
        """Establish Redis connection if not already open."""
        if self._redis is None:
            self._redis = aioredis.Redis(
                host=self.host,
                port=self.port,
                decode_responses=False,  # Binary mode for raw JPEG caches
                max_connections=50,
            )
            try:
                await self._redis.ping()
                logger.info(f"Connected to Redis at {self.host}:{self.port}")
            except Exception as exc:
                logger.error(f"Failed to ping Redis at {self.host}:{self.port}: {exc}")
                raise
        return self._redis

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
            logger.info("Closed Redis connection pool")

    @property
    def client(self) -> aioredis.Redis:
        if self._redis is None:
            raise RuntimeError("Redis client is not connected. Call connect() first.")
        return self._redis
