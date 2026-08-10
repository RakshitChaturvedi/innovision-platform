"""
JPEG Encoder — thin wrapper around OpenCV ``imencode`` for
consistent quality settings across the pipeline.
"""

from __future__ import annotations

import cv2
import numpy as np


def encode(frame: np.ndarray, quality: int = 85) -> bytes:
    """
    JPEG-encode a BGR frame at the given quality level.

    Returns raw JPEG bytes (~150 KB for 1080p at quality 85).
    """
    params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buf = cv2.imencode(".jpg", frame, params)
    if not success:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()
