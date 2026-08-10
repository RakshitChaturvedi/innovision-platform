"""
Shake Detector — uses ORB keypoint matching and homography estimation
to detect camera shake across a sliding window of sampled frames.

When shake is detected the module publishes a signal to the Redis
Pub/Sub channel ``camera:shake:{camera_id}``.
"""

from __future__ import annotations

import logging
from collections import deque
from uuid import UUID

import cv2
import numpy as np
import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


class ShakeDetector:
    """
    Maintains a sliding window of grayscale frames and computes
    inter-frame homography variance to detect camera shake.
    """

    def __init__(
        self,
        camera_id: UUID,
        redis_client: aioredis.Redis,
        window_size: int = 5,
        variance_threshold: float = 50.0,
    ) -> None:
        self._camera_id = camera_id
        self._redis = redis_client
        self._window_size = window_size
        self._variance_threshold = variance_threshold
        self._channel = f"camera:shake:{camera_id}"

        # ORB detector for keypoint extraction
        self._orb = cv2.ORB_create(nfeatures=500)
        self._bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        # Sliding window of grayscale frames
        self._buffer: deque[np.ndarray] = deque(maxlen=window_size)

    async def check(self, frame: np.ndarray) -> bool:
        """
        Analyse *frame* for shake.

        Returns ``True`` if camera shake was detected (and a Pub/Sub
        signal was published), ``False`` otherwise.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self._buffer.append(gray)

        if len(self._buffer) < 2:
            return False

        # Compute homography translations across the window
        translations: list[float] = []
        prev = self._buffer[-2]
        curr = self._buffer[-1]

        kp1, des1 = self._orb.detectAndCompute(prev, None)
        kp2, des2 = self._orb.detectAndCompute(curr, None)

        if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
            return False

        matches = self._bf.match(des1, des2)
        if len(matches) < 4:
            return False

        src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if H is None:
            return False

        # Translation components from the homography matrix
        tx, ty = H[0, 2], H[1, 2]
        translations.append(tx ** 2 + ty ** 2)

        variance = float(np.var(translations)) if len(translations) > 1 else float(translations[0])

        if variance > self._variance_threshold:
            await self._publish_shake(variance)
            return True
        return False

    async def _publish_shake(self, variance: float) -> None:
        """Publish a shake detection signal to Redis Pub/Sub."""
        import json
        from datetime import datetime, timezone

        payload = json.dumps(
            {
                "camera_id": str(self._camera_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "variance": round(variance, 2),
                "event": "camera_shake_detected",
            }
        )
        await self._redis.publish(self._channel, payload)
        logger.warning(
            "camera_shake_detected camera_id=%s variance=%.2f",
            self._camera_id,
            variance,
        )
