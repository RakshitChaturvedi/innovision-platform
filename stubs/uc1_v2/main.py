"""
UC1-v2 platform integration demo.
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
from fastapi.responses import HTMLResponse, StreamingResponse

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

_last_alert_fired_at: float = 0.0
latest_frame_bytes: bytes | None = None  # Global for the video stream

# ─── Alert publishing ────────────────────────────────────────────

async def maybe_fire_alert(redis_client: aioredis.Redis, people: int, frame_seq: int) -> None:
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
        "description": f"UC1 detected {people} persons in frame (threshold: {PEOPLE_THRESHOLD}). Frame sequence {frame_seq}.",
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

    logger.warning("alert_published_to_platform alert_id=%s people=%d severity=%s", alert_id, people, severity)

# ─── Platform poller ────────────────────────────────────────────

async def poll_platform_state() -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            try:
                alerts_resp = await client.get(f"{ALERT_MGMT_URL}/alerts", params={"source_uc": "uc1", "limit": 10})
                alerts_resp.raise_for_status()
                alerts = alerts_resp.json()

                incidents_resp = await client.get(f"{INCIDENT_MGMT_URL}/incidents", params={"limit": 10})
                incidents_resp.raise_for_status()
                incidents = incidents_resp.json()

                platform_view["alerts"] = alerts
                platform_view["incidents"] = incidents
                platform_view["platform_reachable"] = True
                platform_view["last_poll_error"] = None

                if any(a.get("alert_id") == pipeline_state["last_alert_id"] for a in alerts):
                    pipeline_state["stage_alert_persisted"] = "active"

                triggering_alert_row_ids = {a["id"] for a in alerts if a.get("alert_id") == pipeline_state["last_alert_id"]}
                if any(i.get("alert_id") in triggering_alert_row_ids for i in incidents):
                    pipeline_state["stage_incident_created"] = "active"

            except Exception as e:
                platform_view["platform_reachable"] = False
                platform_view["last_poll_error"] = str(e)

            await asyncio.sleep(PLATFORM_POLL_INTERVAL_S)

# ─── Detection Logic ────────────────────────────────────────────

async def ensure_consumer_group(redis_client: aioredis.Redis) -> None:
    try:
        await redis_client.xgroup_create(name=STREAM, groupname=GROUP, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise

def count_people(model: YOLO, frame: np.ndarray) -> tuple[int, np.ndarray]:
    results = model(frame, conf=CONFIDENCE, classes=[0], verbose=False)
    count = 0
    for result in results:
        if result.boxes is not None:
            count += len(result.boxes)
    # Draw boxes on frame
    annotated_frame = results[0].plot() if len(results) > 0 else frame
    return count, annotated_frame

async def process_message(redis_client: aioredis.Redis, model: YOLO, message_id: str, fields: dict[str, str]) -> None:
    global latest_frame_bytes

    payload = fields.get("data")
    if not payload:
        return

    event = json.loads(payload)
    frame_seq = event["frame_seq"]
    camera_id = event["camera_id"]
    frame_reference = event["frame_reference"]
    frame_provider = event["frame_provider"]

    pipeline_state["stage_ingestion"] = "active"

    if frame_provider != "redis":
        return

    fetch_start = time.perf_counter()
    jpeg_bytes = await redis_client.get(frame_reference)
    fetch_ms = (time.perf_counter() - fetch_start) * 1000

    if jpeg_bytes is None:
        latest_result["cache_misses"] += 1
        return

    jpeg_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(jpeg_array, cv2.IMREAD_COLOR)
    if frame is None:
        return

    pipeline_state["stage_detection"] = "active"
    detection_start = time.perf_counter()
    
    # Process YOLO and get annotated image
    people, annotated_frame = count_people(model, frame)
    detection_ms = (time.perf_counter() - detection_start) * 1000

    # Encode for the Web stream
    _, buffer = cv2.imencode('.jpg', annotated_frame)
    latest_frame_bytes = buffer.tobytes()

    height, width = frame.shape[:2]
    latest_result.update({
        "status": "running", "camera_id": camera_id, "frame_seq": frame_seq, "people": people,
        "resolution": f"{width}x{height}", "jpeg_bytes": len(jpeg_bytes), "cache": "hit",
        "cache_fetch_ms": round(fetch_ms, 2), "detection_ms": round(detection_ms, 2),
        "frames_processed": latest_result["frames_processed"] + 1, "last_update": time.time(),
    })

    await maybe_fire_alert(redis_client, people, frame_seq)

async def consume(redis_client: aioredis.Redis, model: YOLO) -> None:
    await ensure_consumer_group(redis_client)
    while True:
        try:
            messages = await redis_client.xreadgroup(
                groupname=GROUP, consumername=CONSUMER, streams={STREAM: ">"}, count=1, block=5000,
            )
            if not messages:
                continue
            for _, entries in messages:
                for message_id, fields in entries:
                    if isinstance(message_id, bytes): message_id = message_id.decode()
                    decoded_fields = {k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v for k, v in fields.items()}
                    try:
                        await process_message(redis_client, model, message_id, decoded_fields)
                        await redis_client.xack(STREAM, GROUP, message_id)
                    except Exception:
                        logger.exception("frame_processing_failed")
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(2)

# ─── App lifecycle ────────────────────────────────────────────

consumer_task: asyncio.Task | None = None
poller_task: asyncio.Task | None = None
redis_client: aioredis.Redis | None = None
model: YOLO | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_task, poller_task, redis_client, model
    model = YOLO(MODEL_PATH)
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    await redis_client.ping()
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
async def get_latest(): return latest_result

@app.get("/api/pipeline")
async def get_pipeline(): return pipeline_state

@app.get("/api/platform")
async def get_platform(): return platform_view

@app.get("/health")
async def health(): return {"status": "healthy", "camera_id": CAMERA_ID}

# ─── Video Streaming Endpoints ─────────────────────────────────

async def frame_generator():
    """Generates the MJPEG stream for the browser."""
    while True:
        if latest_frame_bytes is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + latest_frame_bytes + b'\r\n')
        await asyncio.sleep(0.08) 

@app.get("/api/video")
async def video_feed():
    """Endpoint serving the live annotated video feed."""
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


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
        .pipeline { display:flex; flex-direction:column; gap:10px; margin-top: 10px; }
        .stage { display:flex; align-items:center; gap:12px; padding:12px 14px; background:#252525; border-radius:10px; border-left:4px solid #444; transition: all 0.3s ease; }
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

    <div class="panel" style="margin-bottom: 24px; text-align: center;">
        <h2>Live YOLOv8 Detection Feed</h2>
        <img src="/api/video" alt="Live Camera Feed" style="max-width: 100%; border-radius: 8px; border: 1px solid #444;" />
    </div>

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