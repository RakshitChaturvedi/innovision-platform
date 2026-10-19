"""
main alert pipeline, consumes alerts:live with redis streams, validates, persists, triggers incidents,
pushes to socket io, schedules escalation. Only xacks after every step succeeds.
"""
import json
import asyncio, logging, uuid
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

MAX_DELIVERY_ATTEMPTS = 5


class AlertConsumer:
    def __init__(self):
        self._redis: aioredis.Redis | None = None
        self._known_cameras: set = set()
        self._msg_delivery_attempts: dict[str, int] = {}
        self._last_pending_recovery_time: float = 0.0
        self._metrics = {
            "processed": 0,
            "persisted": 0,
            "duplicates_acked": 0,
            "dead_lettered": 0,
            "pending_recovered": 0,
            "poison_acked": 0,
            "errors": 0,
        }

    @property
    def metrics(self) -> dict:
        return dict(self._metrics)

    async def _load_known_cameras(self) -> None:
        try:
            async with _session_factory() as session:
                rows = await session.execute(text("SELECT id FROM cameras"))
                self._known_cameras = {str(r.id) for r in rows.fetchall()}
                # Also include raw objects if UUID
                self._known_cameras.update({r.id for r in rows.fetchall() if hasattr(r, "id")})
        except Exception as e:
            logger.warning("alert_consumer_load_cameras_warning error=%s", e)

    async def _to_dead_letter(self, error: str, raw: str) -> None:
        self._metrics["dead_lettered"] += 1
        try:
            await self._redis.xadd(settings.dead_letter_stream, {"error": error, "raw": raw})
        except Exception as e:
            logger.error("dead_letter_stream_write_error error=%s", e)

    async def _ack(self, msg_id: str) -> None:
        try:
            await self._redis.xack(settings.alerts_stream, settings.consumer_group, msg_id)
            if msg_id in self._msg_delivery_attempts:
                self._msg_delivery_attempts.pop(msg_id, None)
        except Exception as e:
            logger.error("alert_ack_failed msg_id=%s error=%s", msg_id, e)

    async def _process(self, msg_id: str, data: dict) -> None:
        raw = data.get(b"data") or data.get("data")
        if isinstance(raw, bytes):
            raw = raw.decode()

        # Track delivery attempts for poison pill protection
        attempts = self._msg_delivery_attempts.get(msg_id, 0) + 1
        self._msg_delivery_attempts[msg_id] = attempts
        if attempts > MAX_DELIVERY_ATTEMPTS:
            logger.error(
                "alert_poison_pill_exceeded_attempts msg_id=%s attempts=%d - routing to dead letter",
                msg_id,
                attempts,
            )
            self._metrics["poison_acked"] += 1
            await self._to_dead_letter(f"max_attempts_exceeded_{attempts}", raw or "")
            await self._ack(msg_id)
            return

        # 1. Schema validation
        try:
            alert = AlertEvent.model_validate_json(raw)
        except Exception as e:
            logger.error("alert_schema_invalid msg_id=%s error=%s", msg_id, e)
            await self._to_dead_letter(str(e), raw or "")
            await self._ack(msg_id)
            return

        # 2. Platform camera validation (with dynamic refresh on unknown camera)
        errors = validate_alert(alert, self._known_cameras)
        if errors and any("not registered" in str(err) for err in errors):
            await self._load_known_cameras()
            errors = validate_alert(alert, self._known_cameras)

        if errors:
            logger.warning(
                "alert_validation_failed alert_id=%s errors=%s",
                alert.alert_id,
                errors,
            )
            await self._to_dead_letter(str(errors), raw or "")
            await self._ack(msg_id)
            return

        # 3. Transactional persistence & incident creation
        row_id = str(uuid.uuid4())
        try:
            async with _session_factory() as session:
                async with session.begin():
                    inserted = await insert_alert(session, row_id, alert)
                    if not inserted:
                        # Alert already persisted previously (idempotent retry).
                        # ACK now to avoid leaving the message in Redis PEL forever!
                        self._metrics["duplicates_acked"] += 1
                        logger.info(
                            "alert_duplicate_already_persisted alert_id=%s msg_id=%s - acknowledging",
                            alert.alert_id,
                            msg_id,
                        )
                        await self._ack(msg_id)
                        return

                    self._metrics["persisted"] += 1

                    # Trigger or link incident with full hierarchy & deduplication
                    incident_id = await maybe_create_incident(
                        session=session,
                        alert_row_id=row_id,
                        alert_title=alert,
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
                            "incident_id": incident_id,
                        }),
                        session=session,
                    )
                    alert_row = await fetch_alert_by_alert_id(session, str(alert.alert_id))
        except Exception as e:
            self._metrics["errors"] += 1
            logger.error("alert_persist_failed alert_id=%s error=%s", alert.alert_id, e)
            # Do NOT ack on database failure; allow Redis stream PEL to retry on recovery
            return

        # 4. Push to connected operators & dispatch user notifications
        try:
            if alert_row:
                await push_alert(alert_row)
                from services.notification.src.service import dispatch_alert_notifications
                await dispatch_alert_notifications(_session_factory, alert_row)
        except Exception as e:
            logger.error("socket_push_or_notification_failed alert_id=%s error=%s", alert.alert_id, e)

        # 5. Schedule escalation for severe alerts
        if alert.severity.value in ("high", "critical"):
            try:
                escalation_check.apply_async(args=[row_id, 1], countdown=settings.escalation_level_1_delay_s)
            except Exception as e:
                logger.warning("escalation_task_schedule_warning error=%s", e)

        self._metrics["processed"] += 1
        logger.info(
            "alert_processed alert_id=%s uc=%s severity=%s incident=%s",
            alert.alert_id, alert.source_uc.value, alert.severity.value, incident_id,
        )
        await self._ack(msg_id)

    async def _recover_pending_messages(self) -> None:
        """
        Inspects Pending Entries List (PEL) for unacknowledged messages
        from prior crashes or network dropouts, reprocessing or dead-lettering them.
        """
        if not self._redis:
            return

        try:
            # Read up to 20 pending messages (id='0' reads from history of consumer group)
            pending = await self._redis.xreadgroup(
                groupname=settings.consumer_group,
                consumername=settings.consumer_name,
                streams={settings.alerts_stream: "0"},
                count=20,
            )
            if not pending:
                return

            for stream, entries in pending:
                if not entries:
                    continue
                logger.info("recovering_pending_messages count=%d", len(entries))
                for msg_id, data in entries:
                    if isinstance(msg_id, bytes):
                        msg_id = msg_id.decode()
                    self._metrics["pending_recovered"] += 1
                    await self._process(msg_id, data)

        except Exception as e:
            logger.warning("pending_recovery_error error=%s", e)

    async def start(self) -> None:
        self._redis = await aioredis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
        try:
            await self._redis.xgroup_create(settings.alerts_stream, settings.consumer_group, id="0", mkstream=True)
        except Exception:
            pass

        await self._load_known_cameras()
        logger.info("alert_consumer_started known_cameras=%d", len(self._known_cameras))

        # Perform initial recovery of pending messages on consumer startup
        await self._recover_pending_messages()
        self._last_pending_recovery_time = asyncio.get_event_loop().time()

        while True:
            try:
                # Periodically recover any stuck pending messages (every 30 seconds)
                now = asyncio.get_event_loop().time()
                if now - self._last_pending_recovery_time > 30.0:
                    self._last_pending_recovery_time = now
                    await self._recover_pending_messages()

                messages = await self._redis.xreadgroup(
                    groupname=settings.consumer_group,
                    consumername=settings.consumer_name,
                    streams={settings.alerts_stream: ">"},
                    count=10,
                    block=1000,
                )
                if not messages:
                    continue
                for stream, entries in messages:
                    for msg_id, data in entries:
                        if isinstance(msg_id, bytes):
                            msg_id = msg_id.decode()
                        await self._process(msg_id, data)
            except Exception as e:
                self._metrics["errors"] += 1
                logger.error("alert_consumer_loop_error error=%s", e)
                await asyncio.sleep(1)