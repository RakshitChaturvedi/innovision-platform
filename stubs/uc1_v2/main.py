"""
UC1-v2 platform integration demo.

UC1 discovers its assigned cameras from Camera Registry and consumes
the corresponding ingestion frame streams from Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import cv2
import httpx
import numpy as np
import redis.asyncio as aioredis
from fastapi import FastAPI
from redis.exceptions import ResponseError
from ultralytics import YOLO


# ─── Logging ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger("uc1_v2_platform")


# ─── Configuration ───────────────────────────────────────────────

REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://redis:6379",
)

CAMERA_REGISTRY_URL = os.getenv(
    "CAMERA_REGISTRY_URL",
    "http://camera_registry:8011",
)

UC_ID = "uc1"

REDIS_CONSUMER_GROUP = os.getenv(
    "REDIS_CONSUMER_GROUP",
    "uc1_v2_group",
)

REDIS_CONSUMER_NAME = os.getenv(
    "REDIS_CONSUMER_NAME",
    "uc1_v2_worker_1",
)

MODEL_PATH = os.getenv(
    "YOLO_MODEL",
    "yolov8n.pt",
)

CONFIDENCE = float(
    os.getenv("YOLO_CONFIDENCE", "0.35")
)

ALERTS_STREAM = "alerts:live"

PEOPLE_THRESHOLD = int(
    os.getenv("PEOPLE_THRESHOLD", "3")
)

ALERT_COOLDOWN_SECONDS = float(
    os.getenv("ALERT_COOLDOWN_SECONDS", "20")
)

ALERT_MGMT_URL = os.getenv(
    "ALERT_MGMT_URL",
    "http://alert_management:8000",
)

INCIDENT_MGMT_URL = os.getenv(
    "INCIDENT_MGMT_URL",
    "http://incident_management:8000",
)

PLATFORM_POLL_INTERVAL_S = float(
    os.getenv("PLATFORM_POLL_INTERVAL_S", "3")
)


# ─── Runtime state ────────────────────────────────────────────────

camera_ids: list[str] = []

camera_streams: dict[str, str] = {}


latest_result = {
    "status": "starting",
    "camera_id": None,
    "frame_seq": None,
    "people": 0,
    "resolution": None,
    "jpeg_bytes": 0,
    "cache": "unknown",
    "cache_fetch_ms": None,
    "detection_ms": None,
    "frames_processed": 0,
    "cache_misses": 0,
    "last_update": None,
}


pipeline_state = {
    "stage_ingestion": "idle",
    "stage_detection": "idle",
    "stage_alert_published": "idle",
    "stage_alert_persisted": "idle",
    "stage_incident_created": "idle",
    "last_alert_id": None,
    "last_alert_at": None,
}


platform_view = {
    "alerts": [],
    "incidents": [],
    "platform_reachable": False,
    "last_poll_error": None,
}


# Per-camera alert cooldown.
_last_alert_fired_at: dict[str, float] = {}


# ─── Camera Registry ─────────────────────────────────────────────

async def discover_cameras(
    client: httpx.AsyncClient,
) -> list[str]:
    response = await client.get(
        f"{CAMERA_REGISTRY_URL}/cameras/by-uc/{UC_ID}"
    )

    response.raise_for_status()

    payload = response.json()

    camera_ids = payload.get("camera_ids")

    if not isinstance(camera_ids, list):
        raise RuntimeError(
            "Camera Registry returned an invalid camera assignment response"
        )

    return camera_ids


async def load_camera_assignments() -> None:
    global camera_ids
    global camera_streams

    async with httpx.AsyncClient(timeout=5.0) as client:
        discovered_camera_ids = await discover_cameras(client)

    camera_ids = [
        camera_id
        for camera_id in discovered_camera_ids
        if camera_id
    ]

    camera_streams = {
        camera_id: f"frames:{camera_id}"
        for camera_id in camera_ids
    }

    logger.info(
        "camera_registry_discovery uc=%s cameras=%s",
        UC_ID,
        camera_ids,
    )

    if not camera_ids:
        logger.warning(
            "no_cameras_assigned_to_uc uc=%s",
            UC_ID,
        )


# ─── Alert Publishing ────────────────────────────────────────────

async def maybe_fire_alert(
    redis_client: aioredis.Redis,
    people: int,
    frame_seq: int,
    camera_id: str,
) -> None:

    if people < PEOPLE_THRESHOLD:
        return

    now = time.monotonic()

    last_fired = _last_alert_fired_at.get(
        camera_id,
        0.0,
    )

    if (
        now - last_fired
        < ALERT_COOLDOWN_SECONDS
    ):
        return

    _last_alert_fired_at[camera_id] = now

    alert_id = str(uuid.uuid4())

    source_event_id = str(uuid.uuid4())

    timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    severity = (
        "critical"
        if people >= PEOPLE_THRESHOLD * 2
        else "high"
    )

    alert = {
        "alert_id": alert_id,
        "camera_id": camera_id,
        "timestamp": timestamp,
        "severity": severity,
        "alert_type": "headcount_breach",
        "title": (
            f"Headcount Threshold Exceeded — "
            f"{people} persons detected"
        ),
        "description": (
            f"UC1 detected {people} persons in frame "
            f"(threshold: {PEOPLE_THRESHOLD}). "
            f"Frame sequence {frame_seq}."
        ),
        "source_event_id": source_event_id,
        "source_uc": UC_ID,
        "frame_reference": None,
        "frame_provider": None,
        "status": "pending",
        "metadata": {
            "people_count": people,
            "threshold": PEOPLE_THRESHOLD,
            "frame_seq": frame_seq,
            "camera_id": camera_id,
            "demo_stub": "uc1_v2",
        },
    }

    await redis_client.xadd(
        ALERTS_STREAM,
        {
            "data": json.dumps(alert),
        },
    )

    pipeline_state[
        "stage_alert_published"
    ] = "active"

    pipeline_state[
        "last_alert_id"
    ] = alert_id

    pipeline_state[
        "last_alert_at"
    ] = time.time()

    logger.warning(
        "alert_published_to_platform "
        "alert_id=%s camera_id=%s "
        "people=%d severity=%s",
        alert_id,
        camera_id,
        people,
        severity,
    )


# ─── Platform Poller ──────────────────────────────────────────────

async def poll_platform_state() -> None:

    async with httpx.AsyncClient(timeout=5.0) as client:

        while True:

            try:

                alerts_response = await client.get(
                    f"{ALERT_MGMT_URL}/alerts",
                    params={
                        "source_uc": UC_ID,
                        "limit": 10,
                    },
                )

                alerts_response.raise_for_status()

                alerts = alerts_response.json()

                incidents_response = await client.get(
                    f"{INCIDENT_MGMT_URL}/incidents",
                    params={
                        "limit": 10,
                    },
                )

                incidents_response.raise_for_status()

                incidents = incidents_response.json()

                platform_view[
                    "alerts"
                ] = alerts

                platform_view[
                    "incidents"
                ] = incidents

                platform_view[
                    "platform_reachable"
                ] = True

                platform_view[
                    "last_poll_error"
                ] = None

                last_alert_id = (
                    pipeline_state[
                        "last_alert_id"
                    ]
                )

                if any(
                    alert.get("alert_id")
                    == last_alert_id
                    for alert in alerts
                ):
                    pipeline_state[
                        "stage_alert_persisted"
                    ] = "active"

                triggering_alert_row_ids = {
                    alert["id"]
                    for alert in alerts
                    if (
                        alert.get("alert_id")
                        == last_alert_id
                        and alert.get("id")
                        is not None
                    )
                }

                if any(
                    incident.get("alert_id")
                    in triggering_alert_row_ids
                    for incident in incidents
                ):
                    pipeline_state[
                        "stage_incident_created"
                    ] = "active"

            except asyncio.CancelledError:
                raise

            except Exception as exc:

                platform_view[
                    "platform_reachable"
                ] = False

                platform_view[
                    "last_poll_error"
                ] = str(exc)

            await asyncio.sleep(
                PLATFORM_POLL_INTERVAL_S
            )


# ─── Redis Consumer Groups ───────────────────────────────────────

async def ensure_consumer_groups(
    redis_client: aioredis.Redis,
) -> None:

    for stream in camera_streams.values():

        try:

            await redis_client.xgroup_create(
                name=stream,
                groupname=REDIS_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )

            logger.info(
                "consumer_group_created "
                "stream=%s group=%s",
                stream,
                REDIS_CONSUMER_GROUP,
            )

        except ResponseError as exc:

            if "BUSYGROUP" not in str(exc):
                raise


# ─── Detection ────────────────────────────────────────────────────

def count_people(
    model: YOLO,
    frame: np.ndarray,
) -> tuple[int, np.ndarray]:

    results = model(
        frame,
        conf=CONFIDENCE,
        classes=[0],
        verbose=False,
    )

    count = 0

    for result in results:

        if result.boxes is not None:
            count += len(result.boxes)

    annotated_frame = (
        results[0].plot()
        if len(results) > 0
        else frame
    )

    return count, annotated_frame


async def process_message(
    redis_client: aioredis.Redis,
    model: YOLO,
    message_id: str,
    fields: dict[str, str],
) -> None:

    payload = fields.get("data")

    if not payload:
        return

    event = json.loads(payload)

    frame_seq = event["frame_seq"]
    camera_id = event["camera_id"]
    frame_reference = event["frame_reference"]
    frame_provider = event["frame_provider"]

    pipeline_state[
        "stage_ingestion"
    ] = "active"

    if frame_provider != "redis":

        logger.warning(
            "unsupported_frame_provider "
            "camera_id=%s provider=%s",
            camera_id,
            frame_provider,
        )

        return

    fetch_start = time.perf_counter()

    jpeg_bytes = await redis_client.get(
        frame_reference
    )

    fetch_ms = (
        time.perf_counter()
        - fetch_start
    ) * 1000

    if jpeg_bytes is None:

        latest_result[
            "cache_misses"
        ] += 1

        logger.debug(
            "frame_cache_miss "
            "camera_id=%s frame_seq=%s "
            "reference=%s",
            camera_id,
            frame_seq,
            frame_reference,
        )

        return

    jpeg_array = np.frombuffer(
        jpeg_bytes,
        dtype=np.uint8,
    )

    frame = cv2.imdecode(
        jpeg_array,
        cv2.IMREAD_COLOR,
    )

    if frame is None:

        logger.warning(
            "frame_decode_failed "
            "camera_id=%s frame_seq=%s",
            camera_id,
            frame_seq,
        )

        return

    pipeline_state[
        "stage_detection"
    ] = "active"

    detection_start = time.perf_counter()

    people, _annotated_frame = count_people(
        model,
        frame,
    )

    detection_ms = (
        time.perf_counter()
        - detection_start
    ) * 1000

    height, width = frame.shape[:2]

    latest_result.update(
        {
            "status": "running",
            "camera_id": camera_id,
            "frame_seq": frame_seq,
            "people": people,
            "resolution": f"{width}x{height}",
            "jpeg_bytes": len(jpeg_bytes),
            "cache": "hit",
            "cache_fetch_ms": round(
                fetch_ms,
                2,
            ),
            "detection_ms": round(
                detection_ms,
                2,
            ),
            "frames_processed": (
                latest_result[
                    "frames_processed"
                ] + 1
            ),
            "last_update": time.time(),
        }
    )

    await maybe_fire_alert(
        redis_client=redis_client,
        people=people,
        frame_seq=frame_seq,
        camera_id=camera_id,
    )


# ─── Multi-Camera Consumer ───────────────────────────────────────

async def consume(
    redis_client: aioredis.Redis,
    model: YOLO,
) -> None:

    while not camera_streams:
        try:
            await load_camera_assignments()

        except Exception:
            logger.exception(
                "camera_registry_discovery_failed"
            )

        if not camera_streams:
            logger.warning(
                "UC1 has no assigned cameras; retrying"
            )
            await asyncio.sleep(5)

    await ensure_consumer_groups(redis_client)

    logger.info(
        "UC1 consumer started streams=%s",
        list(camera_streams.values()),
    )

    while True:
        try:

            streams = {
                stream: ">"
                for stream in camera_streams.values()
            }

            messages = await redis_client.xreadgroup(
                groupname=REDIS_CONSUMER_GROUP,
                consumername=REDIS_CONSUMER_NAME,
                streams=streams,
                count=1,
                block=5000,
            )

            if not messages:
                continue

            for stream_name, entries in messages:

                if isinstance(
                    stream_name,
                    bytes,
                ):
                    stream_name = (
                        stream_name.decode()
                    )

                for message_id, fields in entries:

                    if isinstance(
                        message_id,
                        bytes,
                    ):
                        message_id = (
                            message_id.decode()
                        )

                    decoded_fields = {
                        (
                            key.decode()
                            if isinstance(
                                key,
                                bytes,
                            )
                            else key
                        ): (
                            value.decode()
                            if isinstance(
                                value,
                                bytes,
                            )
                            else value
                        )
                        for key, value
                        in fields.items()
                    }

                    try:

                        await process_message(
                            redis_client,
                            model,
                            message_id,
                            decoded_fields,
                        )

                        await redis_client.xack(
                            stream_name,
                            REDIS_CONSUMER_GROUP,
                            message_id,
                        )

                    except Exception:

                        logger.exception(
                            "frame_processing_failed "
                            "stream=%s "
                            "message_id=%s",
                            stream_name,
                            message_id,
                        )

        except asyncio.CancelledError:
            raise

        except Exception:

            logger.exception(
                "uc1_multi_stream_consumer_failed"
            )

            await asyncio.sleep(2)


# ─── Application Lifecycle ───────────────────────────────────────

consumer_task: asyncio.Task | None = None
poller_task: asyncio.Task | None = None

redis_client: aioredis.Redis | None = None
model: YOLO | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):

    global consumer_task
    global poller_task
    global redis_client
    global model

    logger.info(
        "starting UC1-v2"
    )

    model = YOLO(
        MODEL_PATH
    )

    redis_client = aioredis.from_url(
        REDIS_URL,
        decode_responses=False,
    )

    await redis_client.ping()

    latest_result[
        "status"
    ] = "running"

    consumer_task = asyncio.create_task(
        consume(
            redis_client,
            model,
        )
    )

    poller_task = asyncio.create_task(
        poll_platform_state()
    )

    yield

    for task in (
        consumer_task,
        poller_task,
    ):

        if task:
            task.cancel()

    for task in (
        consumer_task,
        poller_task,
    ):

        if task:

            try:
                await task

            except asyncio.CancelledError:
                pass

    if redis_client:
        await redis_client.aclose()


# ─── FastAPI ──────────────────────────────────────────────────────

app = FastAPI(
    title="Innovision UC1-v2 — Platform Demo",
    lifespan=lifespan,
)


@app.get("/api/latest")
async def get_latest():
    return latest_result


@app.get("/api/pipeline")
async def get_pipeline():
    return pipeline_state


@app.get("/api/platform")
async def get_platform():
    return platform_view


@app.get("/api/cameras")
async def get_cameras():
    return {
        "uc": UC_ID,
        "camera_ids": camera_ids,
        "streams": camera_streams,
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "uc": UC_ID,
        "camera_ids": camera_ids,
    }