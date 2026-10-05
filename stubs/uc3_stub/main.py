"""
UC3 Stub / Full Service Runner for Platform Testing.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Dict, List, Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as aioredis
from redis.exceptions import ResponseError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("uc3_stub")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_URL = os.environ.get("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}")
TEST_CAMERA_ID = UUID(os.environ.get("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000003"))
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDS", "12"))

UC3_SCENARIOS = [
    {
        "alert_type": "ppe_violation",
        "severity": AlertSeverity.HIGH,
        "title": "[STUB] PPE violation — construction zone a",
        "description": "Worker detected without helmet in Construction Zone A.",
        "metadata": {
            "track_id": 7,
            "missing_ppe": ["helmet"],
            "zone": "Construction Zone A",
            "compliance_score": 0.0,
        },
    },
    {
        "alert_type": "ppe_violation",
        "severity": AlertSeverity.MEDIUM,
        "title": "[STUB] PPE partial violation — loading dock",
        "description": "Worker missing safety jacket at Loading Dock.",
        "metadata": {
            "track_id": 23,
            "missing_ppe": ["safety_jacket"],
            "zone": "Loading Dock",
            "compliance_score": 0.5,
        },
    },
]

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


app = FastAPI(title="Innovision UC3 PPE Compliance Service", version="2.0.0")

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/uc3/compliance/ppe-summary", response_model=PPEComplianceSummary)
async def get_ppe_summary():
    cameras: List[CameraComplianceSummary] = []
    total_violations = 0

    for cam_id, state in _latest_detections.items():
        detections = state.get("detections", [])
        violation_count = sum(
            1 for d in detections
            if d.get("color") == "#ff3333" or d.get("label", "").startswith("Person") and "Missing" in d.get("label", "")
        )
        compliant_count = sum(1 for d in detections if d.get("color") == "#00e676")
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


async def stub_publisher_loop():
    try:
        redis_client = await aioredis.from_url(REDIS_URL)
        publisher = AlertPublisher(redis_client)
        i = 0
        while True:
            s = UC3_SCENARIOS[i % len(UC3_SCENARIOS)]
            i += 1
            alert = AlertEvent(
                camera_id=TEST_CAMERA_ID,
                timestamp=datetime.now(timezone.utc),
                severity=s["severity"],
                alert_type=s["alert_type"],
                title=s["title"],
                description=s["description"],
                source_event_id=uuid4(),
                source_uc=SourceUC.UC3,
                metadata=s["metadata"],
            )
            await publisher.publish(alert)
            await asyncio.sleep(ALERT_INTERVAL)
    except Exception as exc:
        logger.warning("Stub publisher loop stopped: %s", exc)


if __name__ == "__main__":
    asyncio.run(stub_publisher_loop())