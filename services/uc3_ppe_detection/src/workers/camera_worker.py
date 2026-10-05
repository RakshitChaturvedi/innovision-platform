"""
UC3 Camera Worker — Frame consumer & inference worker per camera stream.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import cv2
import numpy as np
from ultralytics import YOLO

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

from services.uc3_ppe_detection.src import config
from services.uc3_ppe_detection.src.api.router import update_latest_detections
from services.uc3_ppe_detection.src.compliance import WorkerStates, evaluate_compliance
from services.uc3_ppe_detection.src.mannequin_gate import filter_mannequins
from services.uc3_ppe_detection.src.motion_gate import MotionState
from services.uc3_ppe_detection.src.person_gate import has_person
from services.uc3_ppe_detection.src.storage.minio_client import MinIOClient

logger = logging.getLogger(__name__)

CLASS_COLORS = {
    # PPE Items
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
    "safety-glasses": "#F472B6",
    "face-mask": "#2DD4BF",
    "mask": "#2DD4BF",
    "face-guard": "#34D399",
    "ear-muffs": "#EAB308",
    "medical-suit": "#22D3EE",
    "safety-suit": "#FB7185",
    # Negative / Violation classes
    "no-helmet": "#FF3333",
    "no-vest": "#FF3333",
    "no-gloves": "#FF3333",
    "no-shoe": "#FF3333",
    "no-shoes": "#FF3333",
    "no-goggles": "#FF3333",
    "no-mask": "#FF3333",
    # Body Parts & Workers
    "person": "#94A3B8",
    "worker": "#94A3B8",
    "head": "#C084FC",
    "face": "#818CF8",
    "hands": "#60A5FA",
    "foot": "#F87171",
    "tools": "#A78BFA",
}


def get_detection_color(label: str, is_compliant: bool = True) -> str:
    norm_lbl = label.strip().lower().replace("_", "-")
    if not is_compliant or norm_lbl.startswith("no-"):
        return "#FF3333"
    return CLASS_COLORS.get(norm_lbl, "#94A3B8")


class CameraWorker:
    def __init__(
        self,
        camera_id: UUID,
        camera_name: str,
        redis_client: Any,
        publisher: AlertPublisher,
        minio_client: Optional[MinIOClient] = None,
    ) -> None:
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.redis = redis_client
        self.publisher = publisher
        self.minio = minio_client or MinIOClient()

        self.model: Optional[YOLO] = None
        self.motion_state = MotionState()
        self.worker_states = WorkerStates()
        self.last_alert_time: Dict[str, float] = {}

    def _get_model(self) -> YOLO:
        if self.model is None:
            if config.MODEL_PATH.exists():
                self.model = YOLO(str(config.MODEL_PATH))
            else:
                # Fallback to yolo11n or default model
                self.model = YOLO("yolo11n.pt")
        return self.model

    async def process_frame(self, frame_event_dict: dict, msg_id: str, stream_name: str) -> None:
        try:
            frame_bytes: Optional[bytes] = None
            frame_ref = frame_event_dict.get("frame_reference")
            if frame_ref:
                frame_bytes = await self.redis.get(frame_ref)

            if not frame_bytes:
                raw_b64 = frame_event_dict.get("frame_data") or frame_event_dict.get("data")
                if raw_b64 and isinstance(raw_b64, str):
                    pad = len(raw_b64) % 4
                    if pad:
                        raw_b64 += "=" * (4 - pad)
                    try:
                        frame_bytes = base64.b64decode(raw_b64)
                    except Exception:
                        pass
                elif raw_b64 and isinstance(raw_b64, bytes):
                    frame_bytes = raw_b64

            if not frame_bytes:
                return

            nparr = np.frombuffer(frame_bytes, np.uint8)
            frame_img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame_img is None:
                return

            now = time.time()
            frame_seq = int(frame_event_dict.get("frame_seq", 0))

            # Motion & Person gating
            if not self.motion_state.check_motion(frame_img):
                return

            if not has_person(frame_img):
                return

            # Real Inference & ByteTrack Tracking
            model = self._get_model()
            track_kwargs = {
                "source": frame_img,
                "conf": config.CONF_THRESHOLD,
                "iou": config.IOU_THRESHOLD,
                "imgsz": config.IMAGE_SIZE,
                "persist": True,
                "verbose": False,
            }
            if config.TRACKER_CONFIG_PATH.exists():
                track_kwargs["tracker"] = str(config.TRACKER_CONFIG_PATH)

            results = model.track(**track_kwargs)

            raw_detections: list[dict] = []
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        xyxy = box.xyxy[0].cpu().numpy().tolist()
                        cls_id = int(box.cls[0].cpu().item())
                        conf_val = float(box.conf[0].cpu().item())
                        label_name = r.names.get(cls_id, f"cls_{cls_id}")
                        track_id = int(box.id[0].cpu().item()) if box.id is not None else None

                        raw_detections.append({
                            "box": [int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])],
                            "label": label_name,
                            "conf": conf_val,
                            "track_id": track_id,
                        })

            filtered_dets = filter_mannequins(raw_detections)

            # Evaluate Compliance
            severity_str, frame_violations, worker_violations = evaluate_compliance(
                filtered_dets, self.worker_states, now
            )

            # Format overlay payload
            overlay_detections = []
            h, w = frame_img.shape[:2]
            for d in filtered_dets:
                bx = d["box"]
                is_comp = d.get("compliant", True)
                lbl_lower = d["label"].lower()
                is_violation = (not is_comp) or lbl_lower.startswith("no-")
                color = get_detection_color(d["label"], is_compliant=not is_violation)
                track_id = d.get("track_id")
                prefix = f"W-{track_id} " if track_id and lbl_lower in ("person", "worker") else ""

                if is_violation:
                    lbl_text = f"{prefix}{d['label'].title()} (Missing PPE)"
                else:
                    lbl_text = f"{prefix}{d['label'].title()} {int(d['conf'] * 100)}%"

                overlay_detections.append({
                    "label": lbl_text,
                    "confidence": round(d["conf"], 2),
                    "color": color,
                    "compliant": not is_violation,
                    "box": {
                        "x1": round(bx[0] / w, 4),
                        "y1": round(bx[1] / h, 4),
                        "x2": round(bx[2] / w, 4),
                        "y2": round(bx[3] / h, 4),
                    },
                })

            update_latest_detections(str(self.camera_id), {
                "camera_id": str(self.camera_id),
                "detections": overlay_detections,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            # Handle Violations and Emit AlertEvents
            for wv in worker_violations:
                ppe_type = wv["ppe_type"]
                track_id = wv["worker_id"]
                cooldown_key = f"{track_id}:{ppe_type}"

                if (now - self.last_alert_time.get(cooldown_key, 0.0)) < config.ALERT_COOLDOWN_S:
                    continue

                self.last_alert_time[cooldown_key] = now

                alert_id = uuid4()
                evidence_key = await self.minio.upload_evidence(
                    camera_id=self.camera_id,
                    alert_id=str(alert_id),
                    image_bgr=frame_img,
                )

                severity_enum = AlertSeverity.HIGH if len(frame_violations) > 1 else AlertSeverity.MEDIUM

                alert = AlertEvent(
                    alert_id=alert_id,
                    camera_id=self.camera_id,
                    timestamp=datetime.now(timezone.utc),
                    severity=severity_enum,
                    alert_type="ppe_violation",
                    title=f"PPE Violation: Missing {ppe_type.replace('_', ' ').title()}",
                    description=(
                        f"Worker #{track_id} detected missing required PPE "
                        f"'{ppe_type}' on Camera {self.camera_name} (Frame {frame_seq})."
                    ),
                    source_event_id=str(frame_event_dict.get("event_id", uuid4())),
                    source_uc=SourceUC.UC3,
                    frame_reference=evidence_key or frame_event_dict.get("frame_reference", ""),
                    frame_provider=FrameProvider.MINIO if evidence_key else FrameProvider.REDIS,
                    metadata={
                        "track_id": track_id,
                        "missing_ppe": [ppe_type],
                        "violation_name": wv["violation"],
                        "confidence": float(wv["confidence"]),
                        "frame_seq": frame_seq,
                        "camera_id": str(self.camera_id),
                        "camera_name": self.camera_name,
                    },
                )

                await self.publisher.publish(alert)

            # ACK message in Redis stream
            try:
                await self.redis.xack(stream_name, config.REDIS_CONSUMER_GROUP, msg_id)
            except Exception:
                pass

        except Exception as exc:
            logger.error("Error processing frame for camera %s: %s", self.camera_id, exc)
