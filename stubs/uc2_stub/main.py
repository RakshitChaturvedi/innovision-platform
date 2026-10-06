"""
main.py — UC2 Analytics Service entry point.

Replaces the old stub with a real Redis stream consumer + FastAPI
health/metrics server. Wires the CV engine pipeline into the platform.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import cv2
import numpy as np
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, "/app")

from shared.contracts.frame_event import FrameEvent
from shared.contracts.enums import FrameProvider
from shared.platform_client.alert_publisher import AlertPublisher

from stubs.uc2_stub.consumer import consume_loop
from stubs.uc2_stub.frame_fetcher import fetch_frame
from stubs.uc2_stub.alert_builder import build_alert_from_detection

# Import CV engine
from stubs.uc2_stub.cv_engine.pipeline import DetectionPipeline, DetectionResult
from stubs.uc2_stub.cv_engine.engine import YOLOEngine

# ── Logging ───────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("uc2.main")

# ── Configuration ─────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}")

# ── In-memory Metrics (FIX #6) ───────────────────────────────────

metrics = {
    "frames_consumed": 0,
    "alerts_published": 0,
    "alerts_failed": 0,
    "active_detections": 0,
}

# ── Per-camera State ─────────────────────────────────────────────

_camera_state: dict[str, dict] = {}
_camera_state_lock = threading.Lock()

# ── In-memory Latest Detections Store ─────────────────────────────
latest_detections: dict[str, dict] = {}
_latest_detections_lock = threading.Lock()

# ── In-memory Latest Annotated Frames Store ───────────────────────
latest_annotated_frames: dict[str, bytes] = {}
_annotated_frames_lock = threading.Lock()

# ── ML Pipeline (lazy loaded) ────────────────────────────────────

_pipeline: DetectionPipeline | None = None
_pipeline_loaded = False
_pipeline_lock = threading.Lock()


def _load_pipeline():
    """Load the detection pipeline (YOLO engine) in a background thread."""
    global _pipeline, _pipeline_loaded

    with _pipeline_lock:
        if _pipeline_loaded:
            return

        try:
            logger.info("loading_uc2_detection_pipeline")
            _pipeline = DetectionPipeline()
            _pipeline_loaded = True
            logger.info("uc2_detection_pipeline_loaded")
        except Exception as e:
            logger.error("uc2_pipeline_load_failed error=%s", e, exc_info=True)


# ── Per-Camera State Management ──────────────────────────────────

def _get_or_create_camera_state(camera_id: str) -> dict:
    """Get or initialize per-camera tracking state."""
    with _camera_state_lock:
        if camera_id not in _camera_state:
            _camera_state[camera_id] = {
                "prev_frame": None,
                "frame_counter": 0,
                # Dedup: detection_key -> set of alert_types already emitted
                "alerts_emitted": {},
                "alert_cooldowns": {},
            }
        return _camera_state[camera_id]


# ── Frame Processing Pipeline ────────────────────────────────────

ALERT_COOLDOWN_S = float(os.getenv("UC2_ALERT_COOLDOWN_S", "30.0"))


async def process_frame(
    frame_event: FrameEvent,
    redis_client: aioredis.Redis,
    publisher: AlertPublisher,
) -> None:
    """
    Full frame processing pipeline:
    1. Fetch frame (Redis → MinIO fallback)
    2. Run through 6-stage CV engine pipeline
    3. Emit alerts for confirmed detections via AlertPublisher
    """
    camera_id = str(frame_event.camera_id)
    cam_state = _get_or_create_camera_state(camera_id)

    # ── 1. Fetch frame ────────────────────────────────────────────
    frame = await fetch_frame(redis_client, frame_event)
    if frame is None:
        return

    # ── 2. Wait for pipeline ──────────────────────────────────────
    if not _pipeline_loaded:
        threading.Thread(target=_load_pipeline, daemon=True).start()
        return

    if _pipeline is None:
        return

    cam_state["frame_counter"] += 1
    frame_counter = cam_state["frame_counter"]
    prev_frame = cam_state.get("prev_frame")

    # ── 3. Run detection pipeline ─────────────────────────────────
    result: DetectionResult = _pipeline.process_frame(
        camera_id=camera_id,
        frame_seq=frame_event.frame_seq,
        frame_bgr=frame,
        prev_frame_bgr=prev_frame,
    )

    # Store current frame for next iteration's temporal comparison
    cam_state["prev_frame"] = frame

    # ── Update in-memory latest detections cache ──────────────────
    h, w = frame.shape[:2]
    dets_payload = []
    for idx, det in enumerate(result.confirmed_detections):
        x1 = float(max(0.0, min(1.0, round(float(det.bbox["x1"]) / float(w), 4))))
        y1 = float(max(0.0, min(1.0, round(float(det.bbox["y1"]) / float(h), 4))))
        x2 = float(max(0.0, min(1.0, round(float(det.bbox["x2"]) / float(w), 4))))
        y2 = float(max(0.0, min(1.0, round(float(det.bbox["y2"]) / float(h), 4))))
        is_fire = det.detection_type.lower() == "fire"
        is_sparks = "spark" in det.detection_type.lower()
        if is_fire:
            lbl = "FIRE"
            clr = "#FF0000"
        elif is_sparks:
            lbl = "SPARKS"
            clr = "#FFFF00"
        else:
            lbl = "SMOKE"
            clr = "#FFA500"

        dets_payload.append({
            "track_id": int(idx + 1),
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "label": lbl,
            "color": clr,
            "metadata": {
                "confidence": float(round(float(det.final_confidence), 4)),
                "raw_class": det.detection_type,
                "zone": str(det.zone.zone_name),
                "severity": str(det.severity.value),
            },
        })

    with _latest_detections_lock:
        latest_detections[camera_id] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "camera_id": camera_id,
            "detections": dets_payload,
            "zones": [],
        }

    # Render annotations directly onto frame for video stream
    annotated_bgr = frame.copy()
    for d in dets_payload:
        bx1 = max(0, min(w - 1, int(round(d["bbox"]["x1"] * w))))
        by1 = max(0, min(h - 1, int(round(d["bbox"]["y1"] * h))))
        bx2 = max(0, min(w - 1, int(round(d["bbox"]["x2"] * w))))
        by2 = max(0, min(h - 1, int(round(d["bbox"]["y2"] * h))))
        c_bgr = (0, 0, 255) if d["label"] == "FIRE" else ((0, 255, 255) if d["label"] == "SPARKS" else (0, 165, 255))
        cv2.rectangle(annotated_bgr, (bx1, by1), (bx2, by2), c_bgr, 2)
        badge_text = f"{d['label']} {int(d['metadata']['confidence']*100)}%"
        (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ty = max(by1 - 5, th + 5)
        cv2.rectangle(annotated_bgr, (bx1, ty - th - 4), (bx1 + tw + 6, ty + 2), c_bgr, -1)
        cv2.putText(annotated_bgr, badge_text, (bx1 + 3, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    ret, buf = cv2.imencode(".jpg", annotated_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if ret:
        with _annotated_frames_lock:
            latest_annotated_frames[camera_id] = buf.tobytes()

    # ── 4. Emit alerts for confirmed detections ───────────────────
    alert_cooldowns = cam_state["alert_cooldowns"]
    now = time.time()

    for det in result.confirmed_detections:
        # Cooldown dedup: avoid re-alerting same zone+type within cooldown
        cooldown_key = f"{det.detection_type}:{det.zone.zone_id}"
        last_alert_time = alert_cooldowns.get(cooldown_key, 0.0)

        if (now - last_alert_time) < ALERT_COOLDOWN_S:
            logger.debug(
                "alert_cooldown_skip type=%s zone=%s elapsed=%.1fs",
                det.detection_type,
                det.zone.zone_id,
                now - last_alert_time,
            )
            continue

        # Frame reference for alerts
        fr_ref = frame_event.frame_reference
        fr_prov = frame_event.frame_provider

        alert = build_alert_from_detection(
            camera_id=frame_event.camera_id,
            source_event_id=frame_event.event_id,
            detection_type=det.detection_type,
            severity=det.severity,
            final_confidence=det.final_confidence,
            bbox=det.bbox,
            zone_name=det.zone.zone_name,
            zone_id=det.zone.zone_id,
            verification_score=det.verification_score,
            persistence_count=det.persistence_count,
            verification_details=det.verification_details,
            detection_metadata=det.metadata,
            frame_reference=fr_ref,
            frame_provider=fr_prov,
            evidence_key=fr_ref,
            evidence_bucket="innovision-frames" if fr_ref else None,
        )

        success = await publisher.publish(alert)
        if success:
            metrics["alerts_published"] += 1
            alert_cooldowns[cooldown_key] = now
            logger.info(
                "alert_published type=%s camera=%s zone=%s conf=%.2f severity=%s",
                alert.alert_type,
                camera_id,
                det.zone.zone_name,
                det.final_confidence,
                det.severity.value,
            )
        else:
            metrics["alerts_failed"] += 1

    # Update active detections metric
    total_active = 0
    if _pipeline is not None:
        for cam_id in _camera_state:
            tracks = _pipeline.temporal_tracker.get_active_tracks(cam_id)
            total_active += len(tracks)
    metrics["active_detections"] = total_active


# ── Application Lifecycle ────────────────────────────────────────

consumer_task: asyncio.Task | None = None
redis_client: aioredis.Redis | None = None
publisher: AlertPublisher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_task, redis_client, publisher

    logger.info("uc2_analytics_starting")

    # 1. Redis
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    await redis_client.ping()
    logger.info("redis_connected")

    # 2. AlertPublisher (FIX #4)
    publisher = AlertPublisher(redis_client)

    # 3. Load ML pipeline in background
    threading.Thread(target=_load_pipeline, daemon=True).start()

    # 4. Start consumer loop
    async def _frame_callback(frame_event: FrameEvent):
        await process_frame(frame_event, redis_client, publisher)

    consumer_task = asyncio.create_task(
        consume_loop(redis_client, _frame_callback, metrics)
    )

    logger.info("uc2_analytics_started")
    yield

    # Shutdown
    logger.info("uc2_analytics_shutting_down")

    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    if redis_client:
        await redis_client.aclose()

    logger.info("uc2_analytics_stopped")


# ── FastAPI Application (FIX #6) ─────────────────────────────────

app = FastAPI(
    title="UC2 Analytics Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "uc2_analytics"}


@app.get("/metrics")
async def get_metrics():
    return {
        "frames_consumed": metrics["frames_consumed"],
        "alerts_published": metrics["alerts_published"],
        "alerts_failed": metrics["alerts_failed"],
        "active_detections": metrics["active_detections"],
    }


@app.get("/uc2/cameras/{camera_id}/latest-detections")
@app.get("/cameras/{camera_id}/latest-detections")
async def get_latest_detections_endpoint(camera_id: str):
    with _latest_detections_lock:
        if camera_id in latest_detections:
            return latest_detections[camera_id]
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": camera_id,
        "detections": [],
        "zones": [],
    }


@app.get("/uc2/cameras/{camera_id}/annotated-stream")
@app.get("/cameras/{camera_id}/annotated-stream")
async def get_annotated_stream(camera_id: str):
    async def frame_generator():
        while True:
            with _annotated_frames_lock:
                frame_bytes = latest_annotated_frames.get(camera_id)
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            await asyncio.sleep(0.08)
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8022)