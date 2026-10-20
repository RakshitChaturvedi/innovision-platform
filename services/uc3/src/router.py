"""
UC3 FastAPI Router — Overlay API, Health & Prometheus Metrics
"""

from __future__ import annotations

import time
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/uc3", tags=["uc3-ppe-detection"])

consumer_manager = None  # Injected from main.py

@router.get("/cameras/{camera_id}/latest-detections")
async def get_latest_detections(
    camera_id: str,
    session_id: str | None = None,
) -> Dict[str, Any]:
    if consumer_manager is None:
        raise HTTPException(status_code=503, detail="UC3 service is initializing")

    if hasattr(consumer_manager, "get_latest_detections"):
        detections_data = consumer_manager.get_latest_detections(camera_id, session_id)
    else:
        cache_key = f"{camera_id}:{session_id}" if session_id else camera_id
        detections_data = consumer_manager.latest_detections.get(cache_key)

    if not detections_data:
        return {
            "timestamp": "",
            "camera_id": camera_id,
            "session_id": session_id,
            "source_type": "uploaded_video" if session_id else "live_rtsp",
            "detections": [],
            "severity": "ok",
            "violations": [],
            "violations_only": True,
        }

    return detections_data


@router.post("/cameras/{camera_id}/infer-image")
async def infer_image(camera_id: str, request: Request, violations_only: bool = False) -> Dict[str, Any]:
    """
    Direct still-image inference for UC3 (PPE Compliance).
    Accepts raw image bytes or multipart form file, executes YOLO PPE model,
    identifies violation items (missing helmets, vests, etc.), updates latest detections, and returns result.
    """
    import cv2
    import numpy as np
    from datetime import datetime, timezone
    from services.uc3.src.consumer import format_detections_for_overlay
    import services.uc3.src.ppe_config as config

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type:
        form = await request.form()
        file_obj = form.get("file") or form.get("image")
        if not file_obj:
            raise HTTPException(status_code=400, detail="No file uploaded in form")
        image_bytes = await file_obj.read()
    else:
        image_bytes = await request.body()

    if not image_bytes or len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Empty image payload")

    frame = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Failed to decode image bytes")

    h, w = frame.shape[:2]

    raw_detections = []
    model_to_use = consumer_manager._model if (consumer_manager and hasattr(consumer_manager, "_model") and consumer_manager._model) else None
    if model_to_use is None:
        try:
            import os
            from ultralytics import YOLO
            if os.path.exists(config.MODEL_PATH):
                model_to_use = YOLO(config.MODEL_PATH)
        except Exception:
            pass

    if model_to_use:
        results = model_to_use.predict(
            source=frame,
            conf=config.CONF_THRESHOLD,
            imgsz=config.IMAGE_SIZE,
            verbose=False,
        )
        if results and len(results) > 0:
            res = results[0]
            boxes = res.boxes
            if boxes is not None:
                for idx, b in enumerate(boxes):
                    cls_id = int(b.cls[0])
                    label = res.names.get(cls_id, f"class_{cls_id}")
                    conf = float(b.conf[0])
                    xyxyn = b.xyxyn[0].tolist() if hasattr(b, "xyxyn") and len(b.xyxyn) > 0 else [0, 0, 1, 1]
                    is_vio = label.lower().startswith("no-")
                    raw_detections.append({
                        "_track_id": idx + 1,
                        "label": label,
                        "conf": conf,
                        "confidence": conf,
                        "box": [round(float(xyxyn[0]), 4), round(float(xyxyn[1]), 4), round(float(xyxyn[2]), 4), round(float(xyxyn[3]), 4)],
                        "compliant": not is_vio,
                        "is_violation": is_vio,
                    })

    overlay_detections = format_detections_for_overlay(raw_detections, violations_only=violations_only)
    violations = [d["label"] for d in overlay_detections]

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": camera_id,
        "source_type": "uploaded_image",
        "session_id": None,
        "detections": overlay_detections,
        "severity": "critical" if len(violations) > 0 else "ok",
        "violations": violations,
        "violations_only": True,
        "zone": None,
    }

    if consumer_manager:
        consumer_manager.latest_detections[camera_id] = snapshot

    return {
        "status": "success",
        "use_case": "uc3",
        "camera_id": camera_id,
        "source_type": "uploaded_image",
        "resolution": f"{w}x{h}",
        "raw_detections_count": len(raw_detections),
        "violations_count": len(violations),
        "detections": overlay_detections,
        "violations": violations,
        "violations_only": True,
    }

@router.get("/health")
async def get_health() -> Dict[str, Any]:
    if consumer_manager is None:
        raise HTTPException(status_code=503, detail="UC3 service initializing")

    now = time.monotonic()
    last_age = round(now - consumer_manager.last_frame_processed_at, 2) if consumer_manager.last_frame_processed_at > 0 else -1.0

    return {
        "status": "ok",
        "service": "uc3-ppe-detection",
        "model_loaded": consumer_manager._model is not None,
        "mode": "production_integrated",
        "last_frame_age_seconds": last_age,
        "tracked_cameras": list(consumer_manager.latest_detections.keys()),
    }

@router.get("/metrics")
async def get_metrics() -> Response:
    # Prometheus plain text metrics output
    now = time.monotonic()
    last_age = round(now - consumer_manager.last_frame_processed_at, 2) if consumer_manager and consumer_manager.last_frame_processed_at > 0 else -1.0
    cam_count = len(consumer_manager.latest_detections) if consumer_manager else 0

    metrics_text = (
        "# HELP uc3_active_cameras Number of cameras actively tracked by UC3\n"
        "# TYPE uc3_active_cameras gauge\n"
        f"uc3_active_cameras {cam_count}\n"
        "# HELP uc3_last_frame_age_seconds Age of last processed frame in seconds\n"
        "# TYPE uc3_last_frame_age_seconds gauge\n"
        f"uc3_last_frame_age_seconds {last_age}\n"
    )

    return Response(content=metrics_text, media_type="text/plain")
