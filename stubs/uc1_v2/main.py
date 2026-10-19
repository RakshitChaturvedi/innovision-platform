"""
UC1-v2 Person & Intrusion Detection Service.

UC1 discovers its assigned cameras from Camera Registry, consumes
the corresponding ingestion frame streams from Redis, performs real
YOLO person detection, evaluates geometric polygon zone containment
for true intrusion detection, publishes standard AlertEvents, and serves
latest-detections with bounding box overlays and zone coordinates for the dashboard.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import cv2
import httpx
import numpy as np
import redis.asyncio as aioredis
from fastapi import FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from redis.exceptions import ResponseError
from ultralytics import YOLO

# Ensure repository root and /app are on python search path for shared packages
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

# ─── Logging ──────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger("innovision.uc1.service")


# ─── Configuration ───────────────────────────────────────────────

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
CAMERA_REGISTRY_URL = os.getenv("CAMERA_REGISTRY_URL", "http://camera_registry:8011")
UC_ID = "uc1"

REDIS_CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "uc1_v2_group")
REDIS_CONSUMER_NAME = os.getenv("REDIS_CONSUMER_NAME", "uc1_v2_worker_1")

MODEL_PATH = os.getenv("YOLO_MODEL", "yolov8n.pt")
CONFIDENCE = float(os.getenv("YOLO_CONFIDENCE", "0.35"))

ALERTS_STREAM = "alerts:live"
PEOPLE_THRESHOLD = int(os.getenv("PEOPLE_THRESHOLD", "3"))
ALERT_COOLDOWN_SECONDS = float(os.getenv("ALERT_COOLDOWN_SECONDS", "15"))

ALERT_MGMT_URL = os.getenv("ALERT_MGMT_URL", "http://alert_management:8000")
INCIDENT_MGMT_URL = os.getenv("INCIDENT_MGMT_URL", "http://incident_management:8000")
PLATFORM_POLL_INTERVAL_S = float(os.getenv("PLATFORM_POLL_INTERVAL_S", "3"))


# ─── Zone Management & Geometry ──────────────────────────────────

class ZoneConfigItem(BaseModel):
    zone_id: str = Field(..., description="Unique zone identifier")
    zone_name: str = Field(..., description="Human readable zone name")
    polygon: List[List[float]] = Field(..., description="List of [x, y] coordinates, normalized 0.0-1.0 or pixel coordinates")
    priority: str = Field("CRITICAL", description="Zone priority: CRITICAL, HIGH, MEDIUM, LOW")
    is_restricted: bool = Field(True, description="True if unauthorized presence constitutes an intrusion violation")
    color: Optional[str] = Field(None, description="Hex color for visualization, defaults to red for restricted")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ZoneConfigPayload(BaseModel):
    zones: List[ZoneConfigItem]


# Default perimeter zone for cameras that do not yet have customized polygon configurations
DEFAULT_DEMO_ZONE: Dict[str, Any] = {
    "zone_id": "zone-perimeter-danger",
    "zone_name": "Restricted Security Perimeter",
    "polygon": [[0.15, 0.20], [0.85, 0.20], [0.85, 0.85], [0.15, 0.85]],
    "priority": "CRITICAL",
    "is_restricted": True,
    "color": "#EF4444",
    "metadata": {"description": "Automated security restricted polygon perimeter"},
}

# In-memory storage for camera zones: camera_id -> list of zone dicts
camera_zones: Dict[str, List[Dict[str, Any]]] = {}


def get_camera_zones(camera_id: str) -> List[Dict[str, Any]]:
    """Retrieve zones for a camera, falling back to standard default security zone if unconfigured."""
    if camera_id in camera_zones and camera_zones[camera_id]:
        return camera_zones[camera_id]
    return [DEFAULT_DEMO_ZONE]


def point_in_polygon(polygon: List[Any], pt: Tuple[float, float], frame_shape: Tuple[int, int]) -> bool:
    """
    Test if point pt=(cx, cy) is inside the polygon using cv2.pointPolygonTest.
    Handles normalized (0.0 - 1.0) and pixel coordinates seamlessly.
    """
    h, w = frame_shape
    if len(polygon) < 3:
        return False

    pts = []
    for p in polygon:
        px = p[0] if isinstance(p, (list, tuple)) else p.get("x", 0.0)
        py = p[1] if isinstance(p, (list, tuple)) else p.get("y", 0.0)
        if 0.0 <= px <= 1.0 and 0.0 <= py <= 1.0:
            pts.append([int(px * w), int(py * h)])
        else:
            pts.append([int(px), int(py)])

    pts_arr = np.array(pts, dtype=np.int32)
    cx, cy = pt
    test_pt = (float(cx * w if 0.0 <= cx <= 1.0 else cx), float(cy * h if 0.0 <= cy <= 1.0 else cy))
    dist = cv2.pointPolygonTest(pts_arr, test_pt, False)
    return dist >= 0


def safe_uuid(val: Any) -> UUID:
    """Convert string or UUID safely; generates UUID if invalid."""
    if isinstance(val, UUID):
        return val
    try:
        return UUID(str(val))
    except Exception:
        return uuid.uuid4()


# ─── Runtime state ────────────────────────────────────────────────

camera_ids: List[str] = []
camera_streams: Dict[str, str] = {}

latest_result: Dict[str, Any] = {
    "status": "starting",
    "camera_id": None,
    "frame_seq": None,
    "people": 0,
    "intrusions": 0,
    "resolution": None,
    "jpeg_bytes": 0,
    "cache": "unknown",
    "cache_fetch_ms": None,
    "detection_ms": None,
    "frames_processed": 0,
    "cache_misses": 0,
    "last_update": None,
}

pipeline_state: Dict[str, Any] = {
    "stage_ingestion": "idle",
    "stage_detection": "idle",
    "stage_alert_published": "idle",
    "stage_alert_persisted": "idle",
    "stage_incident_created": "idle",
    "last_alert_id": None,
    "last_alert_at": None,
}

platform_view: Dict[str, Any] = {
    "alerts": [],
    "incidents": [],
    "platform_reachable": False,
    "last_poll_error": None,
}

# Cooldown tracking: (camera_id, zone_or_type) -> last_fired_monotonic_timestamp
_last_alert_fired_at: Dict[str, float] = {}

# In-memory latest detections for dashboard overlay polling
latest_camera_detections: Dict[str, Dict[str, Any]] = {}
latest_session_detections: Dict[str, Dict[str, Any]] = {}


# ─── Camera Registry Discovery ───────────────────────────────────

async def discover_cameras(client: httpx.AsyncClient) -> List[str]:
    response = await client.get(f"{CAMERA_REGISTRY_URL}/cameras/by-uc/{UC_ID}")
    response.raise_for_status()
    payload = response.json()
    cams = payload.get("camera_ids", [])
    if not isinstance(cams, list):
        raise RuntimeError("Camera Registry returned an invalid camera assignment response")
    return cams


async def load_camera_assignments() -> None:
    global camera_ids, camera_streams
    async with httpx.AsyncClient(timeout=5.0) as client:
        discovered_camera_ids = await discover_cameras(client)

    camera_ids = [c for c in discovered_camera_ids if c]
    camera_streams = {cid: f"frames:{cid}" for cid in camera_ids}
    logger.info("camera_registry_discovery uc=%s cameras=%s", UC_ID, camera_ids)


# ─── Alert Publishing ────────────────────────────────────────────

async def maybe_fire_alerts(
    redis_client: aioredis.Redis,
    camera_id: str,
    frame_seq: int,
    people_count: int,
    intrusions_by_zone: Dict[str, List[Dict[str, Any]]],
    frame_reference: Optional[str] = None,
    frame_provider: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """
    Publish AlertEvents according to platform contract:
    1. If polygon zone intrusions occurred: generate CRITICAL intrusion_detected alerts per zone.
    2. Fallback: If no polygon zones were configured and people >= threshold: generate headcount_breach alert.
    """
    now = time.monotonic()
    cam_uuid = safe_uuid(camera_id)

    # 1. Process polygon zone intrusions
    if intrusions_by_zone:
        zones_map = {z["zone_id"]: z for z in get_camera_zones(camera_id)}
        for zone_id, intruders in intrusions_by_zone.items():
            zone = zones_map.get(zone_id, {})
            zone_name = zone.get("zone_name", "Restricted Area")
            priority = zone.get("priority", "CRITICAL").upper()

            cooldown_key = f"{camera_id}:{zone_id}"
            last_fired = _last_alert_fired_at.get(cooldown_key, 0.0)
            if now - last_fired < ALERT_COOLDOWN_SECONDS:
                continue

            _last_alert_fired_at[cooldown_key] = now
            alert_id = uuid.uuid4()
            source_event_id = uuid.uuid4()
            timestamp = datetime.now(timezone.utc)

            severity = AlertSeverity.CRITICAL if priority == "CRITICAL" else AlertSeverity.HIGH
            title = f"Restricted Zone Intrusion — {len(intruders)} person(s) in {zone_name}"
            description = (
                f"UC1 Person Detection pipeline detected unauthorized human intrusion "
                f"into restricted zone '{zone_name}' on camera {camera_id}. "
                f"Frame sequence {frame_seq}. Intruders detected: {len(intruders)}."
            )

            # Contract requires frame_reference & frame_provider to both be set or both None
            f_ref = frame_reference if (frame_reference and frame_provider) else None
            f_prov = FrameProvider(frame_provider) if (frame_reference and frame_provider) else None

            alert = AlertEvent(
                alert_id=alert_id,
                camera_id=cam_uuid,
                timestamp=timestamp,
                severity=severity,
                alert_type="intrusion_detected",
                title=title,
                description=description,
                source_event_id=source_event_id,
                source_uc=SourceUC.UC1,
                frame_reference=f_ref,
                frame_provider=f_prov,
                status=AlertStatus.PENDING,
                metadata={
                    "zone_id": zone_id,
                    "zone_name": zone_name,
                    "intruders_count": len(intruders),
                    "total_people": people_count,
                    "frame_seq": frame_seq,
                    "camera_id": camera_id,
                    "session_id": session_id,
                    "source_uc": "uc1",
                    "intruders": intruders,
                },
            )

            payload = alert.model_dump_json()
            await redis_client.xadd(ALERTS_STREAM, {"data": payload})
            pipeline_state["stage_alert_published"] = "active"
            pipeline_state["last_alert_id"] = str(alert_id)
            pipeline_state["last_alert_at"] = time.time()
            logger.warning(
                "uc1_intrusion_alert_published alert_id=%s camera_id=%s zone=%s intruders=%d",
                alert_id, camera_id, zone_name, len(intruders),
            )
        return

    # 2. Fallback: Headcount threshold check if no polygon intrusions occurred
    if people_count >= PEOPLE_THRESHOLD:
        cooldown_key = f"{camera_id}:headcount"
        last_fired = _last_alert_fired_at.get(cooldown_key, 0.0)
        if now - last_fired < ALERT_COOLDOWN_SECONDS:
            return

        _last_alert_fired_at[cooldown_key] = now
        alert_id = uuid.uuid4()
        source_event_id = uuid.uuid4()
        timestamp = datetime.now(timezone.utc)
        severity = AlertSeverity.CRITICAL if people_count >= PEOPLE_THRESHOLD * 2 else AlertSeverity.HIGH

        title = f"Headcount Threshold Exceeded — {people_count} persons detected"
        description = (
            f"UC1 detected {people_count} persons in frame "
            f"(threshold: {PEOPLE_THRESHOLD}). "
            f"Frame sequence {frame_seq}."
        )

        f_ref = frame_reference if (frame_reference and frame_provider) else None
        f_prov = FrameProvider(frame_provider) if (frame_reference and frame_provider) else None

        alert = AlertEvent(
            alert_id=alert_id,
            camera_id=cam_uuid,
            timestamp=timestamp,
            severity=severity,
            alert_type="headcount_breach",
            title=title,
            description=description,
            source_event_id=source_event_id,
            source_uc=SourceUC.UC1,
            frame_reference=f_ref,
            frame_provider=f_prov,
            status=AlertStatus.PENDING,
            metadata={
                "people_count": people_count,
                "threshold": PEOPLE_THRESHOLD,
                "frame_seq": frame_seq,
                "camera_id": camera_id,
                "session_id": session_id,
                "source_uc": "uc1",
            },
        )

        payload = alert.model_dump_json()
        await redis_client.xadd(ALERTS_STREAM, {"data": payload})
        pipeline_state["stage_alert_published"] = "active"
        pipeline_state["last_alert_id"] = str(alert_id)
        pipeline_state["last_alert_at"] = time.time()
        logger.warning(
            "uc1_headcount_alert_published alert_id=%s camera_id=%s people=%d",
            alert_id, camera_id, people_count,
        )


# ─── Detection & Zone Intrusion Engine ───────────────────────────

def detect_people_and_intrusions(
    model: YOLO,
    frame: np.ndarray,
    camera_id: str,
) -> Tuple[int, int, List[Dict[str, Any]], Dict[str, List[Dict[str, Any]]]]:
    """
    Executes YOLO person detection and evaluates polygon zone containment.
    Returns:
      people_count, intruder_count, detections_list, intrusions_by_zone_dict
    """
    results = model(
        frame,
        conf=CONFIDENCE,
        classes=[0],  # class 0 = person in standard COCO / YOLO
        verbose=False,
    )

    h, w = frame.shape[:2]
    zones = get_camera_zones(camera_id)

    detections: List[Dict[str, Any]] = []
    intrusions_by_zone: Dict[str, List[Dict[str, Any]]] = {}
    people_count = 0
    intruder_count = 0

    for result in results:
        if result.boxes is None or len(result.boxes) == 0:
            continue

        people_count += len(result.boxes)
        for idx, box in enumerate(result.boxes):
            conf = float(box.conf[0]) if hasattr(box, "conf") and len(box.conf) > 0 else 0.50
            if hasattr(box, "xyxyn") and len(box.xyxyn) > 0:
                xyxyn = box.xyxyn[0].tolist()
                x1, y1, x2, y2 = float(xyxyn[0]), float(xyxyn[1]), float(xyxyn[2]), float(xyxyn[3])
            else:
                xyxy = box.xyxy[0].tolist()
                x1, y1, x2, y2 = xyxy[0] / w, xyxy[1] / h, xyxy[2] / w, xyxy[3] / h

            # Bottom center (feet on the ground) represents person's spatial presence
            feet_cx = (x1 + x2) / 2.0
            feet_cy = y2

            # Check polygon zone containment
            matched_zone: Optional[Dict[str, Any]] = None
            is_intrusion = False

            for zone in zones:
                poly = zone.get("polygon", [])
                if point_in_polygon(poly, (feet_cx, feet_cy), (h, w)):
                    matched_zone = zone
                    if zone.get("is_restricted", True):
                        is_intrusion = True
                    break

            if is_intrusion and matched_zone:
                intruder_count += 1
                zone_id = matched_zone["zone_id"]
                zone_name = matched_zone.get("zone_name", "Restricted Area")
                det_item = {
                    "track_id": int(idx + 1),
                    "bbox": {
                        "x1": round(x1, 4),
                        "y1": round(y1, 4),
                        "x2": round(x2, 4),
                        "y2": round(y2, 4),
                    },
                    "label": f"INTRUSION ({zone_name}) {int(conf * 100)}%",
                    "color": "#FF3333",
                    "compliant": False,
                    "is_violation": True,
                    "metadata": {
                        "confidence": round(conf, 2),
                        "class": "person",
                        "zone_id": zone_id,
                        "zone_name": zone_name,
                        "feet": [round(feet_cx, 4), round(feet_cy, 4)],
                    },
                }
                detections.append(det_item)
                if zone_id not in intrusions_by_zone:
                    intrusions_by_zone[zone_id] = []
                intrusions_by_zone[zone_id].append(det_item)
            else:
                detections.append({
                    "track_id": int(idx + 1),
                    "bbox": {
                        "x1": round(x1, 4),
                        "y1": round(y1, 4),
                        "x2": round(x2, 4),
                        "y2": round(y2, 4),
                    },
                    "label": f"Person {int(conf * 100)}%",
                    "color": "#38BDF8",
                    "compliant": True,
                    "is_violation": False,
                    "metadata": {
                        "confidence": round(conf, 2),
                        "class": "person",
                        "feet": [round(feet_cx, 4), round(feet_cy, 4)],
                    },
                })

    return people_count, intruder_count, detections, intrusions_by_zone


# ─── Frame Message Processor ─────────────────────────────────────

async def process_message(
    redis_client: aioredis.Redis,
    model: YOLO,
    message_id: str,
    fields: dict[str, str],
) -> None:
    payload = fields.get("data")
    if not payload:
        return

    event = json.loads(payload)
    frame_seq = event["frame_seq"]
    camera_id = str(event["camera_id"])
    frame_reference = event["frame_reference"]
    frame_provider = event["frame_provider"]
    session_id = event.get("session_id")

    pipeline_state["stage_ingestion"] = "active"

    if frame_provider != "redis":
        logger.warning("unsupported_frame_provider camera_id=%s provider=%s", camera_id, frame_provider)
        return

    fetch_start = time.perf_counter()
    jpeg_bytes = await redis_client.get(frame_reference)
    fetch_ms = (time.perf_counter() - fetch_start) * 1000

    if jpeg_bytes is None:
        latest_result["cache_misses"] += 1
        logger.debug("frame_cache_miss camera_id=%s frame_seq=%s", camera_id, frame_seq)
        return

    jpeg_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    frame = cv2.imdecode(jpeg_array, cv2.IMREAD_COLOR)

    if frame is None:
        logger.warning("frame_decode_failed camera_id=%s frame_seq=%s", camera_id, frame_seq)
        return

    pipeline_state["stage_detection"] = "active"
    detection_start = time.perf_counter()

    people, intrusions, detections, intrusions_by_zone = detect_people_and_intrusions(
        model=model,
        frame=frame,
        camera_id=camera_id,
    )

    detection_ms = (time.perf_counter() - detection_start) * 1000
    height, width = frame.shape[:2]

    # Save latest detections for overlay polling with session isolation
    current_zones = get_camera_zones(camera_id)
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": camera_id,
        "session_id": session_id,
        "people_count": people,
        "intrusion_count": intrusions,
        "detections": detections,
        "zones": current_zones,
    }

    latest_camera_detections[camera_id] = snapshot
    if session_id:
        latest_camera_detections[f"{camera_id}:{session_id}"] = snapshot
        latest_session_detections[str(session_id)] = snapshot

    latest_result.update({
        "status": "running",
        "camera_id": camera_id,
        "session_id": session_id,
        "frame_seq": frame_seq,
        "people": people,
        "intrusions": intrusions,
        "resolution": f"{width}x{height}",
        "jpeg_bytes": len(jpeg_bytes),
        "cache": "hit",
        "cache_fetch_ms": round(fetch_ms, 2),
        "detection_ms": round(detection_ms, 2),
        "frames_processed": latest_result["frames_processed"] + 1,
        "last_update": time.time(),
    })

    # Alert pipeline invocation
    await maybe_fire_alerts(
        redis_client=redis_client,
        camera_id=camera_id,
        frame_seq=frame_seq,
        people_count=people,
        intrusions_by_zone=intrusions_by_zone,
        frame_reference=frame_reference,
        frame_provider=frame_provider,
        session_id=session_id,
    )


# ─── Redis Multi-Stream Consumer ─────────────────────────────────

async def ensure_consumer_groups(redis_client: aioredis.Redis) -> None:
    for stream in camera_streams.values():
        try:
            await redis_client.xgroup_create(
                name=stream,
                groupname=REDIS_CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info("consumer_group_created stream=%s group=%s", stream, REDIS_CONSUMER_GROUP)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise


async def consume(redis_client: aioredis.Redis, model: YOLO) -> None:
    while not camera_streams:
        try:
            await load_camera_assignments()
        except Exception:
            logger.exception("camera_registry_discovery_failed")

        if not camera_streams:
            logger.warning("UC1 has no assigned cameras; retrying in 5s")
            await asyncio.sleep(5)

    await ensure_consumer_groups(redis_client)
    logger.info("UC1 multi-stream consumer started streams=%s", list(camera_streams.values()))

    while True:
        try:
            streams = {stream: ">" for stream in camera_streams.values()}
            messages = await redis_client.xreadgroup(
                groupname=REDIS_CONSUMER_GROUP,
                consumername=REDIS_CONSUMER_NAME,
                streams=streams,
                count=1,
                block=5000,
            )

            if not messages:
                continue

            for stream_name, entries in messages:
                if isinstance(stream_name, bytes):
                    stream_name = stream_name.decode()

                for message_id, fields in entries:
                    if isinstance(message_id, bytes):
                        message_id = message_id.decode()

                    decoded_fields = {
                        (key.decode() if isinstance(key, bytes) else key): (
                            value.decode() if isinstance(value, bytes) else value
                        )
                        for key, value in fields.items()
                    }

                    try:
                        await process_message(redis_client, model, message_id, decoded_fields)
                        await redis_client.xack(stream_name, REDIS_CONSUMER_GROUP, message_id)
                    except Exception:
                        logger.exception("frame_processing_failed stream=%s message_id=%s", stream_name, message_id)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("uc1_multi_stream_consumer_failed")
            await asyncio.sleep(2)


# ─── Platform Poller ─────────────────────────────────────────────

async def poll_platform_state() -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        while True:
            try:
                alerts_response = await client.get(
                    f"{ALERT_MGMT_URL}/alerts",
                    params={"source_uc": UC_ID, "limit": 10},
                )
                alerts_response.raise_for_status()
                alerts = alerts_response.json()

                incidents_response = await client.get(
                    f"{INCIDENT_MGMT_URL}/incidents",
                    params={"limit": 10},
                )
                incidents_response.raise_for_status()
                incidents = incidents_response.json()

                platform_view["alerts"] = alerts
                platform_view["incidents"] = incidents
                platform_view["platform_reachable"] = True
                platform_view["last_poll_error"] = None

                last_alert_id = pipeline_state["last_alert_id"]
                if any(alert.get("alert_id") == last_alert_id for alert in alerts):
                    pipeline_state["stage_alert_persisted"] = "active"

                triggering_alert_row_ids = {
                    alert["id"] for alert in alerts
                    if alert.get("alert_id") == last_alert_id and alert.get("id") is not None
                }
                if any(incident.get("alert_id") in triggering_alert_row_ids for incident in incidents):
                    pipeline_state["stage_incident_created"] = "active"

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                platform_view["platform_reachable"] = False
                platform_view["last_poll_error"] = str(exc)

            await asyncio.sleep(PLATFORM_POLL_INTERVAL_S)


# ─── Application Lifecycle ───────────────────────────────────────

consumer_task: asyncio.Task | None = None
poller_task: asyncio.Task | None = None
redis_client: aioredis.Redis | None = None
model: YOLO | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global consumer_task, poller_task, redis_client, model

    logger.info("starting UC1 Person & Intrusion Detection service")

    try:
        model = YOLO(MODEL_PATH)
    except Exception as e:
        logger.warning("Could not load YOLO from %s (%s). Falling back to yolov8n.pt", MODEL_PATH, e)
        try:
            model = YOLO("yolov8n.pt")
        except Exception as e2:
            logger.error("Failed to load fallback YOLO: %s", e2)
            model = None

    redis_client = aioredis.from_url(REDIS_URL, decode_responses=False)
    try:
        await redis_client.ping()
        latest_result["status"] = "running"
    except Exception as e:
        logger.warning("Redis ping failed at startup: %s", e)

    if model and redis_client:
        consumer_task = asyncio.create_task(consume(redis_client, model))
    poller_task = asyncio.create_task(poll_platform_state())

    yield

    for task in (consumer_task, poller_task):
        if task:
            task.cancel()

    for task in (consumer_task, poller_task):
        if task:
            try:
                await task
            except asyncio.CancelledError:
                pass

    if redis_client:
        await redis_client.aclose()


# ─── FastAPI Application & Routes ────────────────────────────────

app = FastAPI(
    title="Innovision UC1 — Intrusion & Person Detection Service",
    version="2.0.0",
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
    return {
        "status": "healthy",
        "uc": UC_ID,
        "camera_ids": camera_ids,
        "model_loaded": model is not None,
        "version": "2.0.0",
    }


@app.get("/uc1/cameras/{camera_id}/latest-detections")
@app.get("/cameras/{camera_id}/latest-detections")
async def get_latest_detections(
    camera_id: str,
    session_id: Optional[str] = Query(None),
):
    """
    Returns latest detections and polygon zones for camera and/or session.
    Queried by CameraOverlay.tsx in dashboard at ~10 FPS.
    """
    # Check session isolated detections if session_id is provided
    if session_id:
        composite_key = f"{camera_id}:{session_id}"
        if composite_key in latest_camera_detections:
            return latest_camera_detections[composite_key]
        if session_id in latest_session_detections:
            return latest_session_detections[session_id]

    data = latest_camera_detections.get(camera_id)
    if data:
        return data

    # Return empty structured detection response with camera zones
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": camera_id,
        "session_id": session_id,
        "people_count": 0,
        "intrusion_count": 0,
        "detections": [],
        "zones": get_camera_zones(camera_id),
    }


@app.post("/uc1/cameras/{camera_id}/infer-image")
@app.post("/cameras/{camera_id}/infer-image")
async def infer_image_endpoint(camera_id: str, request: Request):
    """
    Direct still-image inference for UC1.
    Accepts raw image bytes or multipart form file, executes YOLO person detection
    and polygon intrusion detection, updates latest detections for the camera, and returns result.
    """
    global model
    if model is None:
        try:
            model = YOLO(MODEL_PATH)
        except Exception:
            model = YOLO("yolov8n.pt")

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

    height, width = frame.shape[:2]
    people, intrusions, detections, intrusions_by_zone = detect_people_and_intrusions(
        model=model,
        frame=frame,
        camera_id=camera_id,
    )

    current_zones = get_camera_zones(camera_id)
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "camera_id": camera_id,
        "session_id": None,
        "source_type": "uploaded_image",
        "people_count": people,
        "intrusion_count": intrusions,
        "detections": detections,
        "zones": current_zones,
    }
    latest_camera_detections[camera_id] = snapshot

    return {
        "status": "success",
        "use_case": "uc1",
        "camera_id": camera_id,
        "source_type": "uploaded_image",
        "resolution": f"{width}x{height}",
        "people_count": people,
        "intrusion_count": intrusions,
        "detections": detections,
        "zones": current_zones,
    }


# ─── Camera Zone Configuration APIs ──────────────────────────────

@app.get("/uc1/cameras/{camera_id}/zones")
@app.get("/cameras/{camera_id}/zones")
async def get_zones_api(camera_id: str):
    return {
        "camera_id": camera_id,
        "zones": get_camera_zones(camera_id),
    }


@app.post("/uc1/cameras/{camera_id}/zones")
@app.post("/cameras/{camera_id}/zones")
async def configure_zones_api(camera_id: str, payload: ZoneConfigPayload):
    """Registers or updates restricted polygon zones for a camera."""
    formatted_zones = [z.model_dump() for z in payload.zones]
    camera_zones[camera_id] = formatted_zones
    logger.info("updated_zones camera_id=%s zone_count=%d", camera_id, len(formatted_zones))
    return {
        "status": "success",
        "camera_id": camera_id,
        "zones": formatted_zones,
    }


@app.delete("/uc1/cameras/{camera_id}/zones")
@app.delete("/cameras/{camera_id}/zones")
async def delete_zones_api(camera_id: str):
    """Resets camera zones back to default perimeter."""
    if camera_id in camera_zones:
        del camera_zones[camera_id]
    return {
        "status": "reset_to_default",
        "camera_id": camera_id,
        "zones": get_camera_zones(camera_id),
    }


# ─── Platform & Pipeline Metrics ─────────────────────────────────

@app.get("/api/latest")
async def get_latest():
    return latest_result


@app.get("/api/pipeline")
async def get_pipeline():
    return pipeline_state


@app.get("/api/platform")
async def get_platform():
    return platform_view


@app.get("/api/cameras")
async def get_cameras():
    return {
        "uc": UC_ID,
        "camera_ids": camera_ids,
        "streams": camera_streams,
    }