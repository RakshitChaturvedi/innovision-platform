"""
API Router for UC3 PPE Detection Service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from pydantic import BaseModel
from fastapi import APIRouter

from services.uc3_ppe_detection.src import config

router = APIRouter()

# In-memory storage for latest camera detections
_latest_detections: Dict[str, Dict[str, Any]] = {}


class CameraComplianceSummary(BaseModel):
    camera_id: str
    violation_count: int
    compliant_count: int
    last_updated: str


class PPEComplianceSummary(BaseModel):
    total_cameras: int
    total_violations: int
    cameras: List[CameraComplianceSummary]
    generated_at: str


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "service": config.SERVICE_NAME,
        "version": config.PIPELINE_VERSION,
    }


@router.get("/cameras/{camera_id}/latest-detections")
@router.get("/uc3/cameras/{camera_id}/latest-detections")
async def get_latest_detections(camera_id: str):
    if camera_id in _latest_detections:
        return _latest_detections[camera_id]
    return {
        "camera_id": camera_id,
        "detections": [],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/uc3/compliance/ppe-summary", response_model=PPEComplianceSummary)
async def get_ppe_summary():
    """Return aggregated PPE violation statistics across all tracked cameras."""
    cameras: List[CameraComplianceSummary] = []
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


def update_latest_detections(camera_id: str, payload: dict) -> None:
    _latest_detections[str(camera_id)] = payload
