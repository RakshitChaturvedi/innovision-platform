"""
DetectionPipeline — Unified 6-Stage Fire & Smoke Detection Orchestrator.

Order of Execution:
  Stage 1 — YOLO26m Fire & Smoke Inference
  Stage 2 — Deterministic HSV Color Verification
  Stage 3 — Texture, Gradient, & Entropy Verification
  Stage 4 — Temporal Persistence Verification
  Stage 5 — False Alarm Suppression (Fog, Steam, Reflections, Exhaust, LED)
  Stage 6 — Configurable Weighted Confidence Fusion

Returns a structured DetectionResult object containing confirmed detections,
suppressed candidates, timing metrics, and enriched metadata.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from shared.contracts.enums import AlertSeverity, SourceUC
from services.uc2_fire_smoke.src.config import settings
from services.uc2_fire_smoke.src.detection.confidence import ConfidenceFusion
from services.uc2_fire_smoke.src.detection.engine import YOLOEngine
from services.uc2_fire_smoke.src.detection.suppression import FalseAlarmSuppressor
from services.uc2_fire_smoke.src.detection.temporal import TemporalPersistenceTracker
from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier
from services.uc2_fire_smoke.src.detection.zone_engine import ZoneEngine, ZoneMatch

logger = logging.getLogger("innovision.uc2.detection_pipeline")


@dataclass
class ConfirmedDetection:
    detection_type: str  # "fire" or "smoke"
    severity: AlertSeverity
    final_confidence: float
    bbox: Dict[str, int]  # {"x1": int, "y1": int, "x2": int, "y2": int}
    yolo_confidence: float
    verification_score: float
    zone: ZoneMatch
    persistence_count: int
    verification_details: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DetectionResult:
    camera_id: str
    frame_seq: int
    has_detections: bool
    confirmed_detections: List[ConfirmedDetection]
    suppressed_detections: List[Dict[str, Any]]
    inference_latency_ms: float
    verification_latency_ms: float
    total_pipeline_latency_ms: float
    timestamp: float = field(default_factory=time.time)


class DetectionPipeline:
    """
    Single entry point orchestrator for the 6-stage fire and smoke detection pipeline.
    Ensures workers never call individual verification components independently.
    """

    def __init__(
        self,
        yolo_engine: Optional[YOLOEngine] = None,
        zone_engine: Optional[ZoneEngine] = None,
    ) -> None:
        self.yolo = yolo_engine or YOLOEngine()
        self.verifier = DeterministicVerifier()
        self.temporal_tracker = TemporalPersistenceTracker(
            persistence_threshold=settings.temporal_frames,
            smoothing_alpha=settings.smoothing_alpha,
        )
        self.suppressor = FalseAlarmSuppressor()
        self.fusion = ConfidenceFusion()
        self.zone_engine = zone_engine or ZoneEngine()
        self.pipeline_version = settings.pipeline_version
        self.model_version = settings.model_version

    def process_frame(
        self,
        camera_id: str,
        frame_seq: int,
        frame_bgr: np.ndarray,
        prev_frame_bgr: Optional[np.ndarray] = None,
    ) -> DetectionResult:
        """
        Execute full 6-stage pipeline on a camera frame.
        """
        t_start = time.perf_counter()
        h, w = frame_bgr.shape[:2]

        # Stage 1: YOLO26m Fire & Smoke Inference
        raw_candidates, infer_latency = self.yolo.infer(frame_bgr)
        t_after_infer = time.perf_counter()

        confirmed: List[ConfirmedDetection] = []
        suppressed: List[Dict[str, Any]] = []

        active_detection_keys: List[str] = []

        for candidate in raw_candidates:
            det_type = candidate["detection_type"]
            bbox_dict = candidate["bbox"]
            x1, y1, x2, y2 = bbox_dict["x1"], bbox_dict["y1"], bbox_dict["x2"], bbox_dict["y2"]
            bbox_tuple = (x1, y1, x2, y2)
            yolo_conf = candidate["confidence"]

            # Spatial Zone Assignment
            zone_match = self.zone_engine.filter_and_assign_zones(
                camera_id=camera_id,
                bbox=bbox_tuple,
                frame_shape=(h, w),
                detection_class=det_type,
            ) or ZoneMatch(
                zone_id="zone-default",
                zone_name="Default",
                zone_priority="MEDIUM",
                overlap_ratio=1.0,
                is_inside=True,
            )

            # Crop ROI
            x1_c, y1_c = max(0, min(w - 1, x1)), max(0, min(h - 1, y1))
            x2_c, y2_c = max(0, min(w, x2)), max(0, min(h, y2))
            if x2_c <= x1_c or y2_c <= y1_c:
                continue
            roi = frame_bgr[y1_c:y2_c, x1_c:x2_c]

            # Stage 2 & Stage 3: Deterministic HSV, Texture, Gradient & Entropy Verification
            v_result = self.verifier.verify(roi, det_type)
            hsv_score = v_result.hsv_score
            texture_score = v_result.texture_score

            # Stage 4: Temporal Persistence
            # Key based on spatial centroid proximity to preserve temporal track
            cx_norm = round((x1 + x2) / (2.0 * w), 2)
            cy_norm = round((y1 + y2) / (2.0 * h), 2)
            temporal_key = f"{det_type}:{cx_norm}:{cy_norm}"
            active_detection_keys.append(temporal_key)

            is_persistent, p_count, temp_score = self.temporal_tracker.update(
                camera_id=camera_id,
                det_key=temporal_key,
                raw_confidence=yolo_conf,
            )

            # Stage 5: False Alarm Suppression
            suppression_decision = self.suppressor.evaluate(
                roi=roi,
                det_type=det_type,
                yolo_confidence=yolo_conf,
                hsv_score=hsv_score,
                texture_score=texture_score,
                prev_frame_roi=(
                    prev_frame_bgr[y1_c:y2_c, x1_c:x2_c]
                    if prev_frame_bgr is not None and prev_frame_bgr.shape == frame_bgr.shape
                    else None
                ),
            )

            if suppression_decision.suppressed:
                suppressed.append({
                    "detection_type": det_type,
                    "bbox": bbox_dict,
                    "reason": suppression_decision.reason,
                    "yolo_confidence": yolo_conf,
                    "zone_id": zone_match.zone_id,
                    "frame_seq": frame_seq,
                })
                continue

            # Stage 6: Weighted Confidence Fusion
            fusion_result = self.fusion.fuse(
                yolo_conf=yolo_conf,
                hsv_score=hsv_score,
                texture_score=texture_score,
                temporal_score=temp_score,
                det_type=det_type,
            )

            # Check if detection passes minimal confidence and temporal gate
            if is_persistent and fusion_result.final_confidence >= settings.conf_threshold:
                # Upgrade severity if inside a CRITICAL or HIGH priority zone
                severity = fusion_result.severity
                if zone_match.zone_priority.upper() == "CRITICAL" and severity in (
                    AlertSeverity.MEDIUM, AlertSeverity.HIGH
                ):
                    severity = AlertSeverity.CRITICAL
                elif zone_match.zone_priority.upper() == "HIGH" and severity == AlertSeverity.LOW:
                    severity = AlertSeverity.MEDIUM

                det_obj = ConfirmedDetection(
                    detection_type=det_type,
                    severity=severity,
                    final_confidence=round(fusion_result.final_confidence, 4),
                    bbox=bbox_dict,
                    yolo_confidence=yolo_conf,
                    verification_score=round(fusion_result.verification_score, 4),
                    zone=zone_match,
                    persistence_count=p_count,
                    verification_details={
                        "hsv_score": hsv_score,
                        "texture_score": texture_score,
                        "temporal_score": temp_score,
                        "motion_score": v_result.motion_score,
                        "entropy": v_result.entropy,
                        "laplacian_var": v_result.laplacian_var,
                    },
                    metadata={
                        "model_version": self.model_version,
                        "pipeline_version": self.pipeline_version,
                        "frame_seq": frame_seq,
                    },
                )
                confirmed.append(det_obj)

        # Decay inactive tracks
        self.temporal_tracker.decay(camera_id, active_detection_keys)

        t_end = time.perf_counter()
        verify_latency = (t_end - t_after_infer) * 1000.0
        total_latency = (t_end - t_start) * 1000.0

        return DetectionResult(
            camera_id=camera_id,
            frame_seq=frame_seq,
            has_detections=len(confirmed) > 0,
            confirmed_detections=confirmed,
            suppressed_detections=suppressed,
            inference_latency_ms=infer_latency,
            verification_latency_ms=verify_latency,
            total_pipeline_latency_ms=total_latency,
            timestamp=t_start,
        )
