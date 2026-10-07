"""
Motion detection gate — ported natively for Innovision UC3.
Runs background subtraction / consecutive frame diffing to filter static candidates.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

import services.uc3.src.ppe_config as config

log = logging.getLogger("uc3_motion_gate")

Box = tuple[float, float, float, float]

def _iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0

@dataclass
class _TrackedRegion:
    box: Box
    still_since: float
    last_seen: float
    last_reverified_at: float

@dataclass
class MotionState:
    prev_gray: np.ndarray | None = None
    bg_subtractor: Any | None = None
    frames_seen: int = 0
    last_motion_at: float = float("-inf")
    last_forced_run_at: float = float("-inf")
    static_regions: list[_TrackedRegion] = field(default_factory=list)
    cached_mask: np.ndarray | None = None

def new_motion_state() -> MotionState:
    return MotionState()

def compute_motion_mask(frame: np.ndarray, state: MotionState) -> np.ndarray | None:
    if not config.MOTION_GATE_ENABLED:
        return None

    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if state.prev_gray is None or state.prev_gray.shape != gray.shape:
            state.prev_gray = gray
            return None

        method = config.MOTION_GATE_METHOD
        if method in ("mog2", "knn"):
            if state.bg_subtractor is None:
                if method == "mog2":
                    state.bg_subtractor = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=16, detectShadows=False)
                else:
                    state.bg_subtractor = cv2.createBackgroundSubtractorKNN(history=500, dist2Threshold=400, detectShadows=False)
            mask = state.bg_subtractor.apply(frame)
        else:
            diff = cv2.absdiff(state.prev_gray, gray)
            _, mask = cv2.threshold(diff, config.MOTION_GATE_DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
            state.prev_gray = gray

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        mask = cv2.dilate(mask, kernel, iterations=2)
        state.cached_mask = mask
        return mask
    except Exception:
        log.exception("motion_gate_mask_failed — failing open")
        return None

def should_run_inference(
    frame: np.ndarray,
    candidate_boxes: list[Box] | None,
    state: MotionState,
    now: float,
) -> bool:
    if not config.MOTION_GATE_ENABLED:
        return True

    state.frames_seen += 1
    if state.frames_seen <= 1:
        return True

    if (now - state.last_forced_run_at) >= config.MOTION_GATE_FORCE_INTERVAL_SECONDS:
        state.last_forced_run_at = now
        return True

    mask = state.cached_mask if state.cached_mask is not None else compute_motion_mask(frame, state)
    if mask is None:
        return True

    if candidate_boxes is not None and len(candidate_boxes) > 0:
        h, w = frame.shape[:2]
        for b in candidate_boxes:
            x1 = max(0, int(b[0]))
            y1 = max(0, int(b[1]))
            x2 = min(w, int(b[2]))
            y2 = min(h, int(b[3]))
            if x2 > x1 and y2 > y1:
                crop = mask[y1:y2, x1:x2]
                if cv2.countNonZero(crop) >= config.MOTION_GATE_MIN_PERSON_MOTION_PIXELS:
                    state.last_motion_at = now
                    return True
        return False

    changed_pixels = cv2.countNonZero(mask)
    if changed_pixels >= config.MOTION_GATE_MIN_CHANGED_PIXELS:
        state.last_motion_at = now
        return True

    return False
