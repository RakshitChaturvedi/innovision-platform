# phase 1 stub

import asyncio, logging, os, sys, uuid
import redis.asyncio as aioredis

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

sys.path.insert(0, "/app")
from shared.contracts.alert_event import AlertEvent, AlertEventValidator
from shared.contracts.enums import SourceUC

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
DATABASE_URL = os.environ.get("DATABASE_URL", "")
CONSUMER_GROUP = "alert_management_group"
CONSUMER_NAME = "alert_management_worker_1"
ALERTS_STREAM = "alerts:live"
DEAD_LETTER_STREAM = "alerts:dead_letter"

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    consumer_task = asyncio.create_task(consume_alerts(redis_client, session_factory))
    logger.info("alert_management_phase1_stub_started")

    yield

    logger.info("alert_management_shutting_down")
    consumer_task.cancel()

    try:
        await consumer_task
    except asyncio.CancelledError:
        pass

    await redis_client.aclose()
    await engine.dispose()

app = FastAPI(title="Alert Management Service", version="0.1.0-phase1-stub", lifespan=lifespan)

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "alert_management", "phase": "1-stub"}

async def load_known_camera_ids(session_factory) -> set:
    # load camera ids from db for validation
    async with session_factory() as session:
        rows = await session.execute(text("SELECT id FROM cameras"))
        return {row.id for row in rows.fetchall()}

async def consume_alerts(redis_client: aioredis.Redis, session_factory) -> None:
    # reads from alerts:live, validates AlertEvent schema, writes to platform alerts table, routes invalid alerts to dl stream
    try:
        await redis_client.xgroup_create(ALERTS_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except Exception:
        pass

    known_cameras =await load_known_camera_ids(session_factory)
    logger.info("alert_consumer_started known_cameras=%d", len(known_cameras))

    while True:
        try:
            messages = await redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams={ALERTS_STREAM: ">"},
                count=10,
                block=1000
            )

            if not messages:
                continue

            for stream, entries in messages:
                for msg_id, data in entries:
                    await process_alert(
                        msg_id=msg_id,
                        data=data,
                        redis_client=redis_client,
                        session_factory=session_factory,
                        known_cameras=known_cameras
                    )
        except Exception as e:
            logger.error("alert_consumer_alert error=%s", e)
            await asyncio.sleep(1)

async def process_alert(msg_id:str, data:dict, redis_client:aioredis.Redis, session_factory, known_cameras:set) -> None:
    raw = data.get(b"data") or data.get("data")
    if isinstance(raw, bytes):
        raw = raw.decode()

    try:
        alert = AlertEvent.model_validate_json(raw)
    except Exception as e:
        logger.error("alert_schema_invalid msg_id=%s error=%s", msg_id, e)
        await redis_client.xadd(DEAD_LETTER_STREAM, {"error":str(e), "raw":raw, "msg_id":str(msg_id)})
        await redis_client.xack(ALERTS_STREAM, CONSUMER_GROUP, msg_id)
        return

    errors = AlertEventValidator.validate(alert, known_cameras)
    if errors:
        logger.warning("alert_validation_failed alert_id=%s errors=%s",alert.alert_id, errors)
        await redis_client.xadd(
            DEAD_LETTER_STREAM,
            {"errors":str(errors), "alert_id":str(alert.alert_id), "source_uc":alert.source_uc.value}
        )
        await redis_client.xack(ALERTS_STREAM, CONSUMER_GROUP, msg_id)
        return

    # writing to platform alerts table
    try:
        async with session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    INSERT INTO alerts (
                        id, alert_id, camera_id, source_uc, alert_type, severity, title, 
                        description, source_event_id, frame_reference, frame_provider,
                        status, metadata, created_at
                    ) VALUES (
                        :id, :alert_id, :camera_id, :source_uc, :alert_type, :severity, :title,
                        :description, :source_event_id, :frame_reference, :frame_provider,
                        :status, :metadata, :created_at
                    )
                    ON CONFLICT (alert_id) DO NOTHING
                """), {
                    "id": str(uuid.uuid4()),
                    "alert_id": str(alert.alert_id),
                    "camera_id": str(alert.camera_id),
                    "source_uc": alert.source_uc.value,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity.value,
                    "title": alert.title,
                    "description": alert.description,
                    "source_event_id": str(alert.source_event_id),
                    "frame_reference": alert.frame_reference,
                    "frame_provider": (
                        alert.frame_provider.value if alert.frame_provider else None
                    ),
                    "status": alert.status.value,
                    "metadata": alert.metadata,
                    "created_at": alert.timestamp,
                    } 
                )
        logger.info(
            "alert_persisted alert_id=%s uc=%s type=%s severity=%s",
            alert.alert_id, alert.source_uc.value, alert.alert_type, alert.severity.value
        )

    except Exception as e:
        logger.error("alert_persist_failed alert_id=%s error=%s", alert.alert_id, e)
        return

    await redis_client.xack(ALERTS_STREAM, CONSUMER_GROUP, msg_id)
