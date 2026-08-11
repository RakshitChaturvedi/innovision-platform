"""
JPEG Encoder — thin wrapper around OpenCV ``imencode`` for
consistent quality settings across the pipeline.
"""

from __future__ import annotations

import cv2
import numpy as np

class JpegEncoder:
    def __init__(self, quality: int = 85) -> None:
        if not 1 <= quality <= 100:
            raise ValueError("JPEG quality must be between 1 and 100")
        self._quality = quality

    def encode(self, frame: np.ndarray) -> bytes:
        """
        JPEG-encode a BGR frame at the given quality level.

        Returns raw JPEG bytes (~150 KB for 1080p at quality 85).
        """
        if frame is None or frame.size == 0:
            raise ValueError("Cant encode empty frame")
        success, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, self._quality])
        if not success:
            raise RuntimeError("JPEG encoding failed")
        return buf.tobytes()

    def object_key(self, camera_id: str, frame_seq: int) -> str:
        # generate minio obj key for frame
        return (f"frames/{camera_id}/{frame_seq:08d}.jpg")
