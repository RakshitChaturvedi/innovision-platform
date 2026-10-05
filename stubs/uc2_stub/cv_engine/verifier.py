"""
Stage 2 & 3 — Deterministic HSV / Texture / Gradient Verification.

Each verifier returns a probability score [0.0, 1.0], NOT a boolean.
Scores feed into Stage 5/6 confidence fusion.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

import cv2
import numpy as np

from stubs.uc2_stub.cv_engine.config import settings

logger = logging.getLogger("innovision.uc2.detection.verifier")


@dataclass
class VerificationResult:
    """Per-detection verification output."""
    passed: bool = False
    rejection_reason: str = ""
    hsv_score: float = 0.0
    texture_score: float = 0.0
    combined_score: float = 0.0
    motion_score: float = 0.5
    entropy: float = 0.0
    laplacian_var: float = 0.0
    scores: Dict[str, Any] = field(default_factory=dict)


class DeterministicVerifier:
    """
    Stage 2 & 3: Deterministic fire/smoke verification using colour,
    texture, gradient, entropy, and blur analysis.
    Returns probability scores instead of hard booleans for downstream fusion.
    """

    def __init__(self) -> None:
        self._fire_cfg = settings.fire_hsv
        self._smoke_cfg = settings.smoke_hsv

    # ── Fire HSV Verification ─────────────────────────────────────────────────

    def verify_fire(self, roi_bgr: np.ndarray) -> VerificationResult:
        if roi_bgr.size == 0 or roi_bgr.shape[0] < 4 or roi_bgr.shape[1] < 4:
            return VerificationResult(passed=False, rejection_reason="empty_roi")

        roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        total_px = roi_hsv.shape[0] * roi_hsv.shape[1]
        cfg = self._fire_cfg

        # Multi-range fire colour masking
        fire_mask = np.zeros(roi_hsv.shape[:2], dtype=np.uint8)
        for lower, upper in cfg.hsv_ranges:
            m = cv2.inRange(roi_hsv, np.array(lower), np.array(upper))
            fire_mask = cv2.bitwise_or(fire_mask, m)

        # Morphological noise removal
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_OPEN, kernel)
        fire_mask = cv2.morphologyEx(fire_mask, cv2.MORPH_CLOSE, kernel)

        # Connected components
        num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(fire_mask)
        valid_px = sum(
            stats[i, cv2.CC_STAT_AREA]
            for i in range(1, num_labels)
            if stats[i, cv2.CC_STAT_AREA] >= cfg.min_component_size
        )

        flame_ratio = valid_px / total_px if total_px > 0 else 0.0

        if valid_px > 0:
            active = roi_hsv[fire_mask > 0]
            avg_sat = float(np.mean(active[:, 1]))
            avg_val = float(np.mean(active[:, 2]))
        else:
            avg_sat, avg_val = 0.0, 0.0

        scores = {
            "flame_color_ratio": round(flame_ratio, 4),
            "avg_brightness": round(avg_val, 2),
            "avg_saturation": round(avg_sat, 2),
            "components_count": max(0, num_labels - 1),
        }

        # Probability-based HSV score (0.0 – 1.0)
        colour_prob = min(1.0, flame_ratio / max(cfg.min_pixel_ratio * 3, 0.01))
        bright_prob = min(1.0, avg_val / 255.0)
        sat_prob = min(1.0, avg_sat / 255.0)
        hsv_score = round(0.5 * colour_prob + 0.25 * bright_prob + 0.25 * sat_prob, 4)
        combined_score = hsv_score

        passed = flame_ratio >= cfg.min_pixel_ratio and avg_val >= cfg.min_brightness

        return VerificationResult(
            passed=passed,
            hsv_score=hsv_score,
            texture_score=0.5,
            combined_score=combined_score,
            scores=scores,
        )

    # ── Smoke HSV / Texture Verification ──────────────────────────────────────

    def verify_smoke(self, roi_bgr: np.ndarray) -> VerificationResult:
        if roi_bgr.size == 0 or roi_bgr.shape[0] < 4 or roi_bgr.shape[1] < 4:
            return VerificationResult(passed=False, rejection_reason="empty_roi")

        roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        cfg = self._smoke_cfg

        avg_sat = float(np.mean(roi_hsv[:, :, 1]))
        avg_val = float(np.mean(roi_hsv[:, :, 2]))

        b, g, r = cv2.split(roi_bgr)
        chroma_diff = cv2.absdiff(cv2.max(cv2.max(b, g), r), cv2.min(cv2.min(b, g), r))
        avg_chroma = float(np.mean(chroma_diff))

        texture_std = float(np.std(roi_gray))

        edges = cv2.Canny(roi_gray, 50, 150)
        total_px = roi_gray.size
        edge_density = float(np.count_nonzero(edges) / total_px) if total_px > 0 else 0.0

        hist = cv2.calcHist([roi_gray], [0], None, [256], [0, 256])
        hist = hist.ravel() / (hist.sum() + 1e-7)
        entropy = float(-np.sum(hist * np.log2(hist + 1e-7)))

        laplacian_var = float(cv2.Laplacian(roi_gray, cv2.CV_64F).var())

        sobelx = cv2.Sobel(roi_gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(roi_gray, cv2.CV_64F, 0, 1, ksize=3)
        avg_grad = float(np.mean(cv2.magnitude(sobelx, sobely)))

        scores = {
            "avg_saturation": round(avg_sat, 2),
            "avg_brightness": round(avg_val, 2),
            "avg_chroma": round(avg_chroma, 2),
            "texture_std": round(texture_std, 2),
            "edge_density": round(edge_density, 4),
            "entropy": round(entropy, 2),
            "laplacian_var": round(laplacian_var, 2),
            "avg_gradient_mag": round(avg_grad, 2),
        }

        # Texture probability score
        desat_score = max(0.0, 1.0 - (avg_sat / max(cfg.max_saturation, 1)))
        blur_score = max(0.0, 1.0 - (laplacian_var / max(cfg.max_laplacian_var, 1)))
        texture_score = round(0.4 * desat_score + 0.3 * blur_score + 0.3 * min(1.0, entropy / 7.0), 4)
        hsv_score = round(desat_score, 4)
        combined_score = round(0.5 * hsv_score + 0.5 * texture_score, 4)

        return VerificationResult(
            passed=True,
            hsv_score=hsv_score,
            texture_score=texture_score,
            combined_score=combined_score,
            entropy=round(entropy, 2),
            laplacian_var=round(laplacian_var, 2),
            scores=scores,
        )

    # ── Sparks HSV / Spatial Verification ─────────────────────────────────────

    def verify_sparks(self, roi_bgr: np.ndarray) -> VerificationResult:
        if roi_bgr.size == 0 or roi_bgr.shape[0] < 4 or roi_bgr.shape[1] < 4:
            return VerificationResult(passed=False, rejection_reason="empty_roi")

        roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        roi_gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
        v_channel = roi_hsv[:, :, 2]
        max_val = float(np.max(v_channel))
        avg_val = float(np.mean(v_channel))
        std_val = float(np.std(roi_gray))
        total_px = roi_bgr.shape[0] * roi_bgr.shape[1]

        # Reject smooth daylight sky, clouds, and uniform walls
        if avg_val > 150.0 and std_val < 18.0:
            return VerificationResult(
                passed=False,
                rejection_reason=f"uniform_daylight_or_sky (avg={avg_val:.1f}, std={std_val:.1f})",
                scores={"avg_brightness": avg_val, "std": std_val},
            )

        # Spark particles mask (high brightness and distinct contrast)
        spark_mask = cv2.inRange(roi_hsv, np.array([0, 20, 200]), np.array([180, 255, 255]))
        spark_pixels = int(np.count_nonzero(spark_mask))
        spark_ratio = spark_pixels / float(total_px) if total_px > 0 else 0.0

        scores = {
            "max_brightness": round(max_val, 1),
            "avg_brightness": round(avg_val, 1),
            "std_brightness": round(std_val, 1),
            "spark_pixels": spark_pixels,
            "spark_ratio": round(spark_ratio, 4),
        }

        # Sparks should have intense local brightness
        if max_val < 185.0:
            return VerificationResult(
                passed=False,
                rejection_reason=f"low_spark_intensity (max_val={max_val:.1f} < 185)",
                scores=scores,
            )

        # If it's a solid uniform field of high brightness (like sun, floodlight bulb, or bright sky patch)
        if spark_ratio > 0.70 and std_val < 25.0:
            return VerificationResult(
                passed=False,
                rejection_reason=f"broad_light_field (spark_ratio={spark_ratio:.2f})",
                scores=scores,
            )

        # Reject diffuse smoke cloud or overcast daylight patch misclassified as sparks
        if spark_pixels > 0:
            active_spark_hsv = roi_hsv[spark_mask > 0]
            avg_spark_sat = float(np.mean(active_spark_hsv[:, 1]))
            # If bright pixels are desaturated (gray/white smoke or cloud)
            if avg_spark_sat < 55.0 and total_px > 10000:
                return VerificationResult(
                    passed=False,
                    rejection_reason=f"desaturated_smoke_or_cloud (avg_sat={avg_spark_sat:.1f})",
                    scores=scores,
                )

        # Check for static floodlight bulb / large uniform lamp fixture
        num_labels, _labels, stats, _centroids = cv2.connectedComponentsWithStats(spark_mask)
        if num_labels > 1:
            max_component_area = max(stats[1:, cv2.CC_STAT_AREA]) if len(stats) > 1 else 0
            # If a single solid connected component covers > 80% of ROI and has large area, it's a static lamp fixture
            if max_component_area > 2000 and (max_component_area / float(total_px)) > 0.80 and std_val < 30.0:
                return VerificationResult(
                    passed=False,
                    rejection_reason=f"static_floodlight_bulb (comp_area={max_component_area}, ratio={max_component_area/total_px:.2f})",
                    scores=scores,
                )

        spark_score = round(min(1.0, 0.40 + (std_val / 64.0) * 0.35 + (max_val / 255.0) * 0.25), 4)
        return VerificationResult(
            passed=True,
            hsv_score=spark_score,
            texture_score=spark_score,
            combined_score=spark_score,
            scores=scores,
        )

    # ── Dispatcher supporting both arg orders ─────────────────────────────────

    def verify(
        self,
        arg1: Union[np.ndarray, str],
        arg2: Union[np.ndarray, str],
    ) -> VerificationResult:
        """
        Supports both verify(roi_bgr, detection_type) and verify(detection_type, roi_bgr).
        """
        if isinstance(arg1, np.ndarray):
            roi_bgr, det_type = arg1, str(arg2)
        else:
            det_type, roi_bgr = str(arg1), arg2

        if det_type == "fire":
            return self.verify_fire(roi_bgr)
        elif det_type == "smoke":
            return self.verify_smoke(roi_bgr)
        elif det_type in ("sparks", "spark"):
            return self.verify_sparks(roi_bgr)
        return VerificationResult(passed=True, hsv_score=0.5, texture_score=0.5, combined_score=0.5)


# Alias for compatibility
Verifier = DeterministicVerifier
