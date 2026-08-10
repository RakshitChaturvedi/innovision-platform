"""
Frame Sampler — rate-gates decoded frames to the target FPS and
maintains a monotonically increasing ``frame_seq`` counter.
"""

from __future__ import annotations

import time
import logging

logger = logging.getLogger(__name__)


class FrameSampler:
    """
    Decides whether a decoded frame should be forwarded downstream.

    Call :meth:`should_sample` after every decoded frame; it returns
    ``True`` only when enough wall-clock time has elapsed for the next
    sample.  The internal ``frame_seq`` counter starts at **1** and
    increments on every accepted sample.
    """

    def __init__(self, target_fps: int = 10) -> None:
        self._interval = 1.0 / max(target_fps, 1)
        self._last_sample_time: float = 0.0
        self._frame_seq: int = 0

    def should_sample(self) -> bool:
        """Return ``True`` if enough time has passed for the next sample."""
        now = time.monotonic()
        if now - self._last_sample_time >= self._interval:
            self._last_sample_time = now
            self._frame_seq += 1
            return True
        return False

    @property
    def frame_seq(self) -> int:
        """Current frame sequence number (1-indexed)."""
        return self._frame_seq

    def reset(self) -> None:
        """Reset sampler state (e.g. after a reconnect)."""
        self._last_sample_time = 0.0
        # NOTE: frame_seq intentionally NOT reset — sequences are monotonic
        #       across reconnects to avoid duplicate keys in MinIO.
        logger.info("frame_sampler_reset next_seq=%d", self._frame_seq + 1)
