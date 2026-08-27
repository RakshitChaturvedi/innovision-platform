"""
UC1-v2 platform integration demo.

Extends the original ingestion + detection stub with a visible
end-to-end path into the Platform Services Layer:

  Ingestion (frames:{camera_id})
      ↓
  UC1 detection (this file)
      ↓ threshold crossed
  AlertEvent published to alerts:live
      ↓
  Alert Management Service (real, running separately)
      persists to `alerts`, auto-creates an `incident` if severity is
      high/critical, pushes over Socket.IO, schedules escalation
      ↓
  This dashboard polls Alert Management + Incident Management's
  REST APIs and shows what actually landed there — proving the
  pipeline works end to end, not just that this stub *sent* something.
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
from redis.exceptions import ResponseError
from ultralytics import YOLO
from fastapi import FastAPI
from fastapi.responses import HTMLResponse


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("uc1_v2_platform")

# ─── Config ──────────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
CAMERA_ID = os.getenv("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000001")
STREAM = f"frames:{CAMERA_ID}"
GROUP = os.getenv("REDIS_CONSUMER_GROUP", "uc1_v2_group")
CONSUMER = os.getenv("REDIS_CONSUMER_NAME", "uc1_v2_worker_1")

MODEL_PATH = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.35"))

# Platform integration
ALERTS_STREAM = "alerts:live"
PEOPLE_THRESHOLD = int(os.getenv("PEOPLE_THRESHOLD", "3"))
ALERT_COOLDOWN_SECONDS = float(os.getenv("ALERT_COOLDOWN_SECONDS", "20"))

ALERT_MGMT_URL = os.getenv("ALERT_MGMT_URL", "http://alert_management:8000")
INCIDENT_MGMT_URL = os.getenv("INCIDENT_MGMT_URL", "http://incident_management:8000")
PLATFORM_POLL_INTERVAL_S = float(os.getenv("PLATFORM_POLL_INTERVAL_S", "3"))

# ─── Shared demo state ───────────────────────────────────────────

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

pipeline_state = {
    "stage_ingestion": "idle",       # idle | active
    "stage_detection": "idle",
    "stage_alert_published": "idle",
    "stage_alert_persisted": "idle",
    "stage_incident_created": "idle",
    "last_alert_id": None,
    "last_alert_at": None,
}

platform_view = {
    "alerts": [],       # from Alert Management, source_uc=uc1
    "incidents": [],    # from Incident Management, tied to those alerts
    "platform_reachable": False,
    "last_poll_error": None,
}

_last_alert_fired_at: float = 0.0


# ─── Alert publishing (this is the "UC → Platform" boundary) ────

async def maybe_fire_alert(
    redis_client: aioredis.Redis,
    people: int,
    frame_seq: int,
) -> None:
    """
    Fires an AlertEvent onto alerts:live when the person count crosses
    PEOPLE_THRESHOLD, subject to a cooldown so the demo doesn't flood
    the platform with one alert per frame.

    This constructs the AlertEvent contract by hand (no shared package
    import) so the stub stays a single self-contained file — the shape
    matches shared/contracts/alert_event.py exactly.
    """
    global _last_alert_fired_at

    if people < PEOPLE_THRESHOLD:
        return

    now = time.monotonic()
    if now - _last_alert_fired_at < ALERT_COOLDOWN_SECONDS:
        return
    _last_alert_fired_at = now

    alert_id = str(uuid.uuid4())
    source_event_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc).isoformat()

    severity = "critical" if people >= PEOPLE_THRESHOLD * 2 else "high"

    alert = {
        "alert_id": alert_id,
        "camera_id": CAMERA_ID,
        "timestamp": ts,
        "severity": severity,
        "alert_type": "headcount_breach",
        "title": f"Headcount Threshold Exceeded — {people} persons detected",
        "description": (
            f"UC1 detected {people} persons in frame (threshold: "
            f"{PEOPLE_THRESHOLD}). Frame sequence {frame_seq}."
        ),
        "source_event_id": source_event_id,
        "source_uc": "uc1",
        "frame_reference": None,
        "frame_provider": None,
        "status": "pending",
        "metadata": {
            "people_count": people,
            "threshold": PEOPLE_THRESHOLD,
            "frame_seq": frame_seq,
            "demo_stub": "uc1_v2",
        },
    }

    await redis_client.xadd(ALERTS_STREAM, {"data": json.dumps(alert)})

    pipeline_state["stage_alert_published"] = "active"
    pipeline_state["last_alert_id"] = alert_id
    pipeline_state["last_alert_at"] = time.time()

    logger.warning(
        "alert_published_to_platform alert_id=%s people=%d severity=%s",
        alert_id, people, severity,
    )


# ─── Platform poller — proves the pipeline actually completed ───

async def poll_platform_state() -> None:
    """
    Background loop that queries the REAL Alert Management and
    Incident Management REST APIs and stores what it finds.

    This is what makes the demo honest: it doesn't just show that
    this stub SENT an alert, it shows what the platform DID with it —
    persisted it, created an incident, etc.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            try:
                alerts_resp = await client.get(
                    f"{ALERT_MGMT_URL}/alerts",
                    params={"source_uc": "uc1", "limit": 10},
                )
                alerts_resp.raise_for_status()
                alerts = alerts_resp.json()

                incidents_resp = await client.get(
                    f"{INCIDENT_MGMT_URL}/incidents",
                    params={"limit": 10},
                )
                incidents_resp.raise_for_status()
                incidents = incidents_resp.json()

                platform_view["alerts"] = alerts
                platform_view["incidents"] = incidents
                platform_view["platform_reachable"] = True
                platform_view["last_poll_error"] = None

                # Update pipeline stage lights based on what we actually see
                if any(a.get("alert_id") == pipeline_state["last_alert_id"] for a in alerts):
                    pipeline_state["stage_alert_persisted"] = "active"

                triggering_alert_row_ids = {
                    a["id"] for a in alerts
                    if a.get("alert_id") == pipeline_state["last_alert_id"]
                }
                if any(i.get("alert_id") in triggering_alert_row_ids for i in incidents):
                    pipeline_state["stage_incident_created"] = "active"

            except Exception as e:
                platform_view["platform_reachable"] = False
                platform_view["last_poll_error"] = str(e)
                logger.warning("platform_poll_failed error=%s", e)

            await asyncio.sleep(PLATFORM_POLL_INTERVAL_S)


# ─── Ingestion + detection (unchanged from original stub) ───────

async def ensure_consumer_group(redis_client: aioredis.Redis) -> None:
    try:
        await redis_client.xgroup_create(
            name=STREAM, groupname=GROUP, id="0", mkstream=True,
        )
        logger.info("consumer_group_created stream=%s group=%s", STREAM, GROUP)
    except ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            logger.info("consumer_group_exists stream=%s group=%s", STREAM, GROUP)
        else:
            raise


def count_people(model: YOLO, frame: np.ndarray) -> int:
    results = model(frame, conf=CONFIDENCE, classes=[0], verbose=False)
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
    payload = fields.get("data")
    if not payload:
        logger.warning("frame_event_missing_data message_id=%s", message_id)
        return

    event = json.loads(payload)
    frame_seq = event["frame_seq"]
    camera_id = event["camera_id"]
    frame_reference = event["frame_reference"]
    frame_provider = event["frame_provider"]

    pipeline_state["stage_ingestion"] = "active"

    if frame_provider != "redis":
        logger.warning(
            "unexpected_frame_provider camera_id=%s frame_seq=%d provider=%s",
            camera_id, frame_seq, frame_provider,
        )
        return

    fetch_start = time.perf_counter()
    jpeg_bytes = await redis_client.get(frame_reference)
    fetch_ms = (time.perf_counter() - fetch_start) * 1000

    if jpeg_bytes is None:
        latest_result["cache_misses"] += 1
        logger.warning("frame_cache_miss camera_id=%s frame_seq=%d key=%s",
                       camera_id, frame_seq, frame_reference)
        return

    jpeg_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(jpeg_array, cv2.IMREAD_COLOR)
    if frame is None:
        logger.error("frame_decode_failed camera_id=%s frame_seq=%d", camera_id, frame_seq)
        return

    pipeline_state["stage_detection"] = "active"
    detection_start = time.perf_counter()
    people = count_people(model, frame)
    detection_ms = (time.perf_counter() - detection_start) * 1000

    height, width = frame.shape[:2]
    latest_result.update({
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
    })

    logger.info(
        "uc1_frame_processed camera_id=%s frame_seq=%d people=%d "
        "resolution=%dx%d jpeg_bytes=%d cache=hit "
        "cache_fetch_ms=%.2f detection_ms=%.2f",
        camera_id, frame_seq, people, width, height,
        len(jpeg_bytes), fetch_ms, detection_ms,
    )

    # ── This is the new bit — cross into the Platform layer ──
    await maybe_fire_alert(redis_client, people, frame_seq)


async def consume(redis_client: aioredis.Redis, model: YOLO) -> None:
    await ensure_consumer_group(redis_client)
    logger.info(
        "uc1_v2_consumer_started camera_id=%s stream=%s group=%s consumer=%s",
        CAMERA_ID, STREAM, GROUP, CONSUMER,
    )

    while True:
        try:
            messages = await redis_client.xreadgroup(
                groupname=GROUP, consumername=CONSUMER,
                streams={STREAM: ">"}, count=1, block=5000,
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
                        await process_message(redis_client, model, message_id, decoded_fields)
                        await redis_client.xack(STREAM, GROUP, message_id)
                    except Exception:
                        logger.exception("frame_processing_failed message_id=%s", message_id)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("uc1_v2_consumer_error")
            await asyncio.sleep(2)


# ─── App lifecycle ────────────────────────────────────────────

consumer_task: asyncio.Task | None = None
poller_task: asyncio.Task | None = None
redis_client: aioredis.Redis | None = None
model: YOLO | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_task, poller_task, redis_client, model

    logger.info("uc1_v2_platform_demo_starting camera_id=%s", CAMERA_ID)
    logger.info("loading_yolo_model model=%s", MODEL_PATH)
    model = YOLO(MODEL_PATH)

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    await redis_client.ping()
    logger.info("redis_connected")

    latest_result["status"] = "running"

    consumer_task = asyncio.create_task(consume(redis_client, model))
    poller_task = asyncio.create_task(poll_platform_state())

    yield

    for task in (consumer_task, poller_task):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    if redis_client:
        await redis_client.aclose()


app = FastAPI(title="Innovision UC1-v2 — Platform Demo", lifespan=lifespan)


@app.get("/api/latest")
async def get_latest():
    return latest_result


@app.get("/api/pipeline")
async def get_pipeline():
    return pipeline_state


@app.get("/api/platform")
async def get_platform():
    return platform_view


@app.get("/health")
async def health():
    return {"status": "healthy", "camera_id": CAMERA_ID}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
    <title>Innovision UC1 — Platform Demo</title>
    <style>
        body { margin:0; background:#0d0d0d; color:#eee; font-family:Arial, sans-serif; }
        .wrap { max-width: 1100px; margin: 40px auto; padding: 0 20px; }
        h1 { text-align:center; margin-bottom:4px; }
        .subtitle { text-align:center; color:#888; margin-bottom:30px; }

        .grid2 { display:grid; grid-template-columns: 1fr 1fr; gap:24px; }

        .panel { background:#1b1b1b; border-radius:14px; padding:24px; }
        .panel h2 { margin-top:0; font-size:15px; color:#999; text-transform:uppercase; letter-spacing:1px; }

        .label { text-align:center; color:#999; font-size:16px; }
        #people { text-align:center; font-size:90px; font-weight:bold; margin:10px 0 25px; }

        .stats { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
        .stat { background:#252525; padding:14px; border-radius:10px; }
        .title { color:#888; font-size:12px; }
        .value { margin-top:6px; font-size:16px; }

        /* Pipeline visualization */
        .pipeline { display:flex; flex-direction:column; gap:10px; margin-top: 10px; }
        .stage { display:flex; align-items:center; gap:12px; padding:12px 14px;
                 background:#252525; border-radius:10px; border-left:4px solid #444;
                 transition: all 0.3s ease; }
        .stage.active { border-left-color:#4ade80; background:#1c2b20; }
        .dot { width:12px; height:12px; border-radius:50%; background:#444; flex-shrink:0; }
        .stage.active .dot { background:#4ade80; box-shadow:0 0 8px #4ade80; }
        .stage-label { font-size:14px; }
        .stage-sub { color:#777; font-size:11px; margin-left:auto; }

        .feed { max-height: 260px; overflow-y:auto; margin-top:10px; }
        .feed-item { background:#252525; border-radius:8px; padding:10px 12px; margin-bottom:8px; font-size:13px; }
        .feed-item .sev { display:inline-block; padding:2px 8px; border-radius:4px; font-size:10px; font-weight:bold; margin-right:8px; }
        .sev-critical { background:#dc2626; }
        .sev-high { background:#d97706; }
        .feed-empty { color:#666; font-size:13px; text-align:center; padding:20px 0; }

        .platform-status { text-align:center; margin-top:12px; font-size:12px; }
        .platform-status.ok { color:#4ade80; }
        .platform-status.bad { color:#dc2626; }
    </style>
</head>
<body>
<div class="wrap">
    <h1>INNOVISION — UC1 → PLATFORM SERVICES</h1>
    <div class="subtitle">Ingestion → Detection → Alert Management → Incident Management, live</div>

    <div class="grid2">

        <div class="panel">
            <h2>UC1 Detection</h2>
            <div class="label">PEOPLE DETECTED</div>
            <div id="people">--</div>
            <div class="stats">
                <div class="stat"><div class="title">FRAME</div><div id="frame" class="value">--</div></div>
                <div class="stat"><div class="title">RESOLUTION</div><div id="resolution" class="value">--</div></div>
                <div class="stat"><div class="title">CACHE FETCH</div><div id="fetch" class="value">--</div></div>
                <div class="stat"><div class="title">DETECTION</div><div id="detection" class="value">--</div></div>
                <div class="stat"><div class="title">PROCESSED</div><div id="processed" class="value">0</div></div>
                <div class="stat"><div class="title">STATUS</div><div id="status" class="value">STARTING</div></div>
            </div>
        </div>

        <div class="panel">
            <h2>Pipeline — Ingestion to Platform</h2>
            <div class="pipeline" id="pipeline"></div>
        </div>

    </div>

    <div class="grid2" style="margin-top:24px;">

        <div class="panel">
            <h2>Alert Management — Real Alerts (source=uc1)</h2>
            <div id="alertFeed" class="feed"><div class="feed-empty">No alerts yet</div></div>
        </div>

        <div class="panel">
            <h2>Incident Management — Auto-Created Incidents</h2>
            <div id="incidentFeed" class="feed"><div class="feed-empty">No incidents yet</div></div>
            <div id="platformStatus" class="platform-status">checking platform...</div>
        </div>

    </div>

</div>

<script>
const STAGES = [
    ["stage_ingestion", "Ingestion — frame received", "frames:{camera_id}"],
    ["stage_detection", "UC1 Detection — YOLOv8n", "person count computed"],
    ["stage_alert_published", "AlertEvent published", "alerts:live stream"],
    ["stage_alert_persisted", "Alert Management — persisted", "alerts table"],
    ["stage_incident_created", "Incident Management — created", "incidents table"],
];

function renderPipeline(state) {
    const el = document.getElementById("pipeline");
    el.innerHTML = STAGES.map(([key, label, sub]) => {
        const active = state[key] === "active";
        return `<div class="stage ${active ? 'active' : ''}">
                    <div class="dot"></div>
                    <div class="stage-label">${label}</div>
                    <div class="stage-sub">${sub}</div>
                </div>`;
    }).join("");
}

function renderAlerts(alerts) {
    const el = document.getElementById("alertFeed");
    if (!alerts || alerts.length === 0) {
        el.innerHTML = '<div class="feed-empty">No alerts yet</div>';
        return;
    }
    el.innerHTML = alerts.map(a => `
        <div class="feed-item">
            <span class="sev sev-${a.severity}">${a.severity.toUpperCase()}</span>
            ${a.title}
            <div style="color:#888; margin-top:4px;">status: ${a.status} · ${new Date(a.created_at).toLocaleTimeString()}</div>
        </div>
    `).join("");
}

function renderIncidents(incidents) {
    const el = document.getElementById("incidentFeed");
    if (!incidents || incidents.length === 0) {
        el.innerHTML = '<div class="feed-empty">No incidents yet</div>';
        return;
    }
    el.innerHTML = incidents.map(i => `
        <div class="feed-item">
            <strong>${i.title}</strong>
            <div style="color:#888; margin-top:4px;">status: ${i.status} · created ${new Date(i.created_at).toLocaleTimeString()}</div>
        </div>
    `).join("");
}

async function update() {
    try {
        const [latest, pipeline, platform] = await Promise.all([
            fetch("/api/latest").then(r => r.json()),
            fetch("/api/pipeline").then(r => r.json()),
            fetch("/api/platform").then(r => r.json()),
        ]);

        document.getElementById("people").innerText = latest.people ?? "--";
        document.getElementById("frame").innerText = latest.frame_seq ?? "--";
        document.getElementById("resolution").innerText = latest.resolution ?? "--";
        document.getElementById("fetch").innerText = latest.cache_fetch_ms != null ? latest.cache_fetch_ms + " ms" : "--";
        document.getElementById("detection").innerText = latest.detection_ms != null ? latest.detection_ms + " ms" : "--";
        document.getElementById("processed").innerText = latest.frames_processed ?? 0;
        document.getElementById("status").innerText = (latest.status ?? "unknown").toUpperCase();

        renderPipeline(pipeline);
        renderAlerts(platform.alerts);
        renderIncidents(platform.incidents);

        const statusEl = document.getElementById("platformStatus");
        if (platform.platform_reachable) {
            statusEl.className = "platform-status ok";
            statusEl.innerText = "● Platform services reachable";
        } else {
            statusEl.className = "platform-status bad";
            statusEl.innerText = "● Platform unreachable — " + (platform.last_poll_error || "unknown error");
        }

    } catch (error) {
        document.getElementById("status").innerText = "DISCONNECTED";
    }
}

update();
setInterval(update, 500);
</script>
</body>
</html>
"""