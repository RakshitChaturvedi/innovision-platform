"""
Stage 4 / 5 — False Alarm Suppression.

Rejects known false-positive patterns: fog, clouds, vehicle exhaust,
dust, steam, sunlight reflections, lens flare, factory smoke, LED reflections.
Uses configurable negative-classifier rules on ROI features.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("innovision.uc2.detection.suppression")


@dataclass
class SuppressionResult:
    suppressed: bool = False
    reason: str = ""
    category: str = ""  # fog | cloud | exhaust | dust | steam | reflection | flare


@dataclass
class FalseAlarmDecision:
    suppressed: bool = False
    reason: Optional[str] = None
    category: Optional[str] = None


# ── Rule-based negative classifiers ──────────────────────────────────────────

def _is_fog_or_cloud(roi_gray: np.ndarray, roi_hsv: np.ndarray) -> Tuple[bool, str]:
    """Fog/cloud: very uniform brightness, low saturation, low texture."""
    std = float(np.std(roi_gray))
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    avg_val = float(np.mean(roi_hsv[:, :, 2]))
    if std < 8.0 and avg_sat < 25 and avg_val > 140:
        return True, f"fog_cloud(std={std:.1f},sat={avg_sat:.0f},val={avg_val:.0f})"
    return False, ""


def _is_vehicle_exhaust(roi_gray: np.ndarray, roi_hsv: np.ndarray, bbox: Optional[dict] = None) -> Tuple[bool, str]:
    """Vehicle exhaust: small, low-saturation, bottom region of frame."""
    h, w = roi_gray.shape[:2]
    area = h * w
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    y1 = bbox.get("y1", 0) if bbox else 500
    if area < 2000 and avg_sat < 35 and y1 > 400:
        return True, f"exhaust(area={area},sat={avg_sat:.0f})"
    return False, ""


def _is_dust_or_steam(roi_gray: np.ndarray, roi_hsv: np.ndarray) -> Tuple[bool, str]:
    """Dust/steam: very uniform texture with moderate brightness."""
    std = float(np.std(roi_gray))
    avg_val = float(np.mean(roi_hsv[:, :, 2]))
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    entropy = _entropy(roi_gray)
    if std < 12.0 and avg_sat < 20 and 80 < avg_val < 200 and entropy < 4.0:
        return True, f"dust_steam(std={std:.1f},entropy={entropy:.1f})"
    return False, ""


def _is_sunlight_reflection(roi_gray: np.ndarray, roi_hsv: np.ndarray, det_type: str = "", hsv_score: float = 0.0) -> Tuple[bool, str]:
    """Sunlight/lens flare: extremely bright, uncoloured/desaturated hot spots without flame characteristics."""
    if det_type == "fire" and hsv_score >= 0.25:
        return False, ""
    avg_val = float(np.mean(roi_hsv[:, :, 2]))
    max_val = float(np.max(roi_hsv[:, :, 2]))
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    bright_ratio = float(np.count_nonzero(roi_gray > 240)) / max(roi_gray.size, 1)
    if avg_val > 220 and bright_ratio > 0.4 and avg_sat < 50:
        return True, f"sunlight(val={avg_val:.0f},bright_pct={bright_ratio:.2f},sat={avg_sat:.0f})"
    if max_val > 252 and bright_ratio > 0.6 and avg_sat < 40:
        return True, f"lens_flare(max={max_val:.0f},bright_pct={bright_ratio:.2f},sat={avg_sat:.0f})"
    return False, ""


def _is_led_reflection(roi_gray: np.ndarray, roi_hsv: np.ndarray) -> Tuple[bool, str]:
    """LED/indicator reflections: tiny bright spots with saturated colours."""
    h, w = roi_gray.shape[:2]
    area = h * w
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    avg_val = float(np.mean(roi_hsv[:, :, 2]))
    if area < 400 and avg_val > 200 and avg_sat > 150:
        return True, f"led_reflection(area={area},sat={avg_sat:.0f})"
    return False, ""


def _is_small_light_or_indicator(roi_gray: np.ndarray, roi_hsv: np.ndarray, det_type: str = "") -> Tuple[bool, str]:
    """Small lamp, LED indicator, or tiny spotlight: round/compact bright core without flying spark characteristics."""
    if det_type not in ("sparks", "spark"):
        return False, ""
    h, w = roi_gray.shape[:2]
    area = h * w
    if area > 3600:
        return False, ""
    max_val = float(np.max(roi_hsv[:, :, 2]))
    if max_val < 180:
        return False, ""
    bright = (roi_gray > 190).astype(np.uint8)
    contours, _ = cv2.findContours(bright, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for c in contours:
        c_area = cv2.contourArea(c)
        if c_area < 6:
            continue
        peri = cv2.arcLength(c, True)
        if peri > 0:
            circularity = 4 * np.pi * c_area / (peri * peri)
            x, y, cw, ch = cv2.boundingRect(c)
            aspect = max(cw, ch) / max(min(cw, ch), 1)
            if circularity > 0.40 and aspect < 1.7 and c_area > 8:
                return True, f"small_light_or_indicator(area={c_area:.0f},circ={circularity:.2f},aspect={aspect:.2f})"
    return False, ""


def _is_specular_surface_reflection(roi_gray: np.ndarray, roi_hsv: np.ndarray, det_type: str = "") -> Tuple[bool, str]:
    """Light reflections, surface glints, and glare on polished floors or metallic equipment."""
    if det_type not in ("sparks", "spark"):
        return False, ""
    avg_sat = float(np.mean(roi_hsv[:, :, 1]))
    avg_val = float(np.mean(roi_hsv[:, :, 2]))
    max_val = float(np.max(roi_hsv[:, :, 2]))
    bright_ratio = float(np.count_nonzero(roi_gray > 200)) / max(roi_gray.size, 1)
    if max_val > 210 and avg_sat < 50.0 and (bright_ratio > 0.12 or avg_val > 130.0):
        return True, f"specular_reflection(val={avg_val:.0f},sat={avg_sat:.0f},ratio={bright_ratio:.2f})"
    return False, ""


def _entropy(gray: np.ndarray) -> float:
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
    hist = hist.ravel() / (hist.sum() + 1e-7)
    return float(-np.sum(hist * np.log2(hist + 1e-7)))


class FalseAlarmSuppressor:
    """
    Object-oriented suppressor interface used by DetectionPipeline.
    """

    def evaluate(
        self,
        roi: np.ndarray,
        det_type: str,
        yolo_confidence: float,
        hsv_score: float,
        texture_score: float,
        prev_frame_roi: Optional[np.ndarray] = None,
    ) -> FalseAlarmDecision:
        if roi.size == 0 or roi.shape[0] < 4 or roi.shape[1] < 4:
            return FalseAlarmDecision(suppressed=True, reason="roi_too_small", category="noise")

        roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        roi_hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        # Check sunlight / flare
        is_sunlight, reason = _is_sunlight_reflection(roi_gray, roi_hsv, det_type=det_type, hsv_score=hsv_score)
        if is_sunlight:
            return FalseAlarmDecision(suppressed=True, reason=reason, category="reflection")

        # Motion analysis if previous frame ROI is available
        has_dynamic_motion = False
        if prev_frame_roi is not None and prev_frame_roi.shape == roi.shape:
            prev_gray = cv2.cvtColor(prev_frame_roi, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(roi_gray, prev_gray)
            motion_ratio = float(np.count_nonzero(diff > 15)) / max(diff.size, 1)
            spark_diff = cv2.absdiff(roi_gray, prev_gray)
            spark_motion = float(np.count_nonzero(spark_diff > 12)) / max(spark_diff.size, 1)
            if spark_motion >= 0.008:
                has_dynamic_motion = True

            # If fire/smoke has zero motion over multiple frames and low confidence, suppress
            if motion_ratio < 0.001 and yolo_confidence < 0.35 and hsv_score < 0.4:
                return FalseAlarmDecision(suppressed=True, reason="static_scene_low_confidence", category="static")

            # Sparks are dynamic fast-moving particles; static ceiling lights or screens have near-zero motion
            if det_type in ("sparks", "spark") and spark_motion < 0.008:
                return FalseAlarmDecision(
                    suppressed=True,
                    reason=f"stationary_spark_fixture (motion={spark_motion:.4f})",
                    category="static_spark",
                )

        # Check small lights / indicator LEDs (stationary or single-frame round bright spots)
        if not has_dynamic_motion:
            is_small_light, reason = _is_small_light_or_indicator(roi_gray, roi_hsv, det_type=det_type)
            if is_small_light:
                return FalseAlarmDecision(suppressed=True, reason=reason, category="small_light")

            # Check specular floor / metallic reflections
            is_spec_refl, reason = _is_specular_surface_reflection(roi_gray, roi_hsv, det_type=det_type)
            if is_spec_refl:
                return FalseAlarmDecision(suppressed=True, reason=reason, category="specular_reflection")

        # Check fog / cloud
        is_fog, reason = _is_fog_or_cloud(roi_gray, roi_hsv)
        if is_fog:
            return FalseAlarmDecision(suppressed=True, reason=reason, category="fog")

        # Check dust / steam
        is_dust, reason = _is_dust_or_steam(roi_gray, roi_hsv)
        if is_dust:
            return FalseAlarmDecision(suppressed=True, reason=reason, category="dust_steam")

        # Check LED reflection
        is_led, reason = _is_led_reflection(roi_gray, roi_hsv)
        if is_led:
            return FalseAlarmDecision(suppressed=True, reason=reason, category="led")

        return FalseAlarmDecision(suppressed=False)


SUPPRESSION_RULES = [
    ("fog", _is_fog_or_cloud),
    ("reflection", _is_sunlight_reflection),
    ("led", _is_led_reflection),
    ("dust_steam", _is_dust_or_steam),
    ("small_light", _is_small_light_or_indicator),
    ("specular_reflection", _is_specular_surface_reflection),
]


def suppress_false_alarms(
    frame: np.ndarray,
    detections: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[SuppressionResult]]:
    h_img, w_img = frame.shape[:2]
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    kept: List[Dict[str, Any]] = []
    suppressions: List[SuppressionResult] = []

    for det in detections:
        bb = det["bbox"]
        x1 = max(0, min(bb["x1"], w_img - 1))
        y1 = max(0, min(bb["y1"], h_img - 1))
        x2 = max(0, min(bb["x2"], w_img))
        y2 = max(0, min(bb["y2"], h_img))
        if x2 <= x1 or y2 <= y1:
            continue

        roi_gray = gray_frame[y1:y2, x1:x2]
        roi_hsv = hsv_frame[y1:y2, x1:x2]

        suppressed = False
        for category, rule_fn in SUPPRESSION_RULES:
            try:
                if category == "exhaust":
                    is_fp, reason = _is_vehicle_exhaust(roi_gray, roi_hsv, bb)
                else:
                    is_fp, reason = rule_fn(roi_gray, roi_hsv)
            except Exception:
                continue

            if is_fp:
                suppressions.append(SuppressionResult(
                    suppressed=True, reason=reason, category=category,
                ))
                logger.info(
                    "false_alarm_suppressed type=%s category=%s reason=%s conf=%.3f",
                    det["detection_type"], category, reason, det["confidence"],
                )
                suppressed = True
                break

        if not suppressed:
            kept.append(det)

    return kept, suppressions
