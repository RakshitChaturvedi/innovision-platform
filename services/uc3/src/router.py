"""
UC3 FastAPI Router — Overlay API, Health & Prometheus Metrics
"""

from __future__ import annotations

import time
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, Response

router = APIRouter(prefix="/uc3", tags=["uc3-ppe-detection"])

consumer_manager = None  # Injected from main.py

@router.get("/cameras/{camera_id}/latest-detections")
async def get_latest_detections(camera_id: str) -> Dict[str, Any]:
    if consumer_manager is None:
        raise HTTPException(status_code=503, detail="UC3 service is initializing")

    detections_data = consumer_manager.latest_detections.get(camera_id)
    if not detections_data:
        return {
            "timestamp": "",
            "camera_id": camera_id,
            "detections": [],
            "severity": "ok",
            "violations": [],
        }

    return detections_data

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
