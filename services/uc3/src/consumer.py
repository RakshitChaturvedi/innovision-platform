"""
UC3 Stream Consumer — XREADGROUP frame consumer for Redis streams frames:{camera_id}
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional
from uuid import UUID

import cv2
import httpx
import numpy as np
import redis.asyncio as aioredis
from minio import Minio
from ultralytics import YOLO

from shared.contracts.frame_event import FrameEvent
import services.uc3.src.ppe_config as config
from services.uc3.src.compliance import evaluate_compliance, new_session_state
from services.uc3.src.motion_gate import MotionState, compute_motion_mask, should_run_inference
from services.uc3.src.person_gate import detect_persons
from services.uc3.src.mannequin_gate import enabled as mannequin_enabled, detect as mannequin_detect, exclusion_regions, mask_regions, drop_in_regions
from services.uc3.src.publisher import UC3EventPublisher

logger = logging.getLogger("uc3_consumer")

CLASS_COLORS: Dict[str, str] = {
    "helmet": "#FFC53D",
    "hard-hat": "#FFC53D",
    "hardhat": "#FFC53D",
    "safety-vest": "#FF8A3D",
    "safety_vest": "#FF8A3D",
    "vest": "#FF8A3D",
    "gloves": "#4ADE80",
    "glove": "#4ADE80",
    "shoes": "#38BDF8",
    "shoe": "#38BDF8",
    "boots": "#38BDF8",
    "boot": "#38BDF8",
    "glasses": "#F472B6",
    "goggles": "#F472B6",
    "mask": "#2DD4BF",
    "face-mask": "#2DD4BF",
    "person": "#94A3B8",
    "worker": "#94A3B8",
    "head": "#C084FC",
    "face": "#818CF8",
    "hands": "#60A5FA",
    "hand": "#60A5FA",
    "foot": "#F87171",
    "feet": "#F87171",
    "no-helmet": "#FF3333",
    "no-vest": "#FF3333",
    "no-gloves": "#FF3333",
    "no-shoe": "#FF3333",
    "no-shoes": "#FF3333",
    "no-goggles": "#FF3333",
    "no-mask": "#FF3333",
}

def get_class_color(label: str, is_compliant: bool = True) -> str:
    norm_lbl = label.strip().lower().replace("_", "-")
    if not is_compliant or norm_lbl.startswith("no-"):
        return "#FF3333"
    return CLASS_COLORS.get(norm_lbl, "#94A3B8")

class UC3ConsumerManager:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        publisher: UC3EventPublisher,
        camera_registry_url: str,
        group_name: str = "uc3_group",
    ) -> None:
        self._redis = redis_client
        self._publisher = publisher
        self._registry_url = camera_registry_url.rstrip("/")
        self._group_name = group_name
        self._stopped = False

        # Latest detection state per camera (in-memory cache for API endpoint)
        self.latest_detections: Dict[str, Dict[str, Any]] = {}
        self.last_frame_processed_at: float = 0.0

        # Model instance & tracker
        logger.info("loading_yolo_model path=%s", config.MODEL_PATH)
        self._model = YOLO(config.MODEL_PATH)
        logger.info("yolo_model_loaded classes=%s", getattr(self._model, "names", {}))

        # Per-camera session state
        self._worker_states: Dict[str, Any] = {}
        self._motion_states: Dict[str, MotionState] = {}

        # MinIO client for frame loading
        minio_endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
        minio_access = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        minio_secret = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
        minio_secure = os.environ.get("MINIO_SECURE", "false").lower() in ("true", "1", "yes")
        self._minio_client = Minio(
            endpoint=minio_endpoint,
            access_key=minio_access,
            secret_key=minio_secret,
            secure=minio_secure,
        )

    async def discover_cameras(self) -> List[str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(f"{self._registry_url}/cameras/by-uc/uc3")
                if res.status_code == 200:
                    data = res.json()
                    return data.get("camera_ids", [])
        except Exception as e:
            logger.warning("camera_discovery_failed url=%s error=%s", self._registry_url, e)

        # Fallback default test camera
        test_cam = os.environ.get("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000003")
        return [test_cam]

    async def _load_frame_bytes(self, frame_event: FrameEvent) -> Optional[bytes]:
        provider = (frame_event.frame_provider.value if hasattr(frame_event.frame_provider, "value") else str(frame_event.frame_provider)).lower()
        ref = frame_event.frame_reference

        if not ref:
            return None

        # 1. Primary provider check
        if provider == "redis":
            try:
                frame_bytes = await self._redis.get(ref)
                if frame_bytes:
                    return frame_bytes
            except Exception as e:
                logger.warning("redis_frame_load_failed ref=%s error=%s", ref, e)

        elif provider == "minio":
            try:
                bucket = os.environ.get("MINIO_FRAMES_BUCKET", "innovision-frames")
                res = await asyncio.to_thread(self._minio_client.get_object, bucket, ref)
                return res.read()
            except Exception as e:
                logger.warning("minio_frame_load_failed ref=%s error=%s", ref, e)

        # Fallback attempt across providers if reference was not found
        try:
            frame_bytes = await self._redis.get(ref)
            if frame_bytes:
                return frame_bytes
        except Exception:
            pass

        return None

    async def run(self) -> None:
        logger.info("uc3_consumer_loop_started group=%s", self._group_name)

        while not self._stopped:
            try:
                camera_ids = await self.discover_cameras()
                if not camera_ids:
                    await asyncio.sleep(2.0)
                    continue

                for camera_id in camera_ids:
                    stream_key = f"frames:{camera_id}"
                    try:
                        await self._redis.xgroup_create(stream_key, self._group_name, id="0", mkstream=True)
                    except Exception:
                        pass # Group already exists

                    await self._consume_camera_stream(camera_id, stream_key)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("uc3_consumer_main_loop_error error=%s", e)
                await asyncio.sleep(2.0)

    async def _consume_camera_stream(self, camera_id: str, stream_key: str) -> None:
        consumer_name = f"uc3_worker_{os.uname().nodename if hasattr(os, 'uname') else 'worker'}"

        try:
            messages = await self._redis.xreadgroup(
                groupname=self._group_name,
                consumername=consumer_name,
                streams={stream_key: ">"},
                count=1,
                block=500,
            )

            if not messages:
                return

            for _, entries in messages:
                for message_id, fields in entries:
                    if isinstance(message_id, bytes):
                        message_id = message_id.decode()

                    payload = fields.get(b"data") or fields.get("data")
                    if payload is None:
                        await self._redis.xack(stream_key, self._group_name, message_id)
                        continue

                    if isinstance(payload, bytes):
                        payload = payload.decode()

                    try:
                        event_dict = json.loads(payload)
                        frame_event = FrameEvent.model_validate(event_dict)
                    except Exception as e:
                        logger.error("invalid_frame_event stream=%s error=%s", stream_key, e)
                        await self._redis.xack(stream_key, self._group_name, message_id)
                        continue

                    # Process frame event
                    await self._process_frame_event(frame_event)

                    # Acknowledge after processing complete
                    await self._redis.xack(stream_key, self._group_name, message_id)

        except Exception as e:
            logger.error("consume_stream_failed stream=%s error=%s", stream_key, e)

    async def _process_frame_event(self, frame_event: FrameEvent) -> None:
        camera_id = str(frame_event.camera_id)
        now_ts = time.monotonic()
        dt_now = datetime.now(timezone.utc)

        jpeg_bytes = await self._load_frame_bytes(frame_event)
        if not jpeg_bytes:
            return

        frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return

        h, w = frame.shape[:2]

        # Init per-camera state
        if camera_id not in self._worker_states:
            self._worker_states[camera_id] = new_session_state()
        if camera_id not in self._motion_states:
            self._motion_states[camera_id] = MotionState()

        m_state = self._motion_states[camera_id]
        w_state = self._worker_states[camera_id]

        # Stage 1: Person Gate & Motion Gate
        candidate_boxes = await asyncio.to_thread(detect_persons, frame)
        if not should_run_inference(frame, candidate_boxes, m_state, now_ts):
            return

        # Stage 2: Mannequin Gate
        masked_frame = frame
        ex_regions: List[Any] = []
        if mannequin_enabled():
            res = mannequin_detect(frame)
            if res is not None:
                p_boxes, m_boxes = res
                ex_regions = exclusion_regions(m_boxes, p_boxes)
                masked_frame = mask_regions(frame, ex_regions)

        # Stage 3: YOLO Inference & ByteTrack Tracking
        results = await asyncio.to_thread(
            self._model.track,
            source=masked_frame,
            persist=True,
            tracker=config.TRACKER_CONFIG_PATH if os.path.exists(config.TRACKER_CONFIG_PATH) else "bytetrack.yaml",
            conf=config.CONF_THRESHOLD,
            imgsz=config.IMAGE_SIZE,
            verbose=False,
        )

        if not results:
            return

        res = results[0]
        boxes = res.boxes
        if boxes is None or len(boxes) == 0:
            return

        names = res.names
        raw_detections: List[Dict[str, Any]] = []

        for b in boxes:
            xyxy = b.xyxy[0].tolist()
            conf = float(b.conf[0])
            cls_id = int(b.cls[0])
            track_id = int(b.id[0]) if b.id is not None else None

            label_name = names.get(cls_id, f"class_{cls_id}").lower()

            # Normalized 0.0 - 1.0 bounding box coordinates
            norm_box = (
                max(0.0, min(1.0, xyxy[0] / w)),
                max(0.0, min(1.0, xyxy[1] / h)),
                max(0.0, min(1.0, xyxy[2] / w)),
                max(0.0, min(1.0, xyxy[3] / h)),
            )

            raw_detections.append({
                "box": norm_box,
                "conf": conf,
                "label": label_name,
                "_track_id": track_id,
            })

        # Drop detections inside mannequin regions if applicable
        if ex_regions:
            raw_detections = drop_in_regions(raw_detections, ex_regions, w, h)

        # Stage 4: Zone Determination & Compliance Evaluation
        zone_id, required_ppe, zone_name = await self._publisher.get_camera_zone_and_rules(camera_id)

        severity, unique_vio, worker_violations = evaluate_compliance(
            detections=raw_detections,
            worker_states=w_state,
            now=now_ts,
            required_ppe=required_ppe,
        )

        # Format detection state for API overlay
        formatted_detections: List[Dict[str, Any]] = []
        for d in raw_detections:
            norm_b = d["box"]
            lbl = d["label"]
            norm_lbl = lbl.strip().lower().replace("_", "-")
            comp = False if norm_lbl.startswith("no-") else d.get("compliant", True)
            formatted_detections.append({
                "track_id": d.get("_track_id"),
                "label": lbl.replace("-", " ").title(),
                "bbox": {
                    "x1": norm_b[0],
                    "y1": norm_b[1],
                    "x2": norm_b[2],
                    "y2": norm_b[3],
                },
                "color": get_class_color(lbl, comp),
                "compliant": comp,
                "confidence": round(d["conf"], 2),
            })

        self.latest_detections[camera_id] = {
            "timestamp": dt_now.isoformat(),
            "camera_id": camera_id,
            "detections": formatted_detections,
            "severity": severity,
            "violations": unique_vio,
            "zone": {
                "id": str(zone_id) if zone_id else None,
                "name": zone_name,
                "required_ppe": list(required_ppe) if required_ppe else ["helmet", "vest", "shoes", "gloves", "mask"],
            },
        }
        self.last_frame_processed_at = now_ts

        # Stage 5: Persist UC3 Analytics Event & Publish Alerts
        uc3_evt_id = await self._publisher.persist_uc3_event(
            camera_id=UUID(camera_id),
            event_type="ppe_compliance_evaluated" if not unique_vio else "ppe_violation_detected",
            track_id=None,
            missing_ppe=unique_vio,
            present_ppe=[d["label"].lower() for d in raw_detections if d.get("compliant", True)],
            compliance_score=1.0 if not unique_vio else 0.5,
            timestamp=dt_now,
            frame_reference=frame_event.frame_reference,
            frame_provider=frame_event.frame_provider.value if hasattr(frame_event.frame_provider, "value") else str(frame_event.frame_provider),
            metadata={"severity": severity, "detections_count": len(formatted_detections)},
            zone_id=zone_id,
        )

        for w_vio in worker_violations:
            await self._publisher.publish_violation_alert(
                camera_id=UUID(camera_id),
                worker_violation=w_vio,
                raw_frame=frame,
                detections=formatted_detections,
                timestamp=dt_now,
                zone_id=zone_id,
                uc3_event_id=uc3_evt_id,
                source_frame_reference=frame_event.frame_reference,
                source_frame_provider=frame_event.frame_provider.value if hasattr(frame_event.frame_provider, "value") else str(frame_event.frame_provider),
            )

    def stop(self) -> None:
        self._stopped = True
