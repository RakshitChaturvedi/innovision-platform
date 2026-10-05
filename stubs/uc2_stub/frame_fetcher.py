"""
frame_fetcher.py — Dual-tier frame resolver for UC2 analytics.

FIX #2: Redis-first, MinIO-fallback frame resolution.
"""

from __future__ import annotations

import logging
import os

import cv2
import numpy as np
import redis.asyncio as aioredis
from minio import Minio

from shared.contracts.frame_event import FrameEvent

logger = logging.getLogger("uc2.frame_fetcher")

# ── MinIO Configuration ───────────────────────────────────────────

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "changeme")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET = "innovision-frames"


def _get_minio_client() -> Minio:
    return Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=MINIO_SECURE,
    )


async def fetch_frame(
    redis_client: aioredis.Redis,
    frame_event: FrameEvent,
) -> np.ndarray | None:
    """
    Dual-tier frame fetch:
    1. Try Redis GET on key `frame:{camera_id}:{frame_seq}` (hot path).
    2. If empty/expired, fall back to MinIO bucket `innovision-frames`,
       key `frames/{camera_id}/{frame_seq:08d}.jpg`.
    3. Decode with cv2.imdecode.
    4. Log a warning if decoded shape doesn't roughly match FrameEvent.frame_shape.
    """
    camera_id = str(frame_event.camera_id)
    frame_seq = frame_event.frame_seq

    jpeg_bytes: bytes | None = None
    source = "unknown"

    # ── Tier 1: Redis hot cache ───────────────────────────────────
    redis_key = f"frame:{camera_id}:{frame_seq}"
    try:
        jpeg_bytes = await redis_client.get(redis_key)
        if jpeg_bytes:
            source = "redis"
    except Exception as exc:
        logger.warning("redis_frame_fetch_error key=%s error=%s", redis_key, exc)

    # ── Tier 2: MinIO fallback ────────────────────────────────────
    if not jpeg_bytes:
        minio_key = f"frames/{camera_id}/{frame_seq:08d}.jpg"
        try:
            client = _get_minio_client()
            response = client.get_object(MINIO_BUCKET, minio_key)
            jpeg_bytes = response.read()
            response.close()
            response.release_conn()
            source = "minio"
            logger.debug("minio_frame_fetched key=%s", minio_key)
        except Exception as exc:
            logger.warning(
                "frame_fetch_failed camera_id=%s frame_seq=%d redis_key=%s minio_key=%s error=%s",
                camera_id,
                frame_seq,
                redis_key,
                minio_key,
                exc,
            )
            return None

    if not jpeg_bytes:
        logger.warning(
            "frame_not_found camera_id=%s frame_seq=%d",
            camera_id,
            frame_seq,
        )
        return None

    # ── Decode JPEG ───────────────────────────────────────────────
    frame = cv2.imdecode(
        np.frombuffer(jpeg_bytes, np.uint8),
        cv2.IMREAD_COLOR,
    )

    if frame is None:
        logger.warning(
            "frame_decode_failed camera_id=%s frame_seq=%d source=%s",
            camera_id,
            frame_seq,
            source,
        )
        return None

    # ── Shape validation ──────────────────────────────────────────
    actual_h, actual_w = frame.shape[:2]
    expected_h, expected_w = frame_event.frame_shape

    # "roughly match" — allow up to 20% deviation
    if expected_h > 0 and expected_w > 0:
        h_ratio = abs(actual_h - expected_h) / max(expected_h, 1)
        w_ratio = abs(actual_w - expected_w) / max(expected_w, 1)
        if h_ratio > 0.2 or w_ratio > 0.2:
            logger.warning(
                "frame_shape_mismatch camera_id=%s frame_seq=%d "
                "expected=(%d,%d) actual=(%d,%d) source=%s",
                camera_id,
                frame_seq,
                expected_h,
                expected_w,
                actual_h,
                actual_w,
                source,
            )

    logger.debug(
        "frame_fetched camera_id=%s frame_seq=%d shape=(%d,%d) source=%s",
        camera_id,
        frame_seq,
        actual_h,
        actual_w,
        source,
    )

    return frame
