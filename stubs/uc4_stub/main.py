"""
main.py — UC4 Analytics Service entry point.

Replaces the old timer-loop stub with a real Redis stream consumer + FastAPI
health/metrics server. Wires the CV engine pipeline into the platform.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
import queue
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import cv2
import numpy as np
import redis.asyncio as aioredis
from fastapi import FastAPI

os.environ["FLAGS_use_mkldnn"] = "0"
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "0"
os.environ["FLAGS_use_onednn"] = "0"
try:
    import paddle
    paddle.set_flags({"FLAGS_use_onednn": False, "FLAGS_use_mkldnn": False})
except Exception:
    pass

sys.path.insert(0, "/app")

from shared.contracts.frame_event import FrameEvent
from shared.contracts.enums import FrameProvider
from shared.platform_client.alert_publisher import AlertPublisher

from stubs.uc4_stub.consumer import consume_loop
from stubs.uc4_stub.frame_fetcher import fetch_frame
from stubs.uc4_stub.alert_builder import (
    build_speed_violation_alert,
    build_unauthorized_vehicle_alert,
    build_anpr_read_alert,
)
from stubs.uc4_stub.calibration import get_calibration, close_engine, CameraCalibration

# Import CV engine utilities (do not modify these files)
from stubs.uc4_stub.cv_engine.speed_estimator import SpeedEstimator
from stubs.uc4_stub.cv_engine.utils import (
    YOLO_CLASS_MAP,
    BLACKLISTED_PLATES,
    clean_plate,
    enhance_plate,
    extract_plate_candidates,
    get_mode,
)

# ── Logging ───────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("uc4.main")

# ── Configuration ─────────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}")
SPEED_LIMIT_DEFAULT = float(os.getenv("SPEED_LIMIT_KMH", "30"))
ANPR_CONSENSUS_MIN = int(os.getenv("ANPR_CONSENSUS_MIN", "3"))

# ── In-memory Metrics (FIX #6) ───────────────────────────────────

metrics = {
    "frames_consumed": 0,
    "alerts_published": 0,
    "alerts_failed": 0,
    "active_tracks": 0,
}

# ── Per-camera State (DESIGN DEBT: keyed by camera_id) ───────────

# camera_id -> {active_sessions, speed_estimator, tracker state, ocr_queue, ...}
_camera_state: dict[str, dict] = {}
_camera_state_lock = threading.Lock()

# ── ML Models (lazy loaded) ──────────────────────────────────────

_models_loaded = False
_models_lock = threading.Lock()
_yolo_model = None
_lp_model = None
_ocr_reader = None


def _load_models():
    """Load YOLO + PaddleOCR models in background thread."""
    global _yolo_model, _lp_model, _ocr_reader, _models_loaded

    with _models_lock:
        if _models_loaded:
            return

        try:
            import torch
            from ultralytics import YOLO

            logger.info("loading_ml_models")

            if torch.cuda.is_available() and os.path.exists("yolo11m.engine"):
                _yolo_model = YOLO("yolo11m.engine", task="detect")
            elif torch.cuda.is_available():
                _yolo_model = YOLO("yolo11m.pt")
            else:
                _yolo_model = YOLO("yolo11n.pt")

            if os.path.exists("models/yolov8n_license_plate.pt"):
                try:
                    _lp_model = YOLO("models/yolov8n_license_plate.pt")
                except Exception:
                    _lp_model = None

            from paddleocr import PaddleOCR
            try:
                _ocr_reader = PaddleOCR(use_angle_cls=False, lang="en")
            except Exception:
                try:
                    _ocr_reader = PaddleOCR(lang="en")
                except Exception as e:
                    logger.warning("paddleocr_init_failed error=%s", e)
                    _ocr_reader = None

            _models_loaded = True
            logger.info("ml_models_loaded")
        except Exception as e:
            logger.error("ml_model_load_failed error=%s", e)


# ── OCR Worker Thread ────────────────────────────────────────────

_ocr_queue: queue.Queue = queue.Queue(maxsize=128)
_paddle_lock = threading.Lock()
_NUM_OCR_WORKERS = 2


def _ocr_worker_loop():
    """Background OCR worker — reads from the global OCR queue."""
    while True:
        try:
            item = _ocr_queue.get()
            if item is None:
                break

            tid, crop, active_sessions, camera_id = item

            if tid not in active_sessions:
                _ocr_queue.task_done()
                continue
            if len(active_sessions[tid].get("plate_reads", [])) >= 8:
                _ocr_queue.task_done()
                continue

            if not _models_loaded or _ocr_reader is None:
                _ocr_queue.task_done()
                continue

            plate_crops = []
            if _lp_model:
                try:
                    lp_results = _lp_model(crop, conf=0.25, verbose=False)
                    for r in lp_results:
                        for box in r.boxes:
                            px1, py1, px2, py2 = box.xyxy[0].tolist()
                            w, h = px2 - px1, py2 - py1
                            pad_x, pad_y = int(w * 0.1), int(h * 0.1)
                            px1 = max(0, int(px1) - pad_x)
                            py1 = max(0, int(py1) - pad_y)
                            px2 = min(crop.shape[1], int(px2) + pad_x)
                            py2 = min(crop.shape[0], int(py2) + pad_y)
                            p_crop = crop[py1:py2, px1:px2]
                            if p_crop.size > 0:
                                plate_crops.append(p_crop)
                except Exception:
                    pass

            if not plate_crops:
                plate_crops = extract_plate_candidates(crop)

            for p_crop in plate_crops:
                if p_crop is None or p_crop.size == 0:
                    continue
                enhanced = enhance_plate(p_crop)
                with _paddle_lock:
                    try:
                        result = _ocr_reader.ocr(enhanced)
                    except TypeError:
                        result = _ocr_reader.ocr(enhanced, cls=False)
                    except Exception as err:
                        logger.warning("ocr_call_failed: %s", err)
                        result = None

                if result and result[0]:
                    items_to_process = []
                    first = result[0]
                    if isinstance(first, dict) and "rec_texts" in first:
                        # PaddleX 3.x format: {'rec_texts': [...], 'rec_scores': [...]}
                        texts = first.get("rec_texts", [])
                        scores = first.get("rec_scores", [])
                        for t, s in zip(texts, scores):
                            items_to_process.append((t, s))
                    elif isinstance(first, (list, tuple)):
                        # Classic PaddleOCR format: [[box, (text, prob)], ...]
                        for line in first:
                            if isinstance(line, (list, tuple)) and len(line) >= 2:
                                text_prob = line[1]
                                if isinstance(text_prob, (list, tuple)) and len(text_prob) >= 2:
                                    items_to_process.append((text_prob[0], text_prob[1]))
                                elif isinstance(text_prob, str):
                                    items_to_process.append((text_prob, 0.8))
                            elif isinstance(line, dict):
                                items_to_process.append((
                                    line.get("transcription") or line.get("text") or "",
                                    line.get("score") or 0.8,
                                ))

                    for text, prob in items_to_process:
                        try:
                            if float(prob) > 0.30:
                                cleaned = clean_plate(text)
                                if cleaned and tid in active_sessions:
                                    active_sessions[tid]["plate_reads"].append(cleaned)
                                    active_sessions[tid]["plate_confidences"].append(
                                        float(prob * 100)
                                    )
                                    logger.info("plate_read tracker=%d plate=%s conf=%.1f", tid, cleaned, float(prob * 100))
                        except Exception as parse_err:
                            logger.debug("line_parse_error: %s", parse_err)

            _ocr_queue.task_done()
        except Exception as e:
            logger.error("ocr_worker_error: %s", e)


# Start OCR worker threads (multiple to avoid bottleneck during concurrency spikes)
for _i in range(_NUM_OCR_WORKERS):
    threading.Thread(target=_ocr_worker_loop, daemon=True, name=f"ocr-worker-{_i}").start()


# ── Per-Camera State Management ──────────────────────────────────

def _get_or_create_camera_state(camera_id: str) -> dict:
    """Get or initialize per-camera tracking state."""
    with _camera_state_lock:
        if camera_id not in _camera_state:
            _camera_state[camera_id] = {
                "active_sessions": {},
                "speed_estimator": None,
                "calibration": None,
                "frame_counter": 0,
                "speed_limit": SPEED_LIMIT_DEFAULT,
                # Dedup: tracker_id -> set of alert_types already emitted
                "alerts_emitted": {},
            }
        return _camera_state[camera_id]


async def _setup_speed_estimator(
    camera_id: str,
    frame_width: int,
    frame_height: int,
    cam_state: dict,
) -> None:
    """
    Load calibration from uc4_camera_calibration and create SpeedEstimator.
    If no calibration exists, speed estimation is skipped (logged warning).
    """
    if cam_state.get("speed_estimator") is not None:
        return  # Already configured

    calibration = await get_calibration(UUID(camera_id))
    if calibration is None:
        cam_state["calibration"] = None
        cam_state["speed_estimator"] = None
        return

    cam_state["calibration"] = calibration

    poly = calibration.speed_polygon_normalized
    if poly and len(poly) >= 3:
        # Build 4-point calibration polygon from speed polygon bounding box
        if len(poly) == 4:
            cal_poly = poly
        else:
            xs = [p["x"] for p in poly]
            ys = [p["y"] for p in poly]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            cal_poly = [
                {"x": min_x, "y": min_y},
                {"x": max_x, "y": min_y},
                {"x": max_x, "y": max_y},
                {"x": min_x, "y": max_y},
            ]

        cam_state["speed_estimator"] = SpeedEstimator(
            polygon_normalized=cal_poly,
            distance_meters=calibration.distance_between_lines_meters,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        logger.info(
            "speed_estimator_initialized camera_id=%s distance=%.1fm",
            camera_id,
            calibration.distance_between_lines_meters,
        )
    else:
        logger.warning(
            "calibration_polygon_insufficient camera_id=%s points=%d",
            camera_id,
            len(poly) if poly else 0,
        )


# ── Frame Processing Pipeline ────────────────────────────────────

async def process_frame(
    frame_event: FrameEvent,
    redis_client: aioredis.Redis,
    publisher: AlertPublisher,
) -> None:
    """
    Full frame processing pipeline:
    1. Fetch frame (Redis → MinIO fallback)
    2. Run YOLO detection + tracking
    3. OCR plate reads
    4. Speed estimation (if calibrated)
    5. Emit alerts immediately on detection
    """
    camera_id = str(frame_event.camera_id)
    cam_state = _get_or_create_camera_state(camera_id)

    # ── 1. Fetch frame ────────────────────────────────────────────
    frame = await fetch_frame(redis_client, frame_event)
    if frame is None:
        return

    height, width = frame.shape[:2]

    # ── 2. Initialize speed estimator (first frame) ──────────────
    await _setup_speed_estimator(camera_id, width, height, cam_state)

    # ── 3. Wait for models ───────────────────────────────────────
    if not _models_loaded:
        # Try loading in background thread if not started
        threading.Thread(target=_load_models, daemon=True).start()
        return

    if _yolo_model is None:
        return

    cam_state["frame_counter"] += 1
    frame_counter = cam_state["frame_counter"]
    active_sessions = cam_state["active_sessions"]
    speed_estimator = cam_state.get("speed_estimator")
    speed_limit = cam_state["speed_limit"]
    alerts_emitted = cam_state["alerts_emitted"]

    # ── 4. Run YOLO detection ────────────────────────────────────
    import supervision as sv

    infer_w, infer_h = 640, 360
    scale_x = width / float(infer_w)
    scale_y = height / float(infer_h)

    infer_frame = cv2.resize(frame, (infer_w, infer_h), interpolation=cv2.INTER_LINEAR)
    results = _yolo_model(infer_frame, classes=[1, 2, 3, 5, 7], conf=0.28, imgsz=640, verbose=False)
    raw_detections = sv.Detections.from_ultralytics(results[0])

    # Scale bounding boxes back to full frame
    if raw_detections.xyxy is not None and len(raw_detections.xyxy) > 0:
        raw_detections.xyxy[:, 0] *= scale_x
        raw_detections.xyxy[:, 1] *= scale_y
        raw_detections.xyxy[:, 2] *= scale_x
        raw_detections.xyxy[:, 3] *= scale_y

    # Use ByteTrack — get or create per-camera tracker
    if "tracker" not in cam_state:
        cam_state["tracker"] = sv.ByteTrack()
    tracker = cam_state["tracker"]
    detections = tracker.update_with_detections(raw_detections)

    # ── 5. Process each tracked vehicle ──────────────────────────
    valid_tracks = []
    if detections.tracker_id is not None and len(detections.tracker_id) > 0:
        for idx, tid in enumerate(detections.tracker_id):
            x1, y1, x2, y2 = detections.xyxy[idx]
            x1, y1 = max(0, int(x1)), max(0, int(y1))
            x2, y2 = min(width, int(x2)), min(height, int(y2))
            cls_id = int(detections.class_id[idx]) if detections.class_id is not None else 2
            v_type = YOLO_CLASS_MAP.get(cls_id, "Car")
            valid_tracks.append((int(tid), x1, y1, x2, y2, v_type, idx))

    # ── 6. Update sessions, speeds, OCR ──────────────────────────
    for tid, x1, y1, x2, y2, v_type, det_idx in valid_tracks:
        inst_speed = 0.0
        bottom_center = (int((x1 + x2) / 2), int(y2))

        if speed_estimator:
            safe_fps = 10.0
            inst_speed = speed_estimator.update_and_get_speed(
                tid, bottom_center,
                current_time=frame_counter / safe_fps,
            )
            if inst_speed > 1.0:
                logger.info("vehicle_speed tid=%d type=%s speed=%.1f km/h", tid, v_type, inst_speed)

        if tid not in active_sessions:
            active_sessions[tid] = {
                "plate_reads": [],
                "plate_confidences": [],
                "vehicle_type": v_type,
                "last_seen": frame_counter,
                "max_speed_kmh": inst_speed,
                "first_seen": frame_counter,
            }
        else:
            active_sessions[tid]["last_seen"] = frame_counter
            active_sessions[tid]["vehicle_type"] = v_type
            if inst_speed > active_sessions[tid].get("max_speed_kmh", 0):
                active_sessions[tid]["max_speed_kmh"] = inst_speed

        # OCR queuing — sample every 2 frames or when crop is larger
        last_ocr = active_sessions[tid].get("last_ocr_frame", 0)
        w_box, h_box = x2 - x1, y2 - y1

        if len(active_sessions[tid]["plate_reads"]) < 8:
            if (frame_counter - last_ocr >= 2 or w_box > active_sessions[tid].get("max_w_box", 0) * 1.2):
                if w_box >= 45 and h_box >= 30:
                    crop = frame[y1:y2, x1:x2]
                    if crop.size > 0:
                        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                        sharpness = cv2.Laplacian(gray_crop, cv2.CV_64F).var()
                        if sharpness > 10.0:
                            try:
                                _ocr_queue.put_nowait(
                                    (tid, crop.copy(), active_sessions, camera_id)
                                )
                                active_sessions[tid]["last_ocr_frame"] = frame_counter
                                if w_box > active_sessions[tid].get("max_w_box", 0):
                                    active_sessions[tid]["max_w_box"] = w_box
                            except queue.Full:
                                logger.debug("ocr_queue_full tracker=%d frame=%d", tid, frame_counter)

    # ── 7. Emit alerts immediately on detection ──────────────────
    for tid, x1, y1, x2, y2, v_type, det_idx in valid_tracks:
        session = active_sessions.get(tid)
        if session is None:
            continue

        max_speed = session.get("max_speed_kmh", 0.0)
        plate_reads = session.get("plate_reads", [])
        plate_confs = session.get("plate_confidences", [])
        consensus_plate = get_mode(plate_reads, plate_confs) if plate_reads else None

        # Init dedup set for this tracker
        if tid not in alerts_emitted:
            alerts_emitted[tid] = set()

        # Frame reference for alerts
        fr_ref = frame_event.frame_reference
        fr_prov = frame_event.frame_provider

        # ── Speed violation (with plate-resolution grace period) ──────
        is_speeding = max_speed > speed_limit
        frames_tracked = frame_counter - session.get("first_seen", frame_counter)
        has_plate = bool(consensus_plate and consensus_plate != "UNKNOWN")

        # Grace period: Wait up to 15 frames (~1.5s) for OCR to resolve the plate.
        # If plate is already resolved, fire immediately!
        # If 15 frames passed and no plate was found, fire with UNKNOWN.
        can_emit_speed = is_speeding and (has_plate or frames_tracked >= 15)

        if can_emit_speed and "speed_violation" not in alerts_emitted[tid]:
            plate_display = consensus_plate if has_plate else "UNKNOWN"
            alert = build_speed_violation_alert(
                camera_id=frame_event.camera_id,
                source_event_id=frame_event.event_id,
                tracker_id=tid,
                plate=plate_display,
                speed_kmh=max_speed,
                speed_limit_kmh=speed_limit,
                vehicle_type=v_type,
                frame_reference=fr_ref,
                frame_provider=fr_prov,
            )
            success = await publisher.publish(alert)
            if success:
                metrics["alerts_published"] += 1
                alerts_emitted[tid].add("speed_violation")
                if has_plate:
                    alerts_emitted[tid].add("plate_resolved")
                logger.info(
                    "speed_violation_alert camera=%s tracker=%d speed=%.1f limit=%.0f plate=%s frames_tracked=%d",
                    camera_id, tid, max_speed, speed_limit, plate_display, frames_tracked,
                )
            else:
                metrics["alerts_failed"] += 1

        # ── Speed violation enrichment: if previously emitted as UNKNOWN, and plate is now resolved! ──
        elif (
            is_speeding
            and "speed_violation" in alerts_emitted[tid]
            and "plate_resolved" not in alerts_emitted[tid]
            and has_plate
        ):
            alert = build_speed_violation_alert(
                camera_id=frame_event.camera_id,
                source_event_id=frame_event.event_id,
                tracker_id=tid,
                plate=consensus_plate,
                speed_kmh=max_speed,
                speed_limit_kmh=speed_limit,
                vehicle_type=v_type,
                frame_reference=fr_ref,
                frame_provider=fr_prov,
            )
            success = await publisher.publish(alert)
            if success:
                metrics["alerts_published"] += 1
                alerts_emitted[tid].add("plate_resolved")
                logger.info(
                    "speed_violation_plate_enriched camera=%s tracker=%d speed=%.1f plate=%s",
                    camera_id, tid, max_speed, consensus_plate,
                )

        # ── Unauthorized vehicle (blacklisted plate, dedup) ───
        if (
            consensus_plate
            and consensus_plate in BLACKLISTED_PLATES
            and "unauthorized_vehicle" not in alerts_emitted[tid]
        ):
            alert = build_unauthorized_vehicle_alert(
                camera_id=frame_event.camera_id,
                source_event_id=frame_event.event_id,
                tracker_id=tid,
                plate=consensus_plate,
                vehicle_type=v_type,
                frame_reference=fr_ref,
                frame_provider=fr_prov,
            )
            success = await publisher.publish(alert)
            if success:
                metrics["alerts_published"] += 1
                alerts_emitted[tid].add("unauthorized_vehicle")
                logger.info(
                    "unauthorized_vehicle_alert camera=%s tracker=%d plate=%s",
                    camera_id, tid, consensus_plate,
                )
            else:
                metrics["alerts_failed"] += 1

        # ── ANPR read (consensus ≥ ANPR_CONSENSUS_MIN, dedup) ─
        if (
            consensus_plate
            and len(plate_reads) >= ANPR_CONSENSUS_MIN
            and "anpr_read" not in alerts_emitted[tid]
        ):
            avg_conf = (
                sum(plate_confs) / len(plate_confs) if plate_confs else 0.0
            )
            alert = build_anpr_read_alert(
                camera_id=frame_event.camera_id,
                source_event_id=frame_event.event_id,
                tracker_id=tid,
                plate=consensus_plate,
                confidence=avg_conf,
                vehicle_type=v_type,
                speed_kmh=max_speed,
                frame_reference=fr_ref,
                frame_provider=fr_prov,
            )
            success = await publisher.publish(alert)
            if success:
                metrics["alerts_published"] += 1
                alerts_emitted[tid].add("anpr_read")
                logger.info(
                    "anpr_read_alert camera=%s tracker=%d plate=%s conf=%.0f%%",
                    camera_id, tid, consensus_plate, avg_conf,
                )
            else:
                metrics["alerts_failed"] += 1

    # ── 8. Stale tracker cleanup ─────────────────────────────────
    stale_tids = [
        t for t, data in active_sessions.items()
        if frame_counter - data["last_seen"] > 90
    ]
    for t in stale_tids:
        s_data = active_sessions.get(t, {})
        t_alerts = alerts_emitted.get(t, set())
        if s_data.get("max_speed_kmh", 0) > speed_limit and "speed_violation" not in t_alerts:
            p_reads = s_data.get("plate_reads", [])
            p_confs = s_data.get("plate_confidences", [])
            c_plate = get_mode(p_reads, p_confs) if p_reads else None
            p_disp = c_plate if (c_plate and c_plate != "UNKNOWN") else "UNKNOWN"
            alert = build_speed_violation_alert(
                camera_id=frame_event.camera_id,
                source_event_id=frame_event.event_id,
                tracker_id=t,
                plate=p_disp,
                speed_kmh=s_data.get("max_speed_kmh", 0),
                speed_limit_kmh=speed_limit,
                vehicle_type=s_data.get("vehicle_type", "Car"),
                frame_reference=frame_event.frame_reference,
                frame_provider=frame_event.frame_provider,
            )
            await publisher.publish(alert)
            metrics["alerts_published"] += 1
            logger.info("speed_violation_alert_on_exit camera=%s tracker=%d plate=%s", camera_id, t, p_disp)

        active_sessions.pop(t, None)
        alerts_emitted.pop(t, None)
    if stale_tids and speed_estimator:
        speed_estimator.clean_stale_trackers(active_sessions.keys())

    # Update active tracks metric
    metrics["active_tracks"] = sum(
        len(state["active_sessions"])
        for state in _camera_state.values()
    )


# ── Application Lifecycle ────────────────────────────────────────

consumer_task: asyncio.Task | None = None
redis_client: aioredis.Redis | None = None
publisher: AlertPublisher | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_task, redis_client, publisher

    logger.info("uc4_analytics_starting")

    # 1. Redis
    redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    await redis_client.ping()
    logger.info("redis_connected")

    # 2. AlertPublisher (FIX #4)
    publisher = AlertPublisher(redis_client)

    # 3. Load ML models in background
    threading.Thread(target=_load_models, daemon=True).start()

    # 4. Start consumer loop
    async def _frame_callback(frame_event: FrameEvent):
        await process_frame(frame_event, redis_client, publisher)

    consumer_task = asyncio.create_task(
        consume_loop(redis_client, _frame_callback, metrics)
    )

    logger.info("uc4_analytics_started")
    yield

    # Shutdown
    logger.info("uc4_analytics_shutting_down")

    if consumer_task:
        consumer_task.cancel()
        try:
            await consumer_task
        except asyncio.CancelledError:
            pass

    await close_engine()

    if redis_client:
        await redis_client.aclose()

    # Stop OCR workers (send one sentinel per worker)
    for _ in range(_NUM_OCR_WORKERS):
        _ocr_queue.put(None)

    logger.info("uc4_analytics_stopped")


# ── FastAPI Application (FIX #6) ─────────────────────────────────

app = FastAPI(
    title="UC4 Analytics Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "uc4_analytics"}


@app.get("/metrics")
async def get_metrics():
    return {
        "frames_consumed": metrics["frames_consumed"],
        "alerts_published": metrics["alerts_published"],
        "alerts_failed": metrics["alerts_failed"],
        "active_tracks": metrics["active_tracks"],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8024)