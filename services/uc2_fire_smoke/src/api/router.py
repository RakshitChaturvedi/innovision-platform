"""
Internal UC2 Analytics Service API Routes.
Exposes liveness, readiness, diagnostics, Prometheus metrics, MJPEG camera preview,
pipeline status, compliance stats for Reporting, mode switching, and model metadata.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from services.uc2_fire_smoke.src.config import settings
from services.uc2_fire_smoke.src.metrics.prometheus import get_latest_metrics

logger = logging.getLogger("innovision.uc2.api")

router = APIRouter()


class ModeChangeRequest(BaseModel):
    mode: str = Field(..., description="Detection mode: SENSITIVE, BALANCED, or AGGRESSIVE")


@router.get("/health", summary="Basic Health Check")
async def health_check(request: Request) -> Dict[str, Any]:
    """Return health status and active cameras (backward-compatible)."""
    pm = getattr(request.app.state, "pipeline_manager", None)
    active_count = len(pm._workers) if pm else 0
    return {
        "status": "healthy",
        "service": settings.service_name,
        "phase": "2",
        "pipeline_version": settings.pipeline_version,
        "model_version": settings.model_version,
        "active_cameras": active_count,
    }


@router.get("/health/live", summary="Liveness Probe")
async def liveness_probe() -> Dict[str, Any]:
    """Kubernetes/Container liveness probe — verifies the service process is alive."""
    return {
        "status": "alive",
        "timestamp": time.time(),
        "service": settings.service_name,
    }


@router.get("/health/ready", summary="Readiness Probe")
async def readiness_probe(request: Request) -> Response:
    """
    Kubernetes/Container readiness probe — verifies service can process frames.
    Checks Redis connectivity, YOLO model readiness, and MinIO storage connectivity.
    Returns 503 if any required dependency is unavailable.
    """
    pm = getattr(request.app.state, "pipeline_manager", None)
    dependencies: Dict[str, Any] = {
        "redis": "unknown",
        "model": "unknown",
        "minio": "unknown",
    }
    is_ready = True

    # 1. Redis connectivity
    if pm and pm.redis:
        try:
            await asyncio.wait_for(pm.redis.ping(), timeout=2.0)
            dependencies["redis"] = "connected"
        except Exception as exc:
            dependencies["redis"] = f"unhealthy: {exc}"
            is_ready = False
    else:
        dependencies["redis"] = "not_initialized"
        is_ready = False

    # 2. YOLO model readiness
    if pm and pm.yolo_engine and pm.yolo_engine.is_ready():
        dependencies["model"] = {
            "status": "ready",
            "device": pm.yolo_engine.device,
            "classes": pm.yolo_engine.class_names,
        }
    else:
        dependencies["model"] = "not_ready"
        is_ready = False

    # 3. MinIO connectivity
    if pm and pm.minio:
        try:
            minio_ok = await asyncio.wait_for(pm.minio.check_health(), timeout=2.0)
            dependencies["minio"] = "connected" if minio_ok else "unreachable"
        except Exception as exc:
            dependencies["minio"] = f"unhealthy: {exc}"
    else:
        dependencies["minio"] = "not_initialized"

    payload = {
        "ready": is_ready,
        "service": settings.service_name,
        "active_cameras": len(pm._workers) if pm else 0,
        "dependencies": dependencies,
        "timestamp": time.time(),
    }

    if not is_ready:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload)
    return JSONResponse(status_code=status.HTTP_200_OK, content=payload)


@router.get("/health/diagnostic", summary="Deep Diagnostic Information")
async def diagnostic_endpoint(request: Request) -> Dict[str, Any]:
    """Expose full system diagnostic report for monitoring and troubleshooting."""
    pm = getattr(request.app.state, "pipeline_manager", None)
    if not pm:
        raise HTTPException(status_code=503, detail="Pipeline manager not initialized")

    return {
        "service": settings.service_name,
        "pipeline_version": settings.pipeline_version,
        "detection_mode": settings.detection_mode,
        "pipeline_status": pm.get_pipeline_status(),
        "model_diagnostic": pm.yolo_engine.get_model_info() if pm.yolo_engine else None,
        "settings": {
            "device": settings.device,
            "img_size": settings.inference_size,
            "conf_threshold": settings.conf_threshold,
            "temporal_frames": settings.temporal_frames,
            "alert_cooldown_s": settings.alert_cooldown_s,
            "stream_batch_size": settings.stream_batch_size,
        },
    }


@router.get("/metrics", summary="Prometheus Metrics")
async def metrics_endpoint() -> Response:
    """Prometheus metrics scrape target."""
    metrics_data, content_type = get_latest_metrics()
    return Response(content=metrics_data, media_type=content_type)


@router.get("/pipeline/status", summary="Pipeline Status")
async def pipeline_status(request: Request) -> Dict[str, Any]:
    """Return status of all workers, camera discovery, and detection pipeline."""
    pm = getattr(request.app.state, "pipeline_manager", None)
    if not pm:
        raise HTTPException(status_code=503, detail="Pipeline manager not initialized")
    return pm.get_pipeline_status()


@router.get("/preview/{camera_id}", summary="Live MJPEG Preview")
async def camera_preview(camera_id: str, request: Request) -> StreamingResponse:
    """Stream live annotated MJPEG stream for a camera."""
    pm = getattr(request.app.state, "pipeline_manager", None)
    if not pm:
        raise HTTPException(status_code=503, detail="Pipeline manager not running")

    async def _frame_generator():
        boundary = "frame"
        while True:
            jpeg_bytes = pm.get_preview_jpeg(camera_id)
            if jpeg_bytes:
                yield (
                    b"--" + boundary.encode("utf-8") + b"\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(jpeg_bytes)).encode("utf-8") + b"\r\n\r\n"
                    + jpeg_bytes + b"\r\n"
                )
            await asyncio.sleep(0.1)  # ~10 FPS preview streaming

    return StreamingResponse(
        _frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/metrics/compliance", summary="Reporting Service Compliance Metrics")
async def compliance_metrics(request: Request) -> Dict[str, Any]:
    """
    Returns aggregated real compliance statistics consumed by Innovision Reporting Service.
    Calculates live metrics from actual worker states rather than hardcoded mocks.
    """
    pm = getattr(request.app.state, "pipeline_manager", None)
    status_data = pm.get_pipeline_status() if pm else {}
    workers = status_data.get("workers", [])

    total_received = sum(w.get("received_frames", 0) for w in workers)
    total_processed = sum(w.get("processed_frames", 0) for w in workers)
    total_dropped = sum(w.get("dropped_frames", 0) for w in workers)

    # Calculate real availability / compliance score
    if total_received > 0:
        compliance_score = round(max(0.0, min(100.0, (total_processed / total_received) * 100.0)), 2)
    else:
        compliance_score = 100.0

    return {
        "service": settings.service_name,
        "use_case": "uc2",
        "compliance_score": compliance_score,
        "active_cameras": status_data.get("active_camera_count", 0),
        "online_cameras": status_data.get("online_cameras", 0),
        "pipeline_version": settings.pipeline_version,
        "model_version": settings.model_version,
        "uptime_seconds": status_data.get("uptime_seconds", 0),
        "total_received_frames": total_received,
        "total_processed_frames": total_processed,
        "total_dropped_frames": total_dropped,
    }


@router.post("/mode", summary="Switch Detection Sensitivity Mode")
async def set_detection_mode(payload: ModeChangeRequest) -> Dict[str, Any]:
    """Switch detection operating mode (SENSITIVE, BALANCED, AGGRESSIVE)."""
    valid_modes = ["SENSITIVE", "BALANCED", "AGGRESSIVE"]
    mode_upper = payload.mode.upper()
    if mode_upper not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Mode must be one of {valid_modes}")

    settings.detection_mode = mode_upper
    if mode_upper == "SENSITIVE":
        settings.conf_threshold = 0.15
        settings.temporal_frames = 2
    elif mode_upper == "AGGRESSIVE":
        settings.conf_threshold = 0.35
        settings.temporal_frames = 4
    else:  # BALANCED
        settings.conf_threshold = 0.20
        settings.temporal_frames = 3

    return {
        "status": "updated",
        "detection_mode": settings.detection_mode,
        "conf_threshold": settings.conf_threshold,
        "temporal_frames": settings.temporal_frames,
    }


@router.get("/model", summary="Model Metadata")
async def model_metadata(request: Request) -> Dict[str, Any]:
    """Get active YOLO model information, checksum verification, and loaded weights status."""
    pm = getattr(request.app.state, "pipeline_manager", None)
    if pm and pm.yolo_engine:
        return pm.yolo_engine.get_model_info()
    return {
        "model_version": settings.model_version,
        "model_path": settings.yolo_model_path,
        "ready": False,
    }

