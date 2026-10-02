"""
Alert consumer — reads alerts:live via Redis Streams consumer group.

Reliability guarantees:
- Known-camera set refreshed every 60 s and on camera:added/updated pub/sub events.
- Duplicate alert_ids are ACKed immediately (ON CONFLICT DO NOTHING path).
- Persistence failures leave the message pending; a background XAUTOCLAIM task
  re-delivers messages idle >60 s.  After MAX_DELIVERY_COUNT failed deliveries
  the message is moved to alerts:dead_letter and ACKed.
"""
import json
import asyncio
import logging
import uuid

import redis.asyncio as aioredis
from sqlalchemy import text

from shared.contracts.alert_event import AlertEvent
from shared.platform_client.db import get_session_factory
from .config import settings
from .validator import validate_alert
from .persistence import insert_alert, fetch_alert_by_alert_id
from .incident_trigger import maybe_create_incident
from .websocket import push_alert
from .escalation import escalation_check
from services.audit.src.writer import write_audit_entry

logger = logging.getLogger(__name__)
_session_factory = get_session_factory(settings.database_url)

# Messages idle longer than this are reclaimed and retried.
_AUTOCLAIM_IDLE_MS = 60_000
# After this many delivery attempts the message is dead-lettered.
_MAX_DELIVERY_COUNT = 5
# How often the autoclaim sweep runs (seconds).
_AUTOCLAIM_INTERVAL_S = 30
# How often the known-camera set is refreshed (seconds).
_CAMERA_REFRESH_INTERVAL_S = 60


class AlertConsumer:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._known_cameras: set = set()

    # ------------------------------------------------------------------
    # Camera set management
    # ------------------------------------------------------------------

    async def _load_known_cameras(self) -> None:
        try:
            async with _session_factory() as session:
                rows = await session.execute(text("SELECT id FROM cameras"))
                self._known_cameras = {r.id for r in rows.fetchall()}
            logger.info("known_cameras_refreshed count=%d", len(self._known_cameras))
        except Exception as exc:
            logger.error("known_cameras_refresh_failed error=%s", exc)

    async def _camera_refresh_loop(self) -> None:
        """Refresh the camera set on a timer."""
        while True:
            await asyncio.sleep(_CAMERA_REFRESH_INTERVAL_S)
            await self._load_known_cameras()

    async def _camera_pubsub_loop(self) -> None:
        """Refresh the camera set when camera:added/* or camera:updated/* arrives."""
        pubsub = self._redis.pubsub()
        await pubsub.psubscribe("camera:added:*", "camera:updated:*")
        try:
            async for message in pubsub.listen():
                if message["type"] in ("pmessage", "message"):
                    logger.info("camera_change_detected channel=%s — refreshing", message.get("channel"))
                    await self._load_known_cameras()
        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    # ------------------------------------------------------------------
    # Dead-letter helper
    # ------------------------------------------------------------------

    async def _to_dead_letter(self, error: str, raw: str) -> None:
        await self._redis.xadd(
            settings.dead_letter_stream, {"error": error, "raw": raw}
        )

    async def _ack(self, msg_id: str) -> None:
        await self._redis.xack(
            settings.alerts_stream, settings.consumer_group, msg_id
        )

    # ------------------------------------------------------------------
    # Core message processing
    # ------------------------------------------------------------------

    async def _process(self, msg_id: str, data: dict) -> None:
        raw = data.get(b"data") or data.get("data")
        if isinstance(raw, bytes):
            raw = raw.decode()

        # 1. Schema validation — invalid → dead letter + ACK
        try:
            alert = AlertEvent.model_validate_json(raw)
        except Exception as exc:
            logger.error("alert_schema_invalid msg_id=%s error=%s", msg_id, exc)
            await self._to_dead_letter(str(exc), raw)
            await self._ack(msg_id)
            return

        # 2. Platform validation (unknown camera, etc.) → dead letter + ACK
        errors = validate_alert(alert, self._known_cameras)
        if errors:
            logger.warning(
                "alert_validation_failed alert_id=%s errors=%s", alert.alert_id, errors
            )
            await self._to_dead_letter(str(errors), raw)
            await self._ack(msg_id)
            return

        row_id = str(uuid.uuid4())
        try:
            async with _session_factory() as session:
                async with session.begin():
                    inserted = await insert_alert(session, row_id, alert)
                    if not inserted:
                        # Duplicate alert_id — ACK so it doesn't sit in the PEL forever
                        logger.info(
                            "alert_duplicate_acked alert_id=%s msg_id=%s",
                            alert.alert_id, msg_id,
                        )
                        await self._ack(msg_id)
                        return

                    incident_id = await maybe_create_incident(
                        session, row_id, alert.title, alert.severity.value
                    )
                    await write_audit_entry(
                        _session_factory,
                        service="alert_management",
                        action="alert_created",
                        entity_type="alert",
                        entity_id=row_id,
                        source_uc=alert.source_uc.value,
                        metadata=json.dumps({
                            "alert_type": alert.alert_type,
                            "severity": alert.severity.value,
                        }),
                        session=session,
                    )
                    alert_row = await fetch_alert_by_alert_id(
                        session, str(alert.alert_id)
                    )
        except Exception as exc:
            # Persistence failed — leave message pending; autoclaim will retry it.
            logger.error(
                "alert_persist_failed alert_id=%s msg_id=%s error=%s",
                alert.alert_id, msg_id, exc,
            )
            return

        # 3. Push to connected operators (non-fatal)
        try:
            await push_alert(alert_row)
        except Exception as exc:
            logger.error(
                "socket_push_failed alert_id=%s error=%s", alert.alert_id, exc
            )

        # 4. Schedule escalation for severe alerts
        if alert.severity.value in ("high", "critical"):
            escalation_check.apply_async(
                args=[row_id, 1], countdown=settings.escalation_level_1_delay_s
            )

        logger.info(
            "alert_processed alert_id=%s uc=%s severity=%s incident=%s",
            alert.alert_id, alert.source_uc.value, alert.severity.value, incident_id,
        )
        await self._ack(msg_id)

    # ------------------------------------------------------------------
    # XAUTOCLAIM retry sweep
    # ------------------------------------------------------------------

    async def _autoclaim_loop(self) -> None:
        """
        Periodically reclaim messages that have been idle in the PEL.
        After MAX_DELIVERY_COUNT attempts, move to dead letter and ACK.
        """
        while True:
            await asyncio.sleep(_AUTOCLAIM_INTERVAL_S)
            try:
                result = await self._redis.xautoclaim(
                    settings.alerts_stream,
                    settings.consumer_group,
                    settings.consumer_name,
                    min_idle_time=_AUTOCLAIM_IDLE_MS,
                    start_id="0-0",
                    count=50,
                )
                # result: (next_id, [[msg_id, data], ...], [deleted_ids])
                claimed = result[1] if isinstance(result, (list, tuple)) else []
                for msg_id, data in claimed:
                    # Check delivery count via XPENDING
                    try:
                        pending = await self._redis.xpending_range(
                            settings.alerts_stream,
                            settings.consumer_group,
                            min=msg_id,
                            max=msg_id,
                            count=1,
                        )
                        delivery_count = pending[0]["times_delivered"] if pending else 1
                    except Exception:
                        delivery_count = 1

                    if delivery_count >= _MAX_DELIVERY_COUNT:
                        raw = data.get(b"data") or data.get("data", b"")
                        if isinstance(raw, bytes):
                            raw = raw.decode()
                        logger.warning(
                            "alert_dead_lettered msg_id=%s deliveries=%d",
                            msg_id, delivery_count,
                        )
                        await self._to_dead_letter(
                            f"max_deliveries_exceeded:{delivery_count}", raw
                        )
                        await self._ack(msg_id)
                    else:
                        logger.info(
                            "alert_reclaimed msg_id=%s deliveries=%d",
                            msg_id, delivery_count,
                        )
                        await self._process(msg_id, data)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("autoclaim_loop_error error=%s", exc)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._redis = await aioredis.from_url(
            f"redis://{settings.redis_host}:{settings.redis_port}"
        )
        try:
            await self._redis.xgroup_create(
                settings.alerts_stream, settings.consumer_group, id="0", mkstream=True
            )
        except Exception:
            pass  # group already exists

        await self._load_known_cameras()
        logger.info("alert_consumer_started known_cameras=%d", len(self._known_cameras))

        # Background tasks
        asyncio.create_task(self._camera_refresh_loop(), name="camera_refresh")
        asyncio.create_task(self._camera_pubsub_loop(), name="camera_pubsub")
        asyncio.create_task(self._autoclaim_loop(), name="autoclaim")

        while True:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=settings.consumer_group,
                    consumername=settings.consumer_name,
                    streams={settings.alerts_stream: ">"},
                    count=10,
                    block=1000,
                )
                if not messages:
                    continue
                for _stream, entries in messages:
                    for msg_id, data in entries:
                        await self._process(msg_id, data)
            except Exception as exc:
                logger.error("alert_consumer_loop_error error=%s", exc)
                await asyncio.sleep(1)
