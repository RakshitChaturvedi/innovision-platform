# UC use this to publish AlertEvents

import asyncio
from collections import deque
import logging
import random
import time
from typing import Any, Dict
from uuid import UUID
import redis.asyncio as aioredis
from shared.contracts.alert_event import AlertEvent

logger = logging.getLogger(__name__)

ALERTS_LIVE_STREAM = "alerts:live"
ALERTS_DEAD_LETTER = "alerts:dead_letter"


class AlertPublisher:
    """
    Resilient AlertPublisher for UC1-UC4.
    Guarantees:
    - Bounded retries with exponential backoff and jitter for transient Redis disconnections.
    - Non-blocking in-memory buffering when Redis is temporarily offline.
    - Automatic draining of buffered alerts on reconnection.
    - Dead-letter routing for malformed payloads.
    - Observable metrics and structured logs.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        stream_name: str = ALERTS_LIVE_STREAM,
        dead_letter_stream: str = ALERTS_DEAD_LETTER,
        max_retries: int = 3,
        base_delay_s: float = 0.05,
        max_delay_s: float = 0.5,
        buffer_capacity: int = 1000,
    ):
        self._redis = redis_client
        self._stream = stream_name
        self._dead_letter_stream = dead_letter_stream
        self._max_retries = max_retries
        self._base_delay_s = base_delay_s
        self._max_delay_s = max_delay_s
        self._buffer: deque[AlertEvent] = deque(maxlen=buffer_capacity)
        self._metrics = {
            "published": 0,
            "retried": 0,
            "failed": 0,
            "buffered": 0,
            "dead_lettered": 0,
            "buffer_flushed": 0,
        }

    @property
    def metrics(self) -> Dict[str, int]:
        return dict(self._metrics)

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    async def flush_buffer(self) -> int:
        """Attempts to drain buffered alerts into Redis stream once connected."""
        if not self._buffer:
            return 0

        flushed = 0
        while self._buffer:
            alert = self._buffer[0]
            try:
                payload = alert.model_dump_json()
                await self._redis.xadd(self._stream, {"data": payload})
                self._buffer.popleft()
                flushed += 1
                self._metrics["published"] += 1
                self._metrics["buffer_flushed"] += 1
            except Exception as e:
                logger.warning("buffer_flush_interrupted error=%s remaining=%d", e, len(self._buffer))
                break

        if flushed > 0:
            logger.info("alert_buffer_flushed count=%d remaining=%d", flushed, len(self._buffer))
        return flushed

    async def publish(self, alert: AlertEvent) -> bool:
        """
        Publishes AlertEvent with bounded retries and exponential backoff.
        Buffers in memory if Redis is temporarily unreachable.
        """
        # 1. First drain any previously buffered events if Redis is up
        if self._buffer:
            try:
                await self.flush_buffer()
            except Exception:
                pass

        # 2. Serialize and validate payload
        try:
            payload = alert.model_dump_json()
            AlertEvent.model_validate_json(payload)
        except Exception as e:
            logger.error("alert_serialization_poison alert_id=%s error=%s", alert.alert_id, e)
            self._metrics["dead_lettered"] += 1
            await self._send_to_dead_letter(
                error=f"serialization_failure: {e}",
                alert_id=str(alert.alert_id),
                source_uc=alert.source_uc.value,
                raw=str(alert),
            )
            return False

        # 3. Publish with bounded retries and exponential backoff + jitter
        for attempt in range(1, self._max_retries + 1):
            try:
                t0 = time.monotonic()
                await self._redis.xadd(self._stream, {"data": payload})
                elapsed_ms = (time.monotonic() - t0) * 1000.0

                self._metrics["published"] += 1
                logger.info(
                    "alert_published alert_id=%s uc=%s type=%s severity=%s attempt=%d latency_ms=%.1f",
                    alert.alert_id,
                    alert.source_uc.value,
                    alert.alert_type,
                    alert.severity.value,
                    attempt,
                    elapsed_ms,
                )
                return True

            except Exception as e:
                self._metrics["retried"] += 1
                logger.warning(
                    "alert_publish_retry alert_id=%s attempt=%d/%d error=%s",
                    alert.alert_id,
                    attempt,
                    self._max_retries,
                    e,
                )
                if attempt < self._max_retries:
                    # Exponential backoff with jitter
                    backoff = min(
                        self._max_delay_s,
                        self._base_delay_s * (2 ** (attempt - 1)) + random.uniform(0.01, 0.05),
                    )
                    await asyncio.sleep(backoff)
                else:
                    # Final failure after exhausting retries: buffer in memory to avoid silent loss
                    self._metrics["failed"] += 1
                    self._metrics["buffered"] += 1
                    self._buffer.append(alert)
                    logger.error(
                        "alert_publish_exhausted_buffered alert_id=%s buffer_len=%d",
                        alert.alert_id,
                        len(self._buffer),
                    )
                    return False

        return False

    async def _send_to_dead_letter(self, error: str, alert_id: str, source_uc: str, raw: str) -> None:
        try:
            await self._redis.xadd(
                self._dead_letter_stream,
                {
                    "error": error,
                    "alert_id": alert_id,
                    "source_uc": source_uc,
                    "raw": raw,
                },
            )
        except Exception as e:
            logger.error("dead_letter_write_failed error=%s", e)