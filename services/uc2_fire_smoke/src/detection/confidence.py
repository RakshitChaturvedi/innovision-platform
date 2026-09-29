"""
Stage 5 / 6 — Configurable Weighted Confidence Fusion.

Combines YOLO, HSV, texture, temporal, and motion scores
using env-configurable weights. Generates the final confidence
score and maps it to AlertSeverity.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from shared.contracts.enums import AlertSeverity
from services.uc2_fire_smoke.src.config import settings

logger = logging.getLogger("innovision.uc2.detection.confidence")


@dataclass
class FusionResult:
    final_confidence: float
    severity: AlertSeverity
    verification_score: float
    alert_type: str


class ConfidenceFusion:
    """
    Weighted multi-stage confidence score fusion engine.
    """

    def __init__(self) -> None:
        self.weights = settings.fusion_weights

    def fuse(
        self,
        yolo_conf: float,
        hsv_score: float,
        texture_score: float,
        temporal_score: float,
        det_type: str,
        motion_score: float = 0.5,
    ) -> FusionResult:
        w = self.weights
        total_weight = w.yolo + w.hsv + w.texture + w.temporal + w.motion

        if total_weight <= 0:
            fused = yolo_conf
            v_score = (hsv_score + texture_score) / 2.0
        else:
            fused = (
                w.yolo * yolo_conf
                + w.hsv * hsv_score
                + w.texture * texture_score
                + w.temporal * temporal_score
                + w.motion * motion_score
            ) / total_weight

            v_weight = w.hsv + w.texture + w.temporal + w.motion
            v_score = (
                (w.hsv * hsv_score + w.texture * texture_score + w.temporal * temporal_score + w.motion * motion_score)
                / v_weight
                if v_weight > 0
                else 0.5
            )

        fused = round(max(0.0, min(1.0, fused)), 4)
        v_score = round(max(0.0, min(1.0, v_score)), 4)

        severity = self.determine_severity(det_type, fused)
        alert_type = f"{det_type}_detected"

        return FusionResult(
            final_confidence=fused,
            severity=severity,
            verification_score=v_score,
            alert_type=alert_type,
        )

    @staticmethod
    def determine_severity(detection_type: str, confidence: float) -> AlertSeverity:
        if detection_type == "fire":
            if confidence >= 0.80:
                return AlertSeverity.CRITICAL
            if confidence >= 0.60:
                return AlertSeverity.HIGH
            if confidence >= 0.40:
                return AlertSeverity.MEDIUM
            return AlertSeverity.LOW

        if detection_type == "smoke":
            if confidence >= 0.85:
                return AlertSeverity.HIGH
            if confidence >= 0.50:
                return AlertSeverity.MEDIUM
            return AlertSeverity.LOW

        if detection_type in ("sparks", "spark"):
            if confidence >= 0.85:
                return AlertSeverity.HIGH
            if confidence >= 0.55:
                return AlertSeverity.MEDIUM
            return AlertSeverity.LOW

        return AlertSeverity.LOW


def fuse_confidence(
    yolo_conf: float,
    hsv_score: float,
    texture_score: float,
    temporal_score: float,
    motion_score: float,
) -> float:
    fusion = ConfidenceFusion()
    res = fusion.fuse(
        yolo_conf=yolo_conf,
        hsv_score=hsv_score,
        texture_score=texture_score,
        temporal_score=temporal_score,
        det_type="fire",
        motion_score=motion_score,
    )
    return res.final_confidence


def determine_severity(detection_type: str, confidence: float) -> str:
    return ConfidenceFusion.determine_severity(detection_type, confidence).value


def determine_alert_type(detected_types: Set[str]) -> str:
    has_fire = "fire" in detected_types
    has_smoke = "smoke" in detected_types

    if has_fire and has_smoke:
        return "fire_and_smoke_detected"
    if has_fire:
        return "fire_detected"
    if has_smoke:
        return "smoke_detected"
    return "unknown_detection"
