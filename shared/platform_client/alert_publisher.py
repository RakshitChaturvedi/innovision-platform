# UC use this to publish AlertEvents

import logging
from uuid import UUID
import redis.asyncio as aioredis
from shared.contracts.alert_event import AlertEvent

logger = logging.getLogger(__name__)

ALERTS_LIVE_STREAM = "alerts:live"
ALERTS_DEAD_LETTER = "alerts:dead_letter"

class AlertPublisher:
    def __init__(self, redis_client: aioredis.Redis):
        self._redis = redis_client

    async def publish(self, alert: AlertEvent) -> bool:
        try:
            payload = alert.model_dump_json()
            AlertEvent.model_validate_json(payload)

            await self._redis.xadd(ALERTS_LIVE_STREAM, {"data": payload})
            logger.info(
                "alert_published alert_id=%s uc=%s type=%s severity=%s",
                alert.alert_id, alert.source_uc.value, alert.alert_type, alert.severity.value
            )
            return True
        except Exception as e:
            logger.error("alert_publish_failed alert_id=%s error=%s", alert.alert_id, e,)
            try:
                await self._redis.xadd(
                    ALERTS_DEAD_LETTER,
                    {
                        "error": str(e),
                        "alert_id": str(alert.alert_id),
                        "source_uc": alert.source_uc.value,
                        "raw": alert.model_dump_json(),
                    }
                )
            except Exception:
                pass
            return False