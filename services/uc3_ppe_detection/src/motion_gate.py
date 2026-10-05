"""
UC3 Motion Gate — Background subtraction motion filter for frame evaluation.
"""

from __future__ import annotations

import logging
from typing import Tuple

import cv2
import numpy as np

from services.uc3_ppe_detection.src import config

logger = logging.getLogger(__name__)


class MotionState:
    def __init__(self) -> None:
        self.prev_gray: np.ndarray | None = None
        self.warmup_count: int = 0

    def check_motion(self, frame_bgr: np.ndarray) -> bool:
        if not config.MOTION_GATE_ENABLED:
            return True

        h, w = frame_bgr.shape[:2]
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self.prev_gray is None or self.prev_gray.shape != gray.shape:
            self.prev_gray = gray
            self.warmup_count = 1
            return True

        if self.warmup_count < 5:
            self.warmup_count += 1
            self.prev_gray = gray
            return True

        diff = cv2.absdiff(gray, self.prev_gray)
        _, thresh = cv2.threshold(diff, config.MOTION_DIFF_THRESHOLD, 255, cv2.THRESH_BINARY)
        motion_px = np.count_nonzero(thresh)
        motion_ratio = motion_px / float(h * w)

        self.prev_gray = gray
        return motion_ratio >= config.MOTION_GLOBAL_MIN_FRACTION
