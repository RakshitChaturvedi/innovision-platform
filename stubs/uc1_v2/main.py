"""
UC1-v2 integration stub.

Consumes FrameEvents from the ingestion Redis Stream, retrieves
the actual JPEG frame from the Redis hot-path cache, decodes it,
and performs lightweight person detection using YOLOv8n.

This is intentionally separate from the existing UC1 stub.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import cv2
import numpy as np
import redis.asyncio as aioredis
from redis.exceptions import ResponseError
from ultralytics import YOLO
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger("uc1_v2")


REDIS_URL = os.getenv(
    "REDIS_URL",
    "redis://redis:6379",
)

CAMERA_ID = os.getenv(
    "TEST_CAMERA_ID",
    "00000000-0000-0000-0000-000000000001",
)

STREAM = f"frames:{CAMERA_ID}"

GROUP = os.getenv(
    "REDIS_CONSUMER_GROUP",
    "uc1_v2_group",
)

CONSUMER = os.getenv(
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

latest_result = {
    "status": "starting",
    "camera_id": CAMERA_ID,
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

async def ensure_consumer_group(
    redis_client: aioredis.Redis,
) -> None:
    """Create the consumer group if it doesn't already exist."""

    try:
        await redis_client.xgroup_create(
            name=STREAM,
            groupname=GROUP,
            id="0",
            mkstream=True,
        )

        logger.info(
            "consumer_group_created stream=%s group=%s",
            STREAM,
            GROUP,
        )

    except ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            logger.info(
                "consumer_group_exists stream=%s group=%s",
                STREAM,
                GROUP,
            )
        else:
            raise


def count_people(
    model: YOLO,
    frame: np.ndarray,
) -> int:
    """
    Run lightweight person detection.

    COCO class 0 = person.
    """

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

    return count


async def process_message(
    redis_client: aioredis.Redis,
    model: YOLO,
    message_id: str,
    fields: dict[str, str],
) -> None:
    """Process one FrameEvent."""

    payload = fields.get("data")

    if not payload:
        logger.warning(
            "frame_event_missing_data message_id=%s",
            message_id,
        )
        return

    event = json.loads(payload)

    frame_seq = event["frame_seq"]
    camera_id = event["camera_id"]
    frame_reference = event["frame_reference"]
    frame_provider = event["frame_provider"]

    logger.debug(
        "frame_event_received "
        "camera_id=%s frame_seq=%d provider=%s reference=%s",
        camera_id,
        frame_seq,
        frame_provider,
        frame_reference,
    )

    # We explicitly want to prove the Redis hot path.
    if frame_provider != "redis":
        logger.warning(
            "unexpected_frame_provider "
            "camera_id=%s frame_seq=%d provider=%s",
            camera_id,
            frame_seq,
            frame_provider,
        )
        return

    # ---------------------------------------------------------------
    # Fetch JPEG from Redis hot-path cache
    # ---------------------------------------------------------------

    fetch_start = time.perf_counter()

    jpeg_bytes = await redis_client.get(frame_reference)

    fetch_ms = (
        time.perf_counter() - fetch_start
    ) * 1000

    if jpeg_bytes is None:
        latest_result["cache_misses"] += 1
        logger.warning(
            "frame_cache_miss "
            "camera_id=%s frame_seq=%d key=%s",
            camera_id,
            frame_seq,
            frame_reference,
        )
        return

    # ---------------------------------------------------------------
    # Decode JPEG
    # ---------------------------------------------------------------

    jpeg_array = np.frombuffer(
        jpeg_bytes,
        dtype=np.uint8,
    )

    frame = cv2.imdecode(
        jpeg_array,
        cv2.IMREAD_COLOR,
    )

    if frame is None:
        logger.error(
            "frame_decode_failed "
            "camera_id=%s frame_seq=%d",
            camera_id,
            frame_seq,
        )
        return

    # ---------------------------------------------------------------
    # Lightweight person detection
    # ---------------------------------------------------------------

    detection_start = time.perf_counter()

    people = count_people(
        model,
        frame,
    )

    detection_ms = (
        time.perf_counter() - detection_start
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
            "cache_fetch_ms": round(fetch_ms, 2),
            "detection_ms": round(detection_ms, 2),
            "frames_processed": latest_result["frames_processed"] + 1,
            "last_update": time.time(),
        }
    )

    logger.info(
        "uc1_frame_processed "
        "camera_id=%s "
        "frame_seq=%d "
        "people=%d "
        "resolution=%dx%d "
        "jpeg_bytes=%d "
        "cache=hit "
        "cache_fetch_ms=%.2f "
        "detection_ms=%.2f",
        camera_id,
        frame_seq,
        people,
        width,
        height,
        len(jpeg_bytes),
        fetch_ms,
        detection_ms,
    )


async def consume(
    redis_client: aioredis.Redis,
    model: YOLO,
) -> None:
    """Consume FrameEvents continuously."""

    await ensure_consumer_group(redis_client)

    logger.info(
        "uc1_v2_consumer_started "
        "camera_id=%s stream=%s group=%s consumer=%s",
        CAMERA_ID,
        STREAM,
        GROUP,
        CONSUMER,
    )

    while True:
        try:
            messages = await redis_client.xreadgroup(
                groupname=GROUP,
                consumername=CONSUMER,
                streams={
                    STREAM: ">",
                },
                count=1,
                block=5000,
            )

            if not messages:
                continue

            for _, entries in messages:
                for message_id, fields in entries:

                    if isinstance(message_id, bytes):
                        message_id = message_id.decode()

                    decoded_fields = {}

                    for key, value in fields.items():
                        if isinstance(key, bytes):
                            key = key.decode()

                        if isinstance(value, bytes):
                            value = value.decode()

                        decoded_fields[key] = value

                    try:
                        await process_message(
                            redis_client,
                            model,
                            message_id,
                            decoded_fields,
                        )

                        await redis_client.xack(
                            STREAM,
                            GROUP,
                            message_id,
                        )

                    except Exception:
                        logger.exception(
                            "frame_processing_failed "
                            "message_id=%s",
                            message_id,
                        )

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "uc1_v2_consumer_error"
            )

            await asyncio.sleep(2)

consumer_task: asyncio.Task | None = None
redis_client: aioredis.Redis | None = None
model: YOLO | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_task
    global redis_client
    global model

    logger.info(
        "uc1_v2_starting camera_id=%s",
        CAMERA_ID,
    )

    logger.info(
        "loading_yolo_model model=%s",
        MODEL_PATH,
    )

    model = YOLO(MODEL_PATH)

    redis_client = aioredis.from_url(
        REDIS_URL,
        decode_responses=False,
    )

    await redis_client.ping()

    logger.info("redis_connected")

    latest_result["status"] = "running"

    consumer_task = asyncio.create_task(
        consume(
            redis_client,
            model,
        )
    )

    yield

    if consumer_task:
        consumer_task.cancel()

        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    if redis_client:
        await redis_client.aclose()

app = FastAPI(
    title="Innovision UC1-v2",
    lifespan=lifespan,
)

@app.get("/api/latest")
async def get_latest():
    return latest_result

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "camera_id": CAMERA_ID
    }

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Innovision UC1</title>

    <style>
        body {
            margin: 0;
            background: #111;
            color: white;
            font-family: Arial, sans-serif;
        }

        .container {
            width: 700px;
            margin: 60px auto;
            padding: 35px;
            background: #1b1b1b;
            border-radius: 16px;
        }

        h1 {
            text-align: center;
        }

        .subtitle {
            text-align: center;
            color: #aaa;
            margin-bottom: 40px;
        }

        .label {
            text-align: center;
            color: #999;
            font-size: 18px;
        }

        #people {
            text-align: center;
            font-size: 110px;
            font-weight: bold;
            margin: 15px 0 35px;
        }

        .stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 15px;
        }

        .stat {
            background: #252525;
            padding: 18px;
            border-radius: 10px;
        }

        .title {
            color: #888;
            font-size: 13px;
        }

        .value {
            margin-top: 8px;
            font-size: 19px;
        }

        #status {
            color: #4ade80;
        }
    </style>
</head>

<body>

<div class="container">

    <h1>INNOVISION — UC1</h1>

    <div class="subtitle">
        Redis Frame Ingestion + Person Detection
    </div>

    <div class="label">
        PEOPLE DETECTED
    </div>

    <div id="people">
        --
    </div>

    <div class="stats">

        <div class="stat">
            <div class="title">CAMERA</div>
            <div id="camera" class="value">--</div>
        </div>

        <div class="stat">
            <div class="title">FRAME</div>
            <div id="frame" class="value">--</div>
        </div>

        <div class="stat">
            <div class="title">RESOLUTION</div>
            <div id="resolution" class="value">--</div>
        </div>

        <div class="stat">
            <div class="title">JPEG SIZE</div>
            <div id="jpeg" class="value">--</div>
        </div>

        <div class="stat">
            <div class="title">CACHE</div>
            <div id="cache" class="value">--</div>
        </div>

        <div class="stat">
            <div class="title">CACHE FETCH</div>
            <div id="fetch" class="value">--</div>
        </div>

        <div class="stat">
            <div class="title">YOLO DETECTION</div>
            <div id="detection" class="value">--</div>
        </div>

        <div class="stat">
            <div class="title">FRAMES PROCESSED</div>
            <div id="processed" class="value">0</div>
        </div>

        <div class="stat">
            <div class="title">CACHE MISSES</div>
            <div id="misses" class="value">0</div>
        </div>

        <div class="stat">
            <div class="title">STATUS</div>
            <div id="status" class="value">STARTING</div>
        </div>

    </div>

</div>

<script>

async function update() {

    try {

        const response = await fetch("/api/latest");
        const data = await response.json();

        document.getElementById("people").innerText =
            data.people ?? "--";

        document.getElementById("camera").innerText =
            data.camera_id ?? "--";

        document.getElementById("frame").innerText =
            data.frame_seq ?? "--";

        document.getElementById("resolution").innerText =
            data.resolution ?? "--";

        document.getElementById("jpeg").innerText =
            data.jpeg_bytes
                ? data.jpeg_bytes.toLocaleString() + " bytes"
                : "--";

        document.getElementById("cache").innerText =
            data.cache ?? "--";

        document.getElementById("fetch").innerText =
            data.cache_fetch_ms != null
                ? data.cache_fetch_ms + " ms"
                : "--";

        document.getElementById("detection").innerText =
            data.detection_ms != null
                ? data.detection_ms + " ms"
                : "--";

        document.getElementById("processed").innerText =
            data.frames_processed ?? 0;

        document.getElementById("misses").innerText =
            data.cache_misses ?? 0;

        document.getElementById("status").innerText =
            (data.status ?? "unknown").toUpperCase();

    } catch (error) {

        document.getElementById("status").innerText =
            "DISCONNECTED";
    }
}

update();
setInterval(update, 500);

</script>

</body>
</html>
"""