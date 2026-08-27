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

class AlertConsumer:
    def __init__(self):
        self._redis: aioredis.Redis | None = None
        self._known_cameras: set = set()

    async def _load_known_cameras(self) -> None:
        async with _session_factory() as session:
            rows = await session.execute(text("SELECT id FROM cameras"))
            self._known_cameras = {r.id for r in rows.fetchall()}

    async def _to_dead_letter(self, error: str, raw: str) -> None:
        await self._redis.xadd(settings.dead_letter_stream, {"error": error, "raw": raw})

    async def _ack(self, msg_id: str) -> None:
        await self._redis.xack(settings.alerts_stream, settings.consumer_group, msg_id)

    async def _process(self, msg_id: str, data: dict) -> None:
        raw = data.get(b"data") or data.get("data")
        if isinstance(raw, bytes):
            raw = raw.decode()

        # 1. schema validation
        try:
            alert = AlertEvent.model_validate_json(raw)
        except Exception as e:
            logger.error("alert_schema_invalid msg_id=%s error=%s", msg_id, e)
            await self._to_dead_letter(str(e), raw)
            await self._ack(msg_id)
            return

        # 2. platform validation
        errors = validate_alert(alert, self._known_cameras)
        if errors:
            logger.warning("alert_validation_failed alert_id=%s errors=%s",
                           alert.alert_id, errors)
            await self._to_dead_letter(str(errors), raw)
            await self._ack(msg_id)
            return
        row_id = str(uuid.uuid4())
        try:
            async with _session_factory() as session:
                async with session.begin():
                    inserted = await insert_alert(session, row_id, alert)
                    if not inserted:
                        return
                    incident_id = await maybe_create_incident(
                        session,
                        row_id,
                        alert.title,
                        alert.severity.value,
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
                    alert_row = await fetch_alert_by_alert_id(session, str(alert.alert_id))
        except Exception as e:
            logger.error("alert_persist_failed alert_id=%s error=%s", alert.alert_id, e)
            return
        
        # 3. push to connected operators
        try:
            await push_alert(alert_row)
        except Exception as e:
            logger.error("socket_push_failed alert_id=%s error=%s", alert.alert_id, e)

        # 4. schedule escalation for severe alerts
        if alert.severity.value in ("high", "critical"):
            escalation_check.apply_async(args=[row_id, 1], countdown=settings.escalation_level_1_delay_s)
        logger.info("alert_processed alert_id=%s uc=%s severity=%s incident=%s",
                    alert.alert_id, alert.source_uc.value, alert.severity.value, incident_id)
        await self._ack(msg_id)

    async def start(self) -> None:
        self._redis = await aioredis.from_url(f"redis://{settings.redis_host}:{settings.redis_port}")
        try:
            await self._redis.xgroup_create(settings.alerts_stream, settings.consumer_group, id="0", mkstream=True)
        except Exception:
            pass

        await self._load_known_cameras()
        logger.info("alert_consumer_started known_cameras=%d", len(self._known_cameras))

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
                for stream, entries in messages:
                    for msg_id, data in entries:
                        await self._process(msg_id, data)
            except Exception as e:
                logger.error("alert_consumer_loop_error error=%s", e)
                await asyncio.sleep(1)