"""
UC3 — PPE Compliance & Industrial Safety Monitoring Service.

Consumes camera frames from Redis Stream `frames:{camera_id}`,
performs computer-vision worker detection and PPE verification (helmet & high-vis jacket),
uploads violation evidence snapshots to MinIO, and publishes canonical AlertEvents to `alerts:live`.
Also serves live MJPEG preview and reporting metrics on port 8031.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import cv2
import numpy as np
import redis.asyncio as aioredis
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from minio import Minio

sys.path.insert(0, "/app")
from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("innovision.uc3.worker")

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
TEST_CAMERA_ID = UUID(os.getenv("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000003"))
CAMERA_ID = str(TEST_CAMERA_ID)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "changeme")
STREAM_GROUP = "uc3_ppe_group"
STREAM_KEY = f"frames:{CAMERA_ID}"
PORT = int(os.getenv("UC3_PORT", "8031"))

UC3_SCENARIOS = [
    {
        "severity": AlertSeverity.HIGH,
        "alert_type": "ppe_violation",
        "title": "[UC3] PPE Violation — Missing Helmet",
        "description": "Worker detected in operational zone without required hard hat / helmet.",
        "metadata": {"violation_type": "no_helmet", "confidence": 0.91, "zone": "Zone-C"},
    },
    {
        "severity": AlertSeverity.MEDIUM,
        "alert_type": "ppe_violation",
        "title": "[UC3] PPE Violation — Missing High-Vis Vest",
        "description": "Worker detected in transit aisle without required reflective safety vest.",
        "metadata": {"violation_type": "no_vest", "confidence": 0.88, "zone": "Zone-A"},
    },
]

# ── Metrics & State ─────────────────────────────────────────────────────────

class UC3State:
    def __init__(self):
        self.frames_processed = 0
        self.workers_detected = 0
        self.violations_detected = 0
        self.alerts_published = 0
        self.latest_frame_jpeg: Optional[bytes] = None
        self.latest_compliance_rate: float = 1.0
        self.last_alert_time: float = 0.0
        self.running = True

state = UC3State()


# ── Computer Vision PPE Detector ───────────────────────────────────────────

def detect_ppe_compliance(frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
    """
    Detect workers and inspect PPE compliance (helmet & high-visibility safety jacket).
    Uses color-space segmentation (HSV) and morphological gradient analysis.
    """
    h, w = frame_bgr.shape[:2]
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    # 1. Detect candidate worker regions via foreground contrast
    # Use adaptive thresholding and morphology to detect person silhouettes
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 10))
    morphed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(morphed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    min_area = (h * w) * 0.015  # At least 1.5% of frame
    max_area = (h * w) * 0.40

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if min_area <= area <= max_area:
            x, y, cw, ch = cv2.boundingRect(cnt)
            aspect_ratio = ch / float(cw)
            if 1.2 <= aspect_ratio <= 3.8:  # Vertical human aspect ratio
                candidates.append((x, y, x + cw, y + ch))

    # If no candidate contour found, define a standard inspection ROI
    if not candidates:
        cx1, cy1 = int(w * 0.25), int(h * 0.20)
        cx2, cy2 = int(w * 0.65), int(h * 0.85)
        candidates.append((cx1, cy1, cx2, cy2))

    inspections = []
    for (x1, y1, x2, y2) in candidates[:4]:
        box_h = y2 - y1
        box_w = x2 - x1

        # Head region: Top 25% of bounding box
        head_roi_hsv = hsv[y1 : y1 + int(box_h * 0.28), x1:x2]
        # Torso region: Middle 45% of bounding box
        torso_roi_hsv = hsv[y1 + int(box_h * 0.25) : y1 + int(box_h * 0.70), x1:x2]

        # Check for safety helmet (Yellow, White, Blue, Orange in HSV)
        # Yellow helmet mask: H in [20, 35], S in [100, 255], V in [100, 255]
        yellow_mask = cv2.inRange(head_roi_hsv, np.array([18, 90, 90]), np.array([36, 255, 255]))
        # White helmet mask: Low saturation, high value
        white_mask = cv2.inRange(head_roi_hsv, np.array([0, 0, 180]), np.array([180, 45, 255]))
        helmet_pixels = cv2.countNonZero(yellow_mask) + cv2.countNonZero(white_mask)
        head_area = max(1, head_roi_hsv.shape[0] * head_roi_hsv.shape[1])
        has_helmet = (helmet_pixels / float(head_area)) >= 0.08

        # Check for safety vest (High-vis fluorescent yellow/orange)
        vest_mask = cv2.inRange(torso_roi_hsv, np.array([12, 100, 100]), np.array([38, 255, 255]))
        vest_pixels = cv2.countNonZero(vest_mask)
        torso_area = max(1, torso_roi_hsv.shape[0] * torso_roi_hsv.shape[1])
        has_vest = (vest_pixels / float(torso_area)) >= 0.12

        missing_items = []
        if not has_helmet:
            missing_items.append("helmet")
        if not has_vest:
            missing_items.append("safety_jacket")

        compliance_score = (1.0 if has_helmet else 0.0) * 0.5 + (1.0 if has_vest else 0.0) * 0.5

        inspections.append({
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "has_helmet": has_helmet,
            "has_vest": has_vest,
            "missing_ppe": missing_items,
            "compliance_score": round(compliance_score, 2),
            "is_violation": len(missing_items) > 0,
        })

    return inspections


# ── Background Worker Loop ──────────────────────────────────────────────────

async def run_uc3_worker():
    logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}", decode_responses=False)
    publisher = AlertPublisher(redis_client)

    # Initialize MinIO client
    minio_client = None
    try:
        minio_client = Minio(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    except Exception as e:
        logger.warning(f"MinIO client init warning: {e}")

    # Ensure Redis consumer group
    try:
        await redis_client.xgroup_create(STREAM_KEY, STREAM_GROUP, id="0", mkstream=True)
        logger.info(f"Created consumer group {STREAM_GROUP} on {STREAM_KEY}")
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            pass

    logger.info(f"UC3 Worker active for camera {CAMERA_ID}. Listening on {STREAM_KEY}...")

    while state.running:
        try:
            # 1. Read from Redis frame stream
            messages = await redis_client.xreadgroup(
                groupname=STREAM_GROUP,
                consumername="uc3_worker_1",
                streams={STREAM_KEY: ">"},
                count=5,
                block=1500,
            )

            frame_img = None
            frame_seq = state.frames_processed + 1

            if messages:
                for stream_name, stream_msgs in messages:
                    if stream_msgs:
                        msg_id, msg_data = stream_msgs[-1]  # Take latest frame
                        raw_data = msg_data.get(b"data") or msg_data.get("data")
                        if raw_data:
                            try:
                                payload = json.loads(raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data)
                                ref = payload.get("frame_reference", "")
                                frame_seq = payload.get("frame_seq", frame_seq)
                                if ref.startswith("frame:"):
                                    cached_bytes = await redis_client.get(ref)
                                    if cached_bytes:
                                        nparr = np.frombuffer(cached_bytes, np.uint8)
                                        frame_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                            except Exception as parse_err:
                                logger.debug(f"Frame parse note: {parse_err}")

                        # Acknowledge processed stream messages
                        for m_id, _ in stream_msgs:
                            await redis_client.xack(STREAM_KEY, STREAM_GROUP, m_id)

            # If no frame in stream yet, synthesize or generate inspection frame
            if frame_img is None:
                # Try fetching latest frame key from Ingestion
                latest_bytes = await redis_client.get(f"frame:{CAMERA_ID}:latest")
                if latest_bytes:
                    nparr = np.frombuffer(latest_bytes, np.uint8)
                    frame_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if frame_img is None:
                # Wait briefly for ingestion to populate
                await asyncio.sleep(1.0)
                continue

            state.frames_processed += 1
            h, w = frame_img.shape[:2]
            if w > 640 or h > 480:
                frame_img = cv2.resize(frame_img, (640, 480), interpolation=cv2.INTER_AREA)

            # 2. Run real PPE compliance analysis
            inspections = detect_ppe_compliance(frame_img)
            state.workers_detected += len(inspections)

            annotated = frame_img.copy()
            violation_found = False
            top_violation = None

            for insp in inspections:
                bx = insp["bbox"]
                if insp["is_violation"]:
                    violation_found = True
                    top_violation = insp
                    color = (0, 0, 255)  # Red for violation
                    label = f"VIOLATION: MISSING {','.join(insp['missing_ppe']).upper()}"
                else:
                    color = (0, 255, 0)  # Green for compliant
                    label = "COMPLIANT (HELMET+VEST)"

                cv2.rectangle(annotated, (bx["x1"], bx["y1"]), (bx["x2"], bx["y2"]), color, 2)
                cv2.putText(annotated, label, (bx["x1"], max(20, bx["y1"] - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

            # Store preview JPEG
            ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                state.latest_frame_jpeg = jpeg.tobytes()

            # 3. Handle Alert Triggering with cooldown
            now = time.time()
            if violation_found and (now - state.last_alert_time) >= 15.0:
                state.last_alert_time = now
                state.violations_detected += 1
                state.alerts_published += 1

                # Upload evidence snapshot to MinIO
                evidence_key = f"uc3/evidence/{CAMERA_ID}/{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.jpg"
                if minio_client and ok:
                    try:
                        jpeg_bytes = jpeg.tobytes()
                        minio_client.put_object(
                            "innovision-evidence",
                            evidence_key,
                            io.BytesIO(jpeg_bytes),
                            len(jpeg_bytes),
                            content_type="image/jpeg",
                        )
                    except Exception as minio_err:
                        logger.warning(f"MinIO evidence upload note: {minio_err}")

                # Publish canonical AlertEvent to alerts:live
                alert = AlertEvent(
                    camera_id=UUID(CAMERA_ID),
                    timestamp=datetime.now(timezone.utc),
                    severity=AlertSeverity.HIGH,
                    alert_type="ppe_violation",
                    title="PPE Violation — Missing Safety Equipment",
                    description=f"UC3 / PART: Worker detected without {','.join(top_violation['missing_ppe'])} in Construction Zone A",
                    source_event_id=uuid4(),
                    source_uc=SourceUC.UC3,
                    frame_reference=evidence_key,
                    frame_provider=FrameProvider.MINIO,
                    metadata={
                        "missing_ppe": top_violation["missing_ppe"],
                        "compliance_score": top_violation["compliance_score"],
                        "bbox": top_violation["bbox"],
                        "zone": "Construction Zone A",
                        "frame_seq": frame_seq,
                    },
                )
                try:
                    await publisher.publish(alert)
                    logger.info(f"[UC3 PPE] Published AlertEvent: {alert.title} (missing: {top_violation['missing_ppe']})")
                except Exception as pub_err:
                    logger.error(f"Failed to publish UC3 alert: {pub_err}")

            # Update rolling compliance rate
            if state.workers_detected > 0:
                state.latest_compliance_rate = round(
                    max(0.0, 1.0 - (state.violations_detected / float(max(1, state.workers_detected)))), 2
                )

            await asyncio.sleep(0.1)

        except Exception as loop_err:
            logger.error(f"Error in UC3 processing cycle: {loop_err}")
            await asyncio.sleep(1.0)


# ── FastAPI App & Lifespan ──────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = asyncio.create_task(run_uc3_worker())
    yield
    state.running = False
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="UC3 — PPE Compliance & Safety Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", summary="UC3 Service Health Check")
async def health():
    return {
        "status": "healthy",
        "service": "uc3_worker",
        "use_case": "uc3_ppe_part",
        "camera_id": CAMERA_ID,
        "frames_processed": state.frames_processed,
        "workers_detected": state.workers_detected,
        "violations_detected": state.violations_detected,
        "alerts_published": state.alerts_published,
        "compliance_rate": state.latest_compliance_rate,
    }


@app.get("/uc3/compliance/ppe-summary", summary="Reporting Service PPE Metrics Endpoint")
async def ppe_summary():
    return {
        "service": "uc3_ppe",
        "compliance_score": state.latest_compliance_rate,
        "workers_inspected": state.workers_detected,
        "violations": state.violations_detected,
        "alerts": state.alerts_published,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/preview/{camera_id}", summary="Live MJPEG Stream of UC3 Annotated Camera Feed")
async def uc3_mjpeg_preview(camera_id: str):
    async def _stream():
        while state.running:
            jpeg = state.latest_frame_jpeg
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            await asyncio.sleep(0.1)

    return StreamingResponse(
        _stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("stubs.uc3_stub.main:app", host="0.0.0.0", port=PORT, reload=False)