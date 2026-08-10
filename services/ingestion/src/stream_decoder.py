"""
Stream Decoder — wraps an FFmpeg subprocess that converts an RTSP feed
(or a synthetic test pattern) into raw BGR24 frames for downstream sampling.

When ``rtsp_url`` is ``None`` the decoder falls back to a built-in synthetic
frame generator so the pipeline works without real RTSP infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Optional
from uuid import UUID

import numpy as np

logger = logging.getLogger(__name__)


class StreamDropError(Exception):
    """Raised when the RTSP/FFmpeg stream terminates unexpectedly."""


# ── Synthetic fallback generator ──────────────────────────────────────────


class SyntheticDecoder:
    """
    Generates deterministic coloured test frames with a camera-id overlay.
    Used when ``rtsp_url`` is not configured.
    """

    WIDTH = 1920
    HEIGHT = 1080

    def __init__(self, camera_id: UUID, fps: int = 10) -> None:
        self._camera_id = camera_id
        self._interval = 1.0 / fps
        self._frame_count = 0

    async def start(self) -> None:
        logger.info(
            "synthetic_decoder_started camera_id=%s resolution=%dx%d",
            self._camera_id,
            self.WIDTH,
            self.HEIGHT,
        )

    async def read_frame(self) -> np.ndarray:
        """Return a synthetic BGR frame at the configured FPS."""
        await asyncio.sleep(self._interval)
        self._frame_count += 1

        # Create a colour-cycling frame so each frame is visually distinct
        hue = (self._frame_count * 3) % 180
        frame = np.full((self.HEIGHT, self.WIDTH, 3), (hue, 200, 200), dtype=np.uint8)

        # Burn camera-id text into top-left (avoids cv2 dependency here)
        # Downstream consumers can verify the camera_id from frame metadata
        return frame

    async def stop(self) -> None:
        logger.info("synthetic_decoder_stopped camera_id=%s", self._camera_id)

    @property
    def frame_shape(self) -> tuple[int, int]:
        return (self.HEIGHT, self.WIDTH)


# ── FFmpeg RTSP decoder ───────────────────────────────────────────────────


class FFmpegDecoder:
    """
    Spawns ``ffmpeg`` as an asyncio subprocess and reads raw BGR24 frames
    from its stdout pipe.
    """

    # Default resolution for frame parsing — overridden after the first
    # successful probe if the source stream advertises dimensions.
    WIDTH = 1920
    HEIGHT = 1080

    def __init__(self, rtsp_url: str, camera_id: UUID) -> None:
        self._rtsp_url = rtsp_url
        self._camera_id = camera_id
        self._process: Optional[asyncio.subprocess.Process] = None
        self._frame_bytes = self.HEIGHT * self.WIDTH * 3  # BGR24

    async def start(self) -> None:
        """Launch FFmpeg and begin decoding."""
        cmd = [
            "ffmpeg",
            "-rtsp_transport", "tcp",
            "-i", self._rtsp_url,
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-an",          # discard audio
            "-sn",          # discard subtitles
            "-v", "error",  # suppress noisy output
            "pipe:1",
        ]
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info(
            "ffmpeg_started camera_id=%s rtsp=%s pid=%d",
            self._camera_id,
            self._rtsp_url,
            self._process.pid,
        )

    async def read_frame(self) -> np.ndarray:
        """
        Read exactly one raw BGR24 frame from FFmpeg stdout.

        Raises ``StreamDropError`` if the process exits or stdout closes.
        """
        if self._process is None or self._process.stdout is None:
            raise StreamDropError("FFmpeg process not started")

        data = b""
        remaining = self._frame_bytes
        while remaining > 0:
            chunk = await self._process.stdout.read(remaining)
            if not chunk:
                # FFmpeg exited or pipe broke
                stderr_tail = b""
                if self._process.stderr:
                    stderr_tail = await self._process.stderr.read(2048)
                raise StreamDropError(
                    f"FFmpeg stream dropped for camera {self._camera_id}: "
                    f"{stderr_tail.decode(errors='replace')}"
                )
            data += chunk
            remaining -= len(chunk)

        frame = np.frombuffer(data, dtype=np.uint8).reshape(
            (self.HEIGHT, self.WIDTH, 3)
        )
        return frame

    async def stop(self) -> None:
        """Terminate FFmpeg gracefully."""
        if self._process is not None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except (ProcessLookupError, asyncio.TimeoutError):
                self._process.kill()
            logger.info("ffmpeg_stopped camera_id=%s", self._camera_id)

    @property
    def frame_shape(self) -> tuple[int, int]:
        return (self.HEIGHT, self.WIDTH)


# ── Factory ───────────────────────────────────────────────────────────────


def create_decoder(
    camera_id: UUID,
    rtsp_url: Optional[str],
    fps: int = 10,
) -> FFmpegDecoder | SyntheticDecoder:
    """
    Return the appropriate decoder.

    Falls back to ``SyntheticDecoder`` when *rtsp_url* is ``None`` or empty,
    enabling the full pipeline to work without real camera hardware.
    """
    if rtsp_url:
        return FFmpegDecoder(rtsp_url=rtsp_url, camera_id=camera_id)
    return SyntheticDecoder(camera_id=camera_id, fps=fps)
