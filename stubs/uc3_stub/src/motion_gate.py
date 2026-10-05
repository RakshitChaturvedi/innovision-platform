"""
Motion detection — stage 2 of the person->motion->PPE presence cascade.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from stubs.uc3_stub.src import config

log = logging.getLogger("uc3.motion_gate")

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
    cached_valid: bool = False
    last_pregate_forced_at: float = float("-inf")
    forced_pass: bool = False


def new_session_state() -> MotionState:
    now = time.monotonic()
    return MotionState(last_motion_at=now, last_forced_run_at=now, last_pregate_forced_at=now)


def _get_bg_subtractor():
    if getattr(config, "MOTION_GATE_METHOD", "diff") == "knn":
        return cv2.createBackgroundSubtractorKNN(
            history=getattr(config, "MOTION_MOG2_HISTORY", 500),
            detectShadows=getattr(config, "MOTION_MOG2_DETECT_SHADOWS", False),
        )
    return cv2.createBackgroundSubtractorMOG2(
        history=getattr(config, "MOTION_MOG2_HISTORY", 500),
        varThreshold=getattr(config, "MOTION_MOG2_VAR_THRESHOLD", 16.0),
        detectShadows=getattr(config, "MOTION_MOG2_DETECT_SHADOWS", False),
    )


def _compute_motion_mask(frame: np.ndarray, state: MotionState) -> np.ndarray | None:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    state.frames_seen += 1

    method = getattr(config, "MOTION_GATE_METHOD", "diff")
    if method in ("mog2", "knn"):
        if state.bg_subtractor is None:
            state.bg_subtractor = _get_bg_subtractor()
        mask = state.bg_subtractor.apply(gray)
        mask = np.where(mask == 255, 255, 0).astype(np.uint8)
        if state.frames_seen < getattr(config, "MOTION_WARMUP_FRAMES", 5):
            return None
        return mask

    if state.prev_gray is None:
        state.prev_gray = gray
        return None
    diff = cv2.absdiff(gray, state.prev_gray)
    state.prev_gray = gray
    if state.frames_seen < getattr(config, "MOTION_WARMUP_FRAMES", 5):
        return None
    _, mask = cv2.threshold(diff, getattr(config, "MOTION_DIFF_THRESHOLD", 20), 255, cv2.THRESH_BINARY)
    return mask


def _box_motion_fraction(mask: np.ndarray, box: Box) -> float:
    h, w = mask.shape[:2]
    x1, y1, x2, y2 = box
    px1, py1 = max(0, int(x1)), max(0, int(y1))
    px2, py2 = min(w, int(x2)), min(h, int(y2))
    if px2 <= px1 or py2 <= py1:
        return 0.0
    crop = mask[py1:py2, px1:px2]
    area = crop.size
    if area == 0:
        return 0.0
    return cv2.countNonZero(crop) / area


def _update_static_regions(
    state: MotionState, mask: np.ndarray, candidate_boxes: list[Box], now: float,
) -> list[Box]:
    matched_ids: set[int] = set()
    still_considered: list[Box] = []

    min_frac = getattr(config, "MOTION_MIN_FRACTION", 0.02)
    static_obj_sec = getattr(config, "MOTION_STATIC_OBJECT_SECONDS", 300.0)
    static_reverify_sec = getattr(config, "MOTION_STATIC_REVERIFY_SECONDS", 600.0)
    static_iou_thresh = getattr(config, "MOTION_STATIC_IOU_MATCH_THRESHOLD", 0.5)
    static_ttl_sec = getattr(config, "MOTION_STATIC_REGION_TTL_SECONDS", 60.0)

    for box in candidate_boxes:
        moving = _box_motion_fraction(mask, box) >= min_frac

        region = None
        best_iou = static_iou_thresh
        for candidate_region in state.static_regions:
            iou = _iou(candidate_region.box, box)
            if iou >= best_iou:
                region, best_iou = candidate_region, iou

        if region is None:
            region = _TrackedRegion(box=box, still_since=now, last_seen=now, last_reverified_at=now)
            state.static_regions.append(region)
        else:
            region.box = box
            region.last_seen = now
        matched_ids.add(id(region))

        if moving:
            region.still_since = now
            still_considered.append(box)
            continue

        confirmed_static = (now - region.still_since) >= static_obj_sec
        if not confirmed_static:
            still_considered.append(box)
            continue

        if now - region.last_reverified_at >= static_reverify_sec:
            region.last_reverified_at = now
            still_considered.append(box)

    state.static_regions = [
        r for r in state.static_regions
        if id(r) in matched_ids or (now - r.last_seen) < static_ttl_sec
    ]

    return still_considered


def frame_has_motion(state: MotionState, frame: np.ndarray) -> bool:
    now = time.monotonic()
    state.cached_valid = False
    state.forced_pass = False
    try:
        mask = _compute_motion_mask(frame, state)
        state.cached_mask, state.cached_valid = mask, True
        if mask is None:
            return True
        global_min_frac = getattr(config, "MOTION_GLOBAL_MIN_FRACTION", 0.001)
        grace_sec = getattr(config, "MOTION_GATE_GRACE_SECONDS", 5.0)
        force_interval_sec = getattr(config, "MOTION_GATE_FORCE_INTERVAL_SECONDS", 2.0)

        if cv2.countNonZero(mask) / mask.size >= global_min_frac:
            return True
        if now - state.last_motion_at <= grace_sec:
            return True
        if now - state.last_pregate_forced_at >= force_interval_sec:
            state.last_pregate_forced_at = now
            state.forced_pass = True
            return True
        return False
    except Exception:
        log.exception("motion_pregate_failed — defaulting to has_motion=True (fail open)")
        state.cached_mask, state.cached_valid = None, False
        return True


def should_run_inference(state: MotionState, frame: np.ndarray, candidate_boxes: list[Box]) -> bool:
    if not candidate_boxes:
        state.cached_valid = state.forced_pass = False
        return False

    now = time.monotonic()
    use_cached, cached = state.cached_valid, state.cached_mask
    forced = state.forced_pass
    state.cached_valid = state.forced_pass = False
    try:
        mask = cached if use_cached else _compute_motion_mask(frame, state)
        if mask is None:
            return True

        effective_boxes = _update_static_regions(state, mask, candidate_boxes, now)
        if forced and effective_boxes:
            state.last_forced_run_at = now
            return True
        if not effective_boxes:
            return False

        min_frac = getattr(config, "MOTION_MIN_FRACTION", 0.02)
        grace_sec = getattr(config, "MOTION_GATE_GRACE_SECONDS", 5.0)
        force_interval_sec = getattr(config, "MOTION_GATE_FORCE_INTERVAL_SECONDS", 2.0)

        any_moving = any(
            _box_motion_fraction(mask, box) >= min_frac for box in effective_boxes
        )
        if any_moving:
            state.last_motion_at = now
            state.last_forced_run_at = now
            return True

        if now - state.last_motion_at <= grace_sec:
            return True

        if now - state.last_forced_run_at >= force_interval_sec:
            state.last_forced_run_at = now
            return True

        return False
    except Exception:
        log.exception("motion_gate_failed — defaulting to should_run_inference=True (fail open)")
        return True
