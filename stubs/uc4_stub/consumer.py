"""
consumer.py — Redis XREADGROUP consumer for UC4 analytics.

Discovers assigned cameras via Camera Registry, creates consumer groups on
each camera's frame stream, and dispatches decoded frames through the
CV engine pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from shared.contracts.frame_event import FrameEvent

logger = logging.getLogger("uc4.consumer")

# ── Configuration ─────────────────────────────────────────────────

CAMERA_REGISTRY_URL = os.getenv(
    "CAMERA_REGISTRY_URL",
    "http://camera_registry:8011",
)

UC_ID = "uc4"

CONSUMER_GROUP = os.getenv("REDIS_CONSUMER_GROUP", "uc4_group")
CONSUMER_NAME = os.getenv("REDIS_CONSUMER_NAME", "uc4_worker_1")


# ── Camera Discovery (FIX #5) ────────────────────────────────────

async def discover_cameras(client: httpx.AsyncClient) -> list[str]:
    """
    Call GET /cameras/byuc/uc4 on Camera Registry.
    Falls back to GET /cameras (active list) if byuc returns nothing.
    """
    try:
        response = await client.get(
            f"{CAMERA_REGISTRY_URL}/cameras/by-uc/{UC_ID}"
        )
        response.raise_for_status()
        payload = response.json()
        camera_ids = payload.get("camera_ids", [])
        if camera_ids:
            logger.info(
                "camera_discovery_byuc uc=%s cameras=%s",
                UC_ID,
                camera_ids,
            )
            return camera_ids
    except Exception as exc:
        logger.warning(
            "camera_discovery_byuc_failed uc=%s error=%s",
            UC_ID,
            exc,
        )

    # Fallback: GET /cameras (active list)
    logger.info("camera_discovery_fallback_to_active_list")
    try:
        response = await client.get(f"{CAMERA_REGISTRY_URL}/cameras")
        response.raise_for_status()
        cameras = response.json()
        if isinstance(cameras, list):
            return [str(cam.get("id", "")) for cam in cameras if cam.get("id")]
        return []
    except Exception as exc:
        logger.error("camera_discovery_fallback_failed error=%s", exc)
        return []


async def load_camera_assignments() -> dict[str, str]:
    """
    Returns {camera_id: stream_name} mapping.
    Retries until at least one camera is discovered.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        camera_ids = await discover_cameras(client)

    camera_streams = {
        cam_id: f"frames:{cam_id}"
        for cam_id in camera_ids
        if cam_id
    }

    if not camera_streams:
        logger.warning("no_cameras_assigned_to_uc uc=%s", UC_ID)

    return camera_streams


# ── Consumer Group Setup ──────────────────────────────────────────

async def ensure_consumer_groups(
    redis_client: aioredis.Redis,
    camera_streams: dict[str, str],
) -> None:
    """Create uc4_group on each frames:{camera_id} stream with MKSTREAM."""
    for camera_id, stream in camera_streams.items():
        try:
            await redis_client.xgroup_create(
                name=stream,
                groupname=CONSUMER_GROUP,
                id="0",
                mkstream=True,
            )
            logger.info(
                "consumer_group_created stream=%s group=%s",
                stream,
                CONSUMER_GROUP,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise


# ── Message Consumer Loop ────────────────────────────────────────

async def consume_loop(
    redis_client: aioredis.Redis,
    process_frame_callback,
    metrics: dict,
) -> None:
    """
    Main consumer loop: discovers cameras, ensures consumer groups,
    reads frame events via XREADGROUP, and dispatches to the processing callback.

    XACK is only sent AFTER the frame has been fully processed.
    """
    # Discover cameras with retry
    camera_streams: dict[str, str] = {}
    while not camera_streams:
        try:
            camera_streams = await load_camera_assignments()
        except Exception:
            logger.exception("camera_registry_discovery_failed")

        if not camera_streams:
            logger.warning("UC4 has no assigned cameras; retrying in 5s")
            await asyncio.sleep(5)

    await ensure_consumer_groups(redis_client, camera_streams)

    logger.info(
        "uc4_consumer_started streams=%s group=%s consumer=%s",
        list(camera_streams.values()),
        CONSUMER_GROUP,
        CONSUMER_NAME,
    )

    while True:
        try:
            streams = {
                stream: ">"
                for stream in camera_streams.values()
            }

            messages = await redis_client.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=CONSUMER_NAME,
                streams=streams,
                count=10,
                block=2000,
            )

            if not messages:
                continue

            for stream_name, entries in messages:
                if isinstance(stream_name, bytes):
                    stream_name = stream_name.decode()

                for message_id, fields in entries:
                    if isinstance(message_id, bytes):
                        message_id = message_id.decode()

                    # Decode bytes fields
                    decoded_fields = {
                        (key.decode() if isinstance(key, bytes) else key): (
                            value.decode() if isinstance(value, bytes) else value
                        )
                        for key, value in fields.items()
                    }

                    try:
                        payload = decoded_fields.get("data")
                        if not payload:
                            logger.warning(
                                "empty_frame_event stream=%s message_id=%s",
                                stream_name,
                                message_id,
                            )
                            # ACK empty messages to avoid re-processing
                            await redis_client.xack(
                                stream_name, CONSUMER_GROUP, message_id
                            )
                            continue

                        # Parse into FrameEvent pydantic model (import only, no edit)
                        frame_event = FrameEvent.model_validate_json(payload)
                        metrics["frames_consumed"] += 1

                        # Process the frame (decode + CV engine) — this must
                        # complete before we ACK
                        await process_frame_callback(frame_event)

                        # ACK only after full processing
                        await redis_client.xack(
                            stream_name, CONSUMER_GROUP, message_id
                        )

                    except Exception:
                        logger.exception(
                            "frame_processing_failed stream=%s message_id=%s",
                            stream_name,
                            message_id,
                        )

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("uc4_consumer_loop_error")
            await asyncio.sleep(2)
