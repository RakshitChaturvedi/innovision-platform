"""
UC3 Real PPE Detection Service Entry Point — Platform Integration.

Pipeline:
Camera Registry (/by-uc/uc3)
  -> Redis FrameEvent Stream (frames:{camera_id})
  -> Redis Frame Cache Retrieval (frame:{camera_id}:{frame_seq})
  -> Presence Cascade (Motion Gate -> Person Gate -> Mannequin Gate)
  -> YOLO (best.pt) + ByteTrack Inference
  -> Compliance Engine (hybrid spatial association + temporal windowing)
  -> AlertEvent Generation (source_event_id = frame_event.event_id)
  -> AlertPublisher (alerts:live Stream)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import UUID, uuid4

import cv2
import httpx
import numpy as np
import redis.asyncio as aioredis
import torch
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from redis.exceptions import ResponseError
from ultralytics import YOLO

# Ensure /app is in pythonpath
sys.path.insert(0, "/app")

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, FrameProvider, SourceUC
from shared.contracts.frame_event import FrameEvent
from shared.platform_client.alert_publisher import AlertPublisher

from stubs.uc3_stub.src.config import (
    CAMERA_REGISTRY_URL,
    CONF_THRESHOLD,
    IMAGE_SIZE,
    IOU_THRESHOLD,
    MODEL_PATH,
    PERSON_GATE_ENABLED,
    REDIS_CONSUMER_GROUP,
    REDIS_CONSUMER_NAME,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_URL,
    TEST_CAMERA_ID,
    UC_ID,
)
from stubs.uc3_stub.src import compliance, motion_gate, person_gate, mannequin_gate

# ── Pydantic Models ───────────────────────────────────────────────────────────

class CameraComplianceSummary(BaseModel):
    camera_id: str
    violation_count: int
    compliant_count: int
    last_updated: str


class PPEComplianceSummary(BaseModel):
    total_cameras: int
    total_violations: int
    cameras: list[CameraComplianceSummary]
    generated_at: str


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("uc3_real_service")

# ── In-memory Metrics ──────────────────────────────────────────────────────────
metrics = {
    "frames_consumed": 0,
    "alerts_published": 0,
    "alerts_failed": 0,
    "active_detections": 0,
}

_latest_annotated_frames: dict[str, bytes] = {}

# ── Device Setup ──────────────────────────────────────────────────────────────
_cuda_available = torch.cuda.is_available()
_mps_available = torch.backends.mps.is_available()

if _cuda_available:
    _device: int | str = 0
    _fp16: bool = True
elif _mps_available:
    _device = "mps"
    _fp16 = False
else:
    _device = "cpu"
    _fp16 = False


def _new_model() -> YOLO:
    m = YOLO(str(MODEL_PATH))
    warmup = np.zeros((IMAGE_SIZE, IMAGE_SIZE, 3), dtype=np.uint8)
    m.predict(
        warmup,
        conf=CONF_THRESHOLD,
        iou=IOU_THRESHOLD,
        imgsz=IMAGE_SIZE,
        device=_device,
        half=_fp16,
        verbose=False,
    )
    return m


# ── Camera Discovery ──────────────────────────────────────────────────────────
async def discover_assigned_cameras(http_client: httpx.AsyncClient) -> list[str]:
    url = f"{CAMERA_REGISTRY_URL}/cameras/by-uc/{UC_ID}"
    try:
        resp = await http_client.get(url, timeout=3.0)
        if resp.status_code == 200:
            data = resp.json()
            cam_ids = data.get("camera_ids", [])
            if cam_ids:
                logger.info("camera_registry_discovery uc=%s cameras=%s", UC_ID, cam_ids)
                return [str(cid) for cid in cam_ids if cid]
    except Exception as exc:
        logger.warning("camera_registry_discovery_failed url=%s error=%s (using fallback)", url, exc)

    logger.info("camera_registry_fallback using TEST_CAMERA_ID=%s", TEST_CAMERA_ID)
    return [TEST_CAMERA_ID]


# ── Latest Detections Store ───────────────────────────────────────────────────
_latest_detections: dict[str, dict] = {}


# ── Single Message Processing ──────────────────────────────────────────────────
async def process_frame_message(
    redis_client: aioredis.Redis,
    publisher: AlertPublisher,
    session_models: dict[str, YOLO],
    motion_states: dict[str, motion_gate.MotionState],
    worker_states_map: dict[str, compliance.WorkerStates],
    stream_name: str,
    msg_id: str | bytes,
    fields: dict,
) -> None:
    # Handle byte or str dict keys from redis
    data_bytes = fields.get(b"data") or fields.get("data")
    if not data_bytes:
        return

    if isinstance(data_bytes, bytes):
        payload_str = data_bytes.decode("utf-8")
    else:
        payload_str = str(data_bytes)

    # 1. Parse FrameEvent
    try:
        frame_event = FrameEvent.model_validate_json(payload_str)
    except Exception as exc:
        logger.error("frame_event_parse_error stream=%s msg_id=%s error=%s", stream_name, msg_id, exc)
        return

    camera_id_str = str(frame_event.camera_id)

    # 2. Fetch JPEG bytes from Redis
    try:
        jpeg_bytes = await redis_client.get(frame_event.frame_reference)
    except Exception as exc:
        logger.error("redis_get_frame_failed ref=%s error=%s", frame_event.frame_reference, exc)
        return

    if not jpeg_bytes:
        logger.debug("frame_cache_miss ref=%s", frame_event.frame_reference)
        return

    # 3. Decode image
    try:
        frame_arr = np.frombuffer(jpeg_bytes, np.uint8)
        frame = cv2.imdecode(frame_arr, cv2.IMREAD_COLOR)
        if frame is None:
            logger.warning("frame_decode_failed ref=%s", frame_event.frame_reference)
            return
    except Exception as exc:
        logger.error("frame_decode_error ref=%s error=%s", frame_event.frame_reference, exc)
        return

    # Initialize per-camera session models & states if needed
    if camera_id_str not in motion_states:
        motion_states[camera_id_str] = motion_gate.new_session_state()
    if camera_id_str not in worker_states_map:
        worker_states_map[camera_id_str] = compliance.new_session_state()
    if camera_id_str not in session_models:
        logger.info("initializing_session_model camera_id=%s", camera_id_str)
        session_models[camera_id_str] = _new_model()

    model = session_models[camera_id_str]
    m_state = motion_states[camera_id_str]
    w_states = worker_states_map[camera_id_str]

    h, w = frame.shape[:2]

    # 4. Run Presence Cascade (Motion Gate -> Person Gate -> Mannequin Gate)
    def _run_cascade_and_inference() -> tuple[list[dict], list[str], list[dict]]:
        # Stage 1: Motion pre-gate
        if not motion_gate.frame_has_motion(m_state, frame):
            return [], [], []

        # Stage 2: Person Presence Gate
        if PERSON_GATE_ENABLED:
            if mannequin_gate.enabled():
                res = mannequin_gate.detect(frame)
                if res is not None:
                    candidate_boxes, mannequin_boxes = res
                else:
                    candidate_boxes = person_gate.detect_persons(frame)
                    mannequin_boxes = []
            else:
                candidate_boxes = person_gate.detect_persons(frame)
                mannequin_boxes = []

            if candidate_boxes is None:
                # fail open
                candidate_boxes = []
            elif len(candidate_boxes) == 0:
                # no persons in frame
                return [], [], []
        else:
            candidate_boxes = [(0.0, 0.0, float(w), float(h))]
            mannequin_boxes = []

        # Stage 3: Motion gate per-candidate check
        if not motion_gate.should_run_inference(m_state, frame, candidate_boxes):
            return [], [], []

        # Optional mannequin paint-out
        if mannequin_boxes:
            excl = mannequin_gate.exclusion_regions(mannequin_boxes, candidate_boxes)
            infer_frame = mannequin_gate.mask_regions(frame, excl)
        else:
            excl = []
            infer_frame = frame

        # Stage 4: Primary YOLO + ByteTrack inference
        results = model.track(
            infer_frame,
            persist=True,
            conf=CONF_THRESHOLD,
            iou=IOU_THRESHOLD,
            imgsz=IMAGE_SIZE,
            device=_device,
            half=_fp16,
            verbose=False,
        )

        detections: list[dict] = []
        if results and len(results) > 0 and results[0].boxes is not None:
            res_boxes = results[0].boxes
            names = model.names
            for i in range(len(res_boxes)):
                box_xyxy = res_boxes.xyxy[i].tolist()  # [x1, y1, x2, y2] in pixels
                conf_val = float(res_boxes.conf[i])
                cls_id = int(res_boxes.cls[i])
                label = str(names.get(cls_id, cls_id))
                track_id = int(res_boxes.id[i]) if res_boxes.id is not None else None

                # Normalize box coordinates to 0..1
                norm_box = [
                    box_xyxy[0] / w,
                    box_xyxy[1] / h,
                    box_xyxy[2] / w,
                    box_xyxy[3] / h,
                ]

                detections.append({
                    "label": label,
                    "conf": conf_val,
                    "box": norm_box,
                    "_track_id": track_id,
                })

        # Integrate person gate candidate detections if main model didn't emit persons
        has_person_det = any(d["label"].lower() == "person" for d in detections)
        if not has_person_det and candidate_boxes:
            for p_idx, p_box in enumerate(candidate_boxes):
                p_norm = [
                    p_box[0] / w,
                    p_box[1] / h,
                    p_box[2] / w,
                    p_box[3] / h,
                ]
                detections.append({
                    "label": "person",
                    "conf": 0.85,
                    "box": p_norm,
                    "_track_id": p_idx + 1,
                })

        # Ensure head regions exist for helmet compliance check
        has_head_det = any(d["label"].lower() == "head" for d in detections)
        if not has_head_det:
            for d in list(detections):
                if d["label"].lower() == "person":
                    pb = d["box"]
                    head_box = [pb[0], pb[1], pb[2], pb[1] + 0.25 * (pb[3] - pb[1])]
                    detections.append({
                        "label": "head",
                        "conf": d["conf"],
                        "box": head_box,
                        "_track_id": d.get("_track_id"),
                    })

        if excl:
            detections = mannequin_gate.drop_in_regions(detections, excl, w, h)

        # Stage 5: Compliance evaluation
        now_sec = time.monotonic()
        severity, unique_vio, worker_violations = compliance.evaluate_compliance(
            detections=detections,
            worker_states=w_states,
            now=now_sec,
            required_ppe=frozenset({"helmet", "vest"}),  # Standard industrial requirement
        )

        return detections, unique_vio, worker_violations

    # Run inference in worker thread to prevent blocking event loop
    detections, unique_vio, worker_violations = await asyncio.to_thread(_run_cascade_and_inference)

    # Build UI overlay detections for frontend DetectionOverlay component
    ui_detections: list[dict] = []
    violating_tracks = {wv["worker_id"]: wv["ppe_type"] for wv in worker_violations} if worker_violations else {}

    for d in detections:
        lbl = d["label"]
        norm_box = d["box"]
        track_id = d.get("_track_id")
        x1, y1, x2, y2 = norm_box[0], norm_box[1], norm_box[2], norm_box[3]

        if lbl.lower() == "head":
            continue

        if lbl == "person":
            if track_id in violating_tracks:
                display_label = f"Person #{track_id} (Missing {violating_tracks[track_id]})"
                color = "#ff3333"
            elif track_id is not None:
                display_label = f"Person #{track_id} (Compliant)"
                color = "#00e676"
            else:
                display_label = "Person"
                color = "#00e676"
        elif lbl.startswith("no-"):
            display_label = f"Missing {lbl.replace('no-', '').replace('-', ' ').title()}"
            color = "#ff4d4d"
        else:
            display_label = lbl.replace("-", " ").title()
            color = "#00b0ff"

        ui_detections.append({
            "track_id": int(track_id) if track_id is not None else None,
            "label": str(display_label),
            "color": str(color),
            "bbox": {
                "x1": float(max(0.0, min(1.0, round(float(x1), 4)))),
                "y1": float(max(0.0, min(1.0, round(float(y1), 4)))),
                "x2": float(max(0.0, min(1.0, round(float(x2), 4)))),
                "y2": float(max(0.0, min(1.0, round(float(y2), 4)))),
            },
            "metadata": {
                "confidence": float(round(float(d.get("conf", 0.0)), 2)),
                "raw_label": str(lbl),
            },
        })

    _latest_detections[camera_id_str] = {
        "camera_id": camera_id_str,
        "detections": ui_detections,
        "zones": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    metrics["frames_consumed"] += 1
    metrics["active_detections"] = len(ui_detections)

    # Render annotations directly onto source frame for streaming
    annotated_bgr = frame.copy()
    h, w = frame.shape[:2]
    for d in ui_detections:
        bx1 = max(0, min(w - 1, int(round(d["bbox"]["x1"] * w))))
        by1 = max(0, min(h - 1, int(round(d["bbox"]["y1"] * h))))
        bx2 = max(0, min(w - 1, int(round(d["bbox"]["x2"] * w))))
        by2 = max(0, min(h - 1, int(round(d["bbox"]["y2"] * h))))
        hex_c = d.get("color", "#00e676").lstrip("#")
        c_bgr = (int(hex_c[4:6], 16), int(hex_c[2:4], 16), int(hex_c[0:2], 16)) if len(hex_c) == 6 else (0, 255, 0)
        cv2.rectangle(annotated_bgr, (bx1, by1), (bx2, by2), c_bgr, 2)
        badge_text = f"{d['label']} {int(d['metadata']['confidence']*100)}%"
        (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        ty = max(by1 - 5, th + 5)
        cv2.rectangle(annotated_bgr, (bx1, ty - th - 4), (bx1 + tw + 6, ty + 2), c_bgr, -1)
        cv2.putText(annotated_bgr, badge_text, (bx1 + 3, ty - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)

    ret, buf = cv2.imencode(".jpg", annotated_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    if ret:
        _latest_annotated_frames[camera_id_str] = buf.tobytes()

    # 5. Emit AlertEvents for newly raised worker violations
    for wv in worker_violations:
        ppe_type = wv["ppe_type"]
        track_id = wv["worker_id"]
        confidence = wv["confidence"]

        severity_enum = AlertSeverity.HIGH if len(unique_vio) > 1 else AlertSeverity.MEDIUM

        alert = AlertEvent(
            alert_id=uuid4(),
            camera_id=frame_event.camera_id,
            timestamp=datetime.now(timezone.utc),
            severity=severity_enum,
            alert_type="ppe_violation",
            title=f"PPE Violation: Missing {ppe_type.replace('_', ' ').replace('-', ' ').title()}",
            description=(
                f"UC3 PPE Compliance Pipeline detected worker (Track #{track_id}) missing required PPE "
                f"'{ppe_type}' on Camera {frame_event.camera_id} (Frame {frame_event.frame_seq})."
            ),
            source_event_id=frame_event.event_id,  # CRITICAL: direct linkage to FrameEvent!
            source_uc=SourceUC.UC3,
            frame_reference=frame_event.frame_reference,
            frame_provider=frame_event.frame_provider,
            metadata={
                "track_id": track_id,
                "missing_ppe": [ppe_type],
                "violation_name": wv["violation"],
                "confidence": float(confidence),
                "frame_seq": frame_event.frame_seq,
                "camera_id": str(frame_event.camera_id),
            },
        )

        published = await publisher.publish(alert)
        if published:
            metrics["alerts_published"] += 1
            logger.info(
                "alert_published alert_id=%s camera_id=%s track_id=%s ppe_type=%s source_event_id=%s",
                alert.alert_id,
                alert.camera_id,
                track_id,
                ppe_type,
                alert.source_event_id,
            )
        else:
            metrics["alerts_failed"] += 1

    # 6. Acknowledge stream message
    try:
        await redis_client.xack(stream_name, REDIS_CONSUMER_GROUP, msg_id)
    except Exception as exc:
        logger.warning("redis_xack_failed stream=%s msg_id=%s error=%s", stream_name, msg_id, exc)


# ── Main Pipeline Worker Loop ─────────────────────────────────────────────────
async def run_uc3_pipeline(stop_event: asyncio.Event) -> None:
    logger.info("uc3_pipeline_starting device=%s fp16=%s", _device, _fp16)

    async with httpx.AsyncClient() as http_client:
        camera_ids = await discover_assigned_cameras(http_client)

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    publisher = AlertPublisher(redis_client)

    session_models: dict[str, YOLO] = {}
    motion_states: dict[str, motion_gate.MotionState] = {}
    worker_states_map: dict[str, compliance.WorkerStates] = {}

    stream_names = [f"frames:{cid}" for cid in camera_ids]

    # Ensure Redis consumer groups exist for all assigned camera streams
    for s_name in stream_names:
        try:
            await redis_client.xgroup_create(
                name=s_name,
                groupname=REDIS_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info("consumer_group_created stream=%s group=%s", s_name, REDIS_CONSUMER_GROUP)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                logger.warning("xgroup_create_warning stream=%s error=%s", s_name, exc)

    logger.info("uc3_pipeline_running streams=%s group=%s worker=%s", stream_names, REDIS_CONSUMER_GROUP, REDIS_CONSUMER_NAME)

    while not stop_event.is_set():
        try:
            stream_dict = {s_name: ">" for s_name in stream_names}
            response = await redis_client.xreadgroup(
                groupname=REDIS_CONSUMER_GROUP,
                consumername=REDIS_CONSUMER_NAME,
                streams=stream_dict,
                count=10,
                block=1000,
            )

            if not response:
                await asyncio.sleep(0.01)
                continue

            for stream_b, messages in response:
                if not messages:
                    continue
                stream_name = stream_b.decode("utf-8") if isinstance(stream_b, bytes) else str(stream_b)

                # Process the latest message in the batch to stay realtime, ACK all messages in batch
                latest_msg_id, latest_fields = messages[-1]
                for msg_id, _ in messages[:-1]:
                    try:
                        await redis_client.xack(stream_name, REDIS_CONSUMER_GROUP, msg_id)
                    except Exception:
                        pass

                await process_frame_message(
                    redis_client=redis_client,
                    publisher=publisher,
                    session_models=session_models,
                    motion_states=motion_states,
                    worker_states_map=worker_states_map,
                    stream_name=stream_name,
                    msg_id=latest_msg_id,
                    fields=latest_fields,
                )

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("uc3_pipeline_loop_error error=%s", exc)
            await asyncio.sleep(1.0)

    # Cleanup on shutdown
    logger.info("uc3_pipeline_shutting_down")
    session_models.clear()
    await redis_client.aclose()


# ── FastAPI Application & Lifespan ────────────────────────────────────────────
_pipeline_task: asyncio.Task | None = None
_stop_event = asyncio.Event()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline_task
    _stop_event.clear()
    _pipeline_task = asyncio.create_task(run_uc3_pipeline(_stop_event), name="uc3-pipeline-worker")
    logger.info("uc3_service_started")
    try:
        yield
    finally:
        logger.info("uc3_service_stopping")
        _stop_event.set()
        if _pipeline_task:
            _pipeline_task.cancel()
            try:
                await _pipeline_task
            except asyncio.CancelledError:
                pass
        logger.info("uc3_service_stopped")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Innovision UC3 PPE Compliance Service", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "uc3_compliance"}


@app.get("/cameras/{camera_id}/latest-detections")
@app.get("/uc3/cameras/{camera_id}/latest-detections")
async def get_latest_detections(camera_id: str):
    if camera_id in _latest_detections:
        return _latest_detections[camera_id]
    return {
        "camera_id": camera_id,
        "detections": [],
        "zones": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/uc3/cameras/{camera_id}/annotated-stream")
@app.get("/cameras/{camera_id}/annotated-stream")
async def get_annotated_stream(camera_id: str):
    async def frame_generator():
        while True:
            frame_bytes = _latest_annotated_frames.get(camera_id)
            if frame_bytes:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + frame_bytes
                    + b"\r\n"
                )
            await asyncio.sleep(0.08)
    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/uc3/compliance/ppe-summary", response_model=PPEComplianceSummary)
async def get_ppe_summary():
    """Return aggregated PPE violation statistics across all tracked cameras."""
    cameras: list[CameraComplianceSummary] = []
    total_violations = 0

    for cam_id, state in _latest_detections.items():
        detections = state.get("detections", [])
        violation_count = sum(
            1 for d in detections
            if d.get("color") == "#ff3333" or d.get("label", "").startswith("Person") and "Missing" in d.get("label", "")
        )
        compliant_count = sum(
            1 for d in detections
            if d.get("color") == "#00e676"
        )
        total_violations += violation_count
        cameras.append(CameraComplianceSummary(
            camera_id=cam_id,
            violation_count=violation_count,
            compliant_count=compliant_count,
            last_updated=state.get("timestamp", datetime.now(timezone.utc).isoformat()),
        ))

    return PPEComplianceSummary(
        total_cameras=len(cameras),
        total_violations=total_violations,
        cameras=cameras,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/metrics")
async def get_metrics():
    return metrics


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8023)