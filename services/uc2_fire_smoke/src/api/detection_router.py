"""
Detection Module API Router — Centralized Multimodal Detection Interface.

Provides 3 distinct detection input modes:
  Mode A: POST /detection/image   — Direct image file upload & annotated analysis
  Mode B: POST /detection/video   — Video file upload with timeline & keyframe analysis
  Mode C: POST /detection/rtsp    — Interactive RTSP stream connection, live streaming & control

All modes reuse the core UC2 Detection Pipeline (YOLO Engine + Deterministic Verifier + Temporal Logic).
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from services.uc2_fire_smoke.src.config import settings
from services.uc2_fire_smoke.src.detection.pipeline import ConfirmedDetection, DetectionPipeline, DetectionResult

logger = logging.getLogger("innovision.uc2.detection_module")

router = APIRouter(prefix="/detection", tags=["Detection Module"])


class RTSPConnectRequest(BaseModel):
    rtsp_url: str = Field(..., description="RTSP URL stream, e.g. rtsp://192.168.1.100:554/live")
    camera_name: Optional[str] = Field("Interactive RTSP Camera", description="Display name for this source")


# ── Active RTSP Session Manager ─────────────────────────────────────────────

class ActiveRTSPSession:
    def __init__(self, rtsp_url: str, camera_name: str, pipeline: DetectionPipeline, publisher: Any) -> None:
        self.rtsp_url = rtsp_url
        self.camera_name = camera_name
        self.pipeline = pipeline
        self.publisher = publisher
        self.running = False
        self.connected = False
        self.task: Optional[asyncio.Task] = None
        self.latest_frame_jpeg: Optional[bytes] = None
        self.latest_detection: Optional[str] = None
        self.latest_confidence: float = 0.0
        self.fps: float = 0.0
        self.frames_processed: int = 0
        self.alerts_emitted: int = 0
        self.start_time: float = time.time()
        self.last_error: Optional[str] = None
        self.session_id: str = str(uuid4())

    async def start(self) -> None:
        self.running = True
        self.task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self.running = False
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.connected = False
        logger.info(f"RTSP Session {self.rtsp_url} stopped.")

    async def _run_loop(self) -> None:
        logger.info(f"Starting RTSP loop for {self.rtsp_url}")
        cap = cv2.VideoCapture(self.rtsp_url)
        if not cap.isOpened():
            self.last_error = f"Cannot open RTSP URL: {self.rtsp_url}"
            logger.error(self.last_error)
            self.running = False
            return

        self.connected = True
        fps_counter = 0
        fps_timer = time.time()

        try:
            loop = asyncio.get_running_loop()
            while self.running:
                # Read frame in executor to prevent blocking asyncio loop
                ret, frame = await loop.run_in_executor(None, cap.read)
                if not ret or frame is None:
                    logger.warning("RTSP stream disconnected or end of stream.")
                    await asyncio.sleep(0.5)
                    continue

                self.frames_processed += 1
                fps_counter += 1
                if time.time() - fps_timer >= 1.0:
                    self.fps = round(fps_counter / (time.time() - fps_timer), 1)
                    fps_counter = 0
                    fps_timer = time.time()

                # Run detection pipeline
                h, w = frame.shape[:2]
                if w > 640 or h > 480:
                    frame_proc = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_AREA)
                else:
                    frame_proc = frame

                result: DetectionResult = self.pipeline.process_frame(
                    camera_id=self.session_id,
                    frame_seq=self.frames_processed,
                    frame_bgr=frame_proc,
                    single_frame=False,
                )

                # Annotate frame
                annotated = frame_proc.copy()
                if result.has_detections and result.confirmed_detections:
                    top_det = max(result.confirmed_detections, key=lambda d: d.final_confidence)
                    self.latest_detection = top_det.detection_type
                    self.latest_confidence = top_det.final_confidence

                    for det in result.confirmed_detections:
                        bx = det.bbox
                        color = (0, 0, 255) if det.detection_type == "fire" else (200, 200, 0) if det.detection_type == "smoke" else (0, 215, 255)
                        cv2.rectangle(annotated, (bx["x1"], bx["y1"]), (bx["x2"], bx["y2"]), color, 2)
                        label = f"{det.detection_type.upper()} {det.final_confidence*100:.1f}%"
                        cv2.putText(annotated, label, (bx["x1"], max(15, bx["y1"] - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                    # Trigger alert via publisher if present
                    if self.publisher and top_det.final_confidence >= 0.30:
                        try:
                            alert = AlertEvent(
                                camera_id=uuid4(),
                                timestamp=datetime.now(timezone.utc),
                                severity=top_det.severity,
                                alert_type=top_det.detection_type,
                                title=f"Real-time {top_det.detection_type.upper()} detected on RTSP stream",
                                description=f"Detection Module: {top_det.detection_type} verified with {top_det.final_confidence*100:.1f}% confidence on {self.camera_name}",
                                source_uc=SourceUC.UC2,
                                metadata={
                                    "source": "detection_module_rtsp",
                                    "rtsp_url": self.rtsp_url,
                                    "confidence": top_det.final_confidence,
                                    "bbox": top_det.bbox,
                                },
                            )
                            await self.publisher.publish(alert)
                            self.alerts_emitted += 1
                        except Exception as e:
                            logger.error(f"Failed to publish RTSP alert: {e}")
                else:
                    if self.frames_processed % 15 == 0:
                        self.latest_detection = None
                        self.latest_confidence = 0.0

                # Encode to JPEG for preview stream
                ok, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    self.latest_frame_jpeg = jpeg.tobytes()

                # Control loop yield
                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Error in RTSP processing loop: {e}")
        finally:
            cap.release()
            self.connected = False


# Module-level active RTSP session
_active_rtsp: Optional[ActiveRTSPSession] = None


def _get_pipeline(request: Request) -> DetectionPipeline:
    pm = getattr(request.app.state, "pipeline_manager", None)
    if pm and getattr(pm, "pipeline", None):
        return pm.pipeline
    # Fallback to local pipeline instance
    from services.uc2_fire_smoke.src.detection.engine import YOLOEngine
    from services.uc2_fire_smoke.src.detection.zone_engine import ZoneEngine
    return DetectionPipeline(yolo_engine=YOLOEngine(), zone_engine=ZoneEngine())


def _draw_annotations(img: np.ndarray, detections: List[ConfirmedDetection]) -> np.ndarray:
    annotated = img.copy()
    h_img, w_img = img.shape[:2]
    total_area = max(h_img * w_img, 1)

    for det in detections:
        bx = det.bbox
        dt = det.detection_type.lower()
        if dt == "fire":
            color = (0, 0, 235)       # Fire Red
            label = "FIRE"
        elif dt == "smoke":
            color = (200, 180, 0)     # Smoke Blue/Cyan
            label = "SMOKE"
        else:
            color = (0, 215, 255)     # Spark Gold
            label = "SPARKS"

        w_box = max(1, bx["x2"] - bx["x1"])
        h_box = max(1, bx["y2"] - bx["y1"])
        area_pct = round(((w_box * h_box) / total_area) * 100.0, 1)

        cv2.rectangle(annotated, (bx["x1"], bx["y1"]), (bx["x2"], bx["y2"]), color, 3)

        badge_text = f"{label} {det.final_confidence*100:.1f}% ({area_pct}% area)"
        (tw, th), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        y_text = max(th + 6, bx["y1"] - 8)

        # Background tag behind text for high visibility
        cv2.rectangle(
            annotated,
            (bx["x1"], y_text - th - 4),
            (bx["x1"] + tw + 6, y_text + 4),
            color,
            -1,
        )
        cv2.putText(
            annotated,
            badge_text,
            (bx["x1"] + 3, y_text - 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0) if dt != "fire" else (255, 255, 255),
            2,
        )
    return annotated


# ── Mode A: Image Upload Detection ──────────────────────────────────────────

@router.post("/image", summary="Detect Fire, Smoke, and Sparks in Uploaded Image")
async def detect_image(
    request: Request,
    file: UploadFile = File(...),
    conf_threshold: Optional[float] = Query(None, description="Confidence threshold override (0.05-1.0)"),
) -> Dict[str, Any]:
    """
    Run real Stage 1–6 detection pipeline on a user-uploaded image.
    Returns detected bounding boxes, confidence, class labels, area occupancy, and base64 annotated image.
    """
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a valid image (JPEG/PNG/WebP).")

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise HTTPException(status_code=400, detail="Failed to decode image.")

    orig_h, orig_w = img_bgr.shape[:2]
    total_area = max(orig_h * orig_w, 1)
    logger.info("Upload image received: %s [%dx%d, %d bytes]", file.filename, orig_w, orig_h, len(contents))

    pipeline = _get_pipeline(request)
    t0 = time.perf_counter()

    # Pass conf_override to YOLO if specified, else use default
    conf_limit = conf_threshold if conf_threshold is not None else settings.conf_threshold

    # Run detection pipeline in single_frame mode (no multi-frame temporal requirement)
    result: DetectionResult = pipeline.process_frame(
        camera_id="upload-image-session",
        frame_seq=1,
        frame_bgr=img_bgr,
        single_frame=True,
    )
    t_total = (time.perf_counter() - t0) * 1000.0

    logger.info(
        "Upload image detection completed: %d confirmed, %d suppressed (latency=%.1fms)",
        len(result.confirmed_detections), len(result.suppressed_detections), t_total
    )

    # Draw annotations
    annotated = _draw_annotations(img_bgr, result.confirmed_detections)
    _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    raw_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
    b64_data_uri = f"data:image/jpeg;base64,{raw_b64}"

    detections_payload = []
    summary_counts = {"fire": 0, "smoke": 0, "sparks": 0}
    for d in result.confirmed_detections:
        cl = d.detection_type.lower()
        if cl in summary_counts:
            summary_counts[cl] += 1

        bx = d.bbox
        w_box = max(0, bx["x2"] - bx["x1"])
        h_box = max(0, bx["y2"] - bx["y1"])
        area_box = w_box * h_box
        area_pct = round((area_box / total_area) * 100.0, 2)

        detections_payload.append({
            "class": cl,
            "class_name": cl,
            "class_id": 0 if cl == "fire" else 1 if cl == "smoke" else 2,
            "confidence": float(d.final_confidence),
            "yolo_confidence": float(d.yolo_confidence),
            "verification_score": float(d.verification_score),
            "severity": d.severity.value,
            "bbox": [bx["x1"], bx["y1"], bx["x2"], bx["y2"]],
            "width": w_box,
            "height": h_box,
            "area": area_box,
            "area_percentage": area_pct,
            "verified": True,
        })

    has_hazard = len(detections_payload) > 0
    top_hazard = detections_payload[0]["class"] if has_hazard else "none"

    return {
        "status": "success",
        "success": True,
        "input_mode": "image",
        "filename": file.filename,
        "hazard_detected": has_hazard,
        "has_detections": has_hazard,
        "has_alert": has_hazard,
        "alert_triggered": has_hazard,
        "detection_count": len(detections_payload),
        "primary_hazard": top_hazard,
        "detections": detections_payload,
        "summary": summary_counts,
        "annotated_image": b64_data_uri,
        "annotated_image_base64": raw_b64,
        "dimensions": {"width": orig_w, "height": orig_h, "total_pixels": total_area},
        "inference_latency_ms": round(result.inference_latency_ms, 2),
        "total_latency_ms": round(t_total, 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Mode B: Video Upload Detection ──────────────────────────────────────────

@router.post("/video", summary="Process Uploaded Video for Fire / Smoke / Sparks")
async def detect_video(request: Request, file: UploadFile = File(...)) -> Dict[str, Any]:
    """
    Process an uploaded video frame-by-frame through the UC2 detection and temporal pipeline.
    Returns detection timeline, detected classes, peak confidence, and best keyframe snapshot.
    """
    if not (file.content_type.startswith("video/") or file.filename.endswith((".mp4", ".avi", ".mov", ".mkv"))):
        raise HTTPException(status_code=400, detail="Uploaded file must be a valid video format.")

    # Write temporarily to disk for cv2.VideoCapture
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp:
        tmp_path = tmp.name
        content = await file.read()
        tmp.write(content)

    cap = cv2.VideoCapture(tmp_path)
    if not cap.isOpened():
        os.unlink(tmp_path)
        raise HTTPException(status_code=400, detail="Could not open video file.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    duration_s = total_frames / video_fps if video_fps > 0 else 0.0

    pipeline = _get_pipeline(request)
    frame_step = max(1, int(video_fps / 3))  # Sample ~3 frames per second for responsiveness

    t0 = time.perf_counter()
    seq = 0
    sampled_count = 0
    timeline = []
    classes_detected = set()
    peak_confidence = 0.0
    best_keyframe_b64 = None

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            seq += 1
            if seq % frame_step != 0:
                continue

            sampled_count += 1
            h, w = frame.shape[:2]
            if w > 640 or h > 480:
                frame_proc = cv2.resize(frame, (640, 480), interpolation=cv2.INTER_AREA)
            else:
                frame_proc = frame

            res = pipeline.process_frame(
                camera_id="upload-video-session",
                frame_seq=seq,
                frame_bgr=frame_proc,
                single_frame=False,
            )

            if res.has_detections and res.confirmed_detections:
                for d in res.confirmed_detections:
                    cl = d.detection_type.lower()
                    classes_detected.add(cl)
                    conf = float(d.final_confidence)
                    if conf > peak_confidence:
                        peak_confidence = conf
                        ann = _draw_annotations(frame_proc, [d])
                        _, buf = cv2.imencode(".jpg", ann, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        best_keyframe_b64 = f"data:image/jpeg;base64,{base64.b64encode(buf.tobytes()).decode('utf-8')}"

                    timeline.append({
                        "frame_seq": seq,
                        "time_seconds": round(seq / video_fps, 2),
                        "hazard": cl,
                        "confidence": conf,
                        "bbox": [d.bbox["x1"], d.bbox["y1"], d.bbox["x2"], d.bbox["y2"]],
                    })

            # Cap max sampled frames per upload to prevent long blocking
            if sampled_count >= 100:
                break

    finally:
        cap.release()
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

    proc_time_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "status": "success",
        "input_mode": "video",
        "filename": file.filename,
        "total_video_frames": total_frames,
        "sampled_frames_processed": sampled_count,
        "duration_seconds": round(duration_s, 2),
        "has_detections": len(classes_detected) > 0,
        "classes_detected": list(classes_detected),
        "peak_confidence": round(peak_confidence, 4),
        "timeline": timeline[:50],  # Return up to 50 key detection points
        "keyframe_annotated": best_keyframe_b64,
        "summary": {
            "fire": 1 if "fire" in classes_detected else 0,
            "smoke": 1 if "smoke" in classes_detected else 0,
            "sparks": 1 if "sparks" in classes_detected else 0,
            "alert_triggered": len(classes_detected) > 0,
        },
        "processing_time_ms": proc_time_ms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Mode C: RTSP Camera Connection & Control ────────────────────────────────

@router.post("/rtsp", summary="Connect and Start Real-Time RTSP Stream Detection")
async def connect_rtsp(request: Request, payload: RTSPConnectRequest) -> Dict[str, Any]:
    """
    Connect to an RTSP camera stream and launch real-time background detection.
    Streams annotated frames live at /detection/rtsp/stream.
    """
    global _active_rtsp
    if _active_rtsp and _active_rtsp.running:
        await _active_rtsp.stop()

    pipeline = _get_pipeline(request)
    pm = getattr(request.app.state, "pipeline_manager", None)
    publisher = getattr(pm, "alert_publisher", None)

    session = ActiveRTSPSession(
        rtsp_url=payload.rtsp_url,
        camera_name=payload.camera_name or "Custom RTSP",
        pipeline=pipeline,
        publisher=publisher,
    )
    await session.start()
    _active_rtsp = session

    # Give stream 0.5s to establish connection
    await asyncio.sleep(0.5)

    return {
        "status": "connected" if session.connected else "connecting",
        "input_mode": "rtsp",
        "rtsp_url": payload.rtsp_url,
        "camera_name": payload.camera_name,
        "stream_url": "/detection/rtsp/stream",
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/rtsp/stop", summary="Stop Current RTSP Stream Detection")
async def stop_rtsp() -> Dict[str, Any]:
    global _active_rtsp
    if not _active_rtsp or not _active_rtsp.running:
        return {"status": "stopped", "message": "No active RTSP session was running."}

    await _active_rtsp.stop()
    return {"status": "stopped", "message": "RTSP detection session terminated successfully."}


@router.get("/rtsp/status", summary="Get RTSP Stream Detection Telemetry & Status")
async def get_rtsp_status() -> Dict[str, Any]:
    global _active_rtsp
    if not _active_rtsp:
        return {
            "active": False,
            "connected": False,
            "rtsp_url": None,
            "fps": 0.0,
            "frames_processed": 0,
            "latest_detection": None,
            "latest_confidence": 0.0,
            "alert_status": "idle",
        }

    return {
        "active": _active_rtsp.running,
        "connected": _active_rtsp.connected,
        "rtsp_url": _active_rtsp.rtsp_url,
        "camera_name": _active_rtsp.camera_name,
        "fps": _active_rtsp.fps,
        "frames_processed": _active_rtsp.frames_processed,
        "latest_detection": _active_rtsp.latest_detection,
        "latest_confidence": round(_active_rtsp.latest_confidence, 4),
        "alert_status": "alerting" if _active_rtsp.latest_detection else "normal",
        "alerts_emitted": _active_rtsp.alerts_emitted,
        "uptime_seconds": round(time.time() - _active_rtsp.start_time, 1),
        "last_error": _active_rtsp.last_error,
    }


@router.get("/rtsp/stream", summary="Live MJPEG Stream of Annotated RTSP Feed")
async def rtsp_mjpeg_stream() -> StreamingResponse:
    global _active_rtsp
    if not _active_rtsp or not _active_rtsp.running:
        raise HTTPException(status_code=404, detail="No active RTSP stream. Start one with POST /detection/rtsp.")

    async def _frame_generator():
        while _active_rtsp and _active_rtsp.running:
            jpeg = _active_rtsp.latest_frame_jpeg
            if jpeg:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
            await asyncio.sleep(0.066)  # ~15 FPS MJPEG delivery

    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ── Global Detection Status ─────────────────────────────────────────────────

@router.get("/status", summary="Overall Detection Module Engine Status")
async def detection_module_status(request: Request) -> Dict[str, Any]:
    pipeline = _get_pipeline(request)
    global _active_rtsp
    return {
        "status": "ready",
        "service": "detection_module",
        "model_file": settings.yolo_model_path,
        "supported_classes": ["fire", "smoke", "sparks"],
        "class_mapping": {"0": "fire", "1": "smoke", "2": "sparks"},
        "device": getattr(pipeline.yolo, "device", "cpu"),
        "confidence_threshold": settings.conf_threshold,
        "temporal_persistence_required_frames": settings.temporal_frames,
        "supported_modes": ["image", "video", "rtsp"],
        "active_rtsp_session": _active_rtsp.running if _active_rtsp else False,
    }
