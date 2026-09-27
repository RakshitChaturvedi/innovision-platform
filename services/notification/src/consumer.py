"""
Consumes notifications:live (published only by alert_management's
escalation.py) and resolves + notifies the correct recipients.
"""
import asyncio
import logging
import redis.asyncio as aioredis
from sqlalchemy import text
from shared.platform_client.db import get_session_factory
from .config import settings
from .email import send_escalation_email
from .logger import log_delivery

logger = logging.getLogger(__name__)
_session_factory = get_session_factory(settings.database_url)


class NotificationConsumer:

    def __init__(self):
        self._redis: aioredis.Redis | None = None

    async def start(self) -> None:
        self._redis = await aioredis.from_url(
            f"redis://{settings.redis_host}:{settings.redis_port}"
        )
        try:
            await self._redis.xgroup_create(
                settings.notifications_stream, settings.consumer_group,
                id="0", mkstream=True,
            )
        except Exception:
            pass

        logger.info("notification_consumer_started")

        while True:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=settings.consumer_group,
                    consumername=settings.consumer_name,
                    streams={settings.notifications_stream: ">"},
                    count=10,
                    block=1000,
                )
                if not messages:
                    continue
                for stream, entries in messages:
                    for msg_id, data in entries:
                        await self._process(msg_id, data)
            except Exception as e:
                logger.error("notification_consumer_loop_error error=%s", e)
                await asyncio.sleep(1)

    async def _process(self, msg_id: str, data: dict) -> None:
        def _get(key):
            v = data.get(key.encode()) or data.get(key)
            return v.decode() if isinstance(v, bytes) else v

        alert_row_id = _get("alert_id")
        camera_id = _get("camera_id")
        level = int(_get("level") or 1)

        try:
            async with _session_factory() as session:
                async with session.begin():
                    alert_row = (await session.execute(text("""
                        SELECT title, description FROM alerts WHERE id = :id
                    """), {"id": alert_row_id})).fetchone()

                    camera_row = (await session.execute(text("""
                        SELECT name FROM cameras WHERE id = :id
                    """), {"id": camera_id})).fetchone()

                    if not alert_row or not camera_row:
                        logger.warning("notification_missing_alert_or_camera id=%s", alert_row_id)
                        await self._ack(msg_id)
                        return

                    role = settings.escalation_role_map.get(min(level, 3), "superadmin")
                    recipients = await session.execute(text("""
                        SELECT id, email FROM users
                        WHERE role = :role AND :camera_id = ANY(camera_ids)
                    """), {"role": role, "camera_id": camera_id})
                    recipient_rows = recipients.fetchall()

                    for r in recipient_rows:
                        success = send_escalation_email(
                            r.email, alert_row.title, alert_row.description,
                            camera_row.name, level,
                        )
                        await log_delivery(
                            session, alert_row_id, str(r.id), "email", success,
                        )

                logger.info(
                    "notification_processed alert_id=%s level=%d recipients=%d",
                    alert_row_id, level, len(recipient_rows),
                )
        except Exception as e:
            logger.error("notification_process_failed alert_id=%s error=%s",
                         alert_row_id, e)
            return  # do not ack — retry on redelivery

        await self._ack(msg_id)

    async def _ack(self, msg_id: str) -> None:
        await self._redis.xack(
            settings.notifications_stream, settings.consumer_group, msg_id
        )