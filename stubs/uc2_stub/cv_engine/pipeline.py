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
import cv2

from shared.contracts.enums import AlertSeverity, SourceUC
from stubs.uc2_stub.cv_engine.config import settings
from stubs.uc2_stub.cv_engine.confidence import ConfidenceFusion
from stubs.uc2_stub.cv_engine.engine import YOLOEngine
from stubs.uc2_stub.cv_engine.suppression import FalseAlarmSuppressor
from stubs.uc2_stub.cv_engine.temporal import TemporalPersistenceTracker
from stubs.uc2_stub.cv_engine.verifier import DeterministicVerifier
from stubs.uc2_stub.cv_engine.zone_engine import ZoneEngine, ZoneMatch

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

    def _detect_cv_sparks(self, frame_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Classical CV extraction layer for flying incandescent sparks and arc flash bursts.
        Recovers fast-moving transient particles, streaks, and showers that YOLO may miss.
        """
        h, w = frame_bgr.shape[:2]
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        v_chan = hsv[:, :, 2]
        # High brightness spark particles (white & golden sparks)
        spark_mask = cv2.inRange(v_chan, 215, 255)

        # Exclude deep flame cores (orange-red high-saturation areas)
        flame_mask = cv2.inRange(hsv, np.array([0, 110, 120]), np.array([35, 255, 255]))
        flame_dil = cv2.dilate(flame_mask, cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11)), iterations=1)
        spark_only_mask = cv2.bitwise_and(spark_mask, cv2.bitwise_not(flame_dil))

        # Connect nearby flying sparks into coherent burst envelopes
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        dilated = cv2.dilate(spark_only_mask, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            area = cw * ch
            if area < 30 or area > 160000:
                continue
            pad = 4
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w, x + cw + pad)
            y2 = min(h, y + ch + pad)

            roi_gray = gray[y1:y2, x1:x2]
            if roi_gray.size == 0:
                continue
            std_val = float(np.std(roi_gray))
            max_val = float(np.max(roi_gray))
            avg_val = float(np.mean(roi_gray))

            if max_val < 220 or (max_val - avg_val) < 20.0:
                continue
            if avg_val > 200 and std_val < 20.0:
                continue

            spk_px = int(np.count_nonzero(spark_only_mask[y1:y2, x1:x2]))
            if spk_px < 3:
                continue

            conf = float(min(0.92, max(0.55, 0.45 + (std_val / 40.0) * 0.35 + min(0.15, spk_px / 150.0))))
            candidates.append({
                "detection_type": "sparks",
                "confidence": round(conf, 4),
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "raw_class_name": "sparks",
                "class_id": 2,
                "source": "cv_spark",
            })
        return candidates

    def process_frame(
        self,
        camera_id: str,
        frame_seq: int,
        frame_bgr: np.ndarray,
        prev_frame_bgr: Optional[np.ndarray] = None,
        single_frame: bool = False,
    ) -> DetectionResult:
        """
        Execute full 6-stage pipeline on a camera frame.
        """
        t_start = time.perf_counter()
        h, w = frame_bgr.shape[:2]

        # Stage 1: YOLO26m Fire & Smoke Inference
        raw_candidates, infer_latency = self.yolo.infer(frame_bgr)
        t_after_infer = time.perf_counter()

        # Stage 1.2: CV Spark Burst & Shower Enhancement (captures flying sparks missed by YOLO)
        cv_sparks = self._detect_cv_sparks(frame_bgr)
        for cv_s in cv_sparks:
            c_bb = cv_s["bbox"]
            c_area = max(1, (c_bb["x2"] - c_bb["x1"]) * (c_bb["y2"] - c_bb["y1"]))
            duplicate = any(
                yd["detection_type"] in ("sparks", "spark") and
                (max(0, min(c_bb["x2"], yd["bbox"]["x2"]) - max(c_bb["x1"], yd["bbox"]["x1"])) *
                 max(0, min(c_bb["y2"], yd["bbox"]["y2"]) - max(c_bb["y1"], yd["bbox"]["y1"]))) / float(c_area) > 0.50
                for yd in raw_candidates
            )
            if not duplicate:
                raw_candidates.append(cv_s)

        confirmed: List[ConfirmedDetection] = []
        suppressed: List[Dict[str, Any]] = []

        # Stage 1.5: Enclosure pre-filtering (sparks inside large smoke clouds suppressed)
        smoke_boxes = [c["bbox"] for c in raw_candidates if c["detection_type"] == "smoke"]
        valid_candidates = []
        for cand in raw_candidates:
            if cand["detection_type"] in ("sparks", "spark") and smoke_boxes:
                sb = cand["bbox"]
                sb_area = max(1, (sb["x2"] - sb["x1"]) * (sb["y2"] - sb["y1"]))
                inside_smoke = False
                for mb in smoke_boxes:
                    mb_area = max(1, (mb["x2"] - mb["x1"]) * (mb["y2"] - mb["y1"]))
                    if mb_area > sb_area * 1.8:
                        ix1 = max(sb["x1"], mb["x1"])
                        iy1 = max(sb["y1"], mb["y1"])
                        ix2 = min(sb["x2"], mb["x2"])
                        iy2 = min(sb["y2"], mb["y2"])
                        if ix2 > ix1 and iy2 > iy1:
                            inter_area = (ix2 - ix1) * (iy2 - iy1)
                            if (inter_area / float(sb_area)) > 0.25:
                                inside_smoke = True
                                break
                if inside_smoke:
                    suppressed.append({
                        "detection_type": cand["detection_type"],
                        "bbox": cand["bbox"],
                        "reason": "spark_enclosed_in_smoke",
                        "yolo_confidence": cand["confidence"],
                        "zone_id": "zone-default",
                        "frame_seq": frame_seq,
                    })
                    continue
            valid_candidates.append(cand)

        active_detection_keys: List[str] = []

        for candidate in valid_candidates:
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
            if not v_result.passed:
                suppressed.append({
                    "detection_type": det_type,
                    "bbox": bbox_dict,
                    "reason": v_result.rejection_reason or "verifier_rejected",
                    "yolo_confidence": yolo_conf,
                    "zone_id": zone_match.zone_id,
                    "frame_seq": frame_seq,
                })
                continue

            hsv_score = v_result.hsv_score
            texture_score = v_result.texture_score

            # Stage 4: Temporal Persistence
            is_spark = det_type in ("sparks", "spark")
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

            # Sparks are fast-moving transient hazards that scatter and travel across frames.
            # Once verified by Stage 2/3 deterministic verifier, confirm immediately.
            if is_spark:
                is_persistent = True
                temp_score = max(temp_score, 0.85)

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
                temporal_score=temp_score if not (single_frame or is_spark) else max(temp_score, 0.75),
                det_type=det_type,
            )

            # Check if detection passes minimal confidence and temporal gate
            if (is_persistent or single_frame or is_spark) and fusion_result.final_confidence >= settings.conf_threshold:
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
