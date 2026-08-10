"""
Ingestion Service — Main Orchestrator
=====================================

Ties together every module in ``services/ingestion/src/`` into a single
asyncio application:

1. Loads cameras from PostgreSQL on startup.
2. Spawns one ``camera_worker`` task per camera (decode → sample →
   shake-detect → JPEG-encode → upload → publish FrameEvent).
3. Runs a per-camera heartbeat co-task.
4. Handles stream drops with exponential backoff and status updates.
5. Subscribes to Redis Pub/Sub for dynamic camera config changes
   (``camera:added:*``, ``camera:updated:*``, ``camera:removed:*``).
6. Serves a ``/health`` endpoint via uvicorn on port 8020.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from uuid import UUID

import redis.asyncio as aioredis
import uvicorn

# Ensure project root is on the path (for Docker ``/app`` mount)
sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))

from services.ingestion.src.config import load_config, IngestionConfig
from services.ingestion.src.camera_loader import (
    create_db_engine,
    load_cameras,
    update_camera_status,
    get_camera_by_id,
)
from services.ingestion.src.stream_decoder import create_decoder, StreamDropError
from services.ingestion.src.frame_sampler import FrameSampler
from services.ingestion.src.shake_detector import ShakeDetector
from services.ingestion.src.jpeg_encoder import encode as jpeg_encode
from services.ingestion.src.frame_store import FrameStore
from services.ingestion.src.publisher import FramePublisher
from services.ingestion.src.heartbeat import heartbeat_loop
from services.ingestion.src.health import app as health_app, register_workers
from shared.contracts.enums import CameraStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("ingestion")

# ── Global state managed by the orchestrator ──────────────────────────────

# camera_id → asyncio.Task  (worker + heartbeat)
_workers: dict[UUID, asyncio.Task] = {}
_heartbeats: dict[UUID, asyncio.Task] = {}


# ── Camera worker ─────────────────────────────────────────────────────────


async def camera_worker(
    camera: dict,
    cfg: IngestionConfig,
    redis_client: aioredis.Redis,
    frame_store: FrameStore,
    publisher: FramePublisher,
    db_engine,
) -> None:
    """
    Pipeline loop for a single camera.  Reconnects with exponential
    backoff on stream drops.
    """
    camera_id: UUID = camera["id"]
    rtsp_url: str | None = camera.get("rtsp_url")
    fps: int = camera.get("fps", cfg.default_fps)
    backoff = cfg.backoff_base_s

    while True:
        decoder = create_decoder(camera_id, rtsp_url, fps)
        sampler = FrameSampler(target_fps=fps)
        shake = ShakeDetector(
            camera_id=camera_id,
            redis_client=redis_client,
            window_size=cfg.shake_window_size,
            variance_threshold=cfg.shake_variance_threshold,
        )
        last_frame_time = time.monotonic()

        try:
            await decoder.start()
            await update_camera_status(db_engine, camera_id, CameraStatus.ONLINE)
            backoff = cfg.backoff_base_s  # reset on successful connect
            logger.info("camera_worker_online camera_id=%s fps=%d", camera_id, fps)

            while True:
                frame = await decoder.read_frame()
                last_frame_time = time.monotonic()

                if not sampler.should_sample():
                    continue

                # Shake detection (non-blocking best-effort)
                try:
                    await shake.check(frame)
                except Exception as exc:
                    logger.debug("shake_check_error camera_id=%s: %s", camera_id, exc)

                # JPEG encode
                jpeg_bytes = jpeg_encode(frame, quality=cfg.jpeg_quality)

                # Upload to MinIO
                frame_ref = await frame_store.upload_frame(
                    camera_id=camera_id,
                    frame_seq=sampler.frame_seq,
                    jpeg_bytes=jpeg_bytes,
                )

                # Publish FrameEvent to Redis stream
                await publisher.publish(
                    camera_id=camera_id,
                    frame_seq=sampler.frame_seq,
                    frame_reference=frame_ref,
                    frame_shape=decoder.frame_shape,
                )

                logger.debug(
                    "frame_processed camera_id=%s seq=%d size=%dB",
                    camera_id, sampler.frame_seq, len(jpeg_bytes),
                )

        except StreamDropError as exc:
            logger.error("stream_drop camera_id=%s: %s", camera_id, exc)

        except asyncio.CancelledError:
            logger.info("camera_worker_cancelled camera_id=%s", camera_id)
            await decoder.stop()
            return

        except Exception as exc:
            logger.exception("camera_worker_error camera_id=%s", camera_id)

        # ── Reconnection with exponential backoff ────────────────────
        await decoder.stop()
        await update_camera_status(db_engine, camera_id, CameraStatus.RECONNECTING)
        logger.info(
            "camera_reconnecting camera_id=%s backoff=%.1fs", camera_id, backoff
        )
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, cfg.backoff_max_s)


# ── Dynamic config subscriber ────────────────────────────────────────────


async def config_subscriber(
    cfg: IngestionConfig,
    redis_client: aioredis.Redis,
    frame_store: FrameStore,
    publisher: FramePublisher,
    db_engine,
) -> None:
    """
    Listens on Redis Pub/Sub pattern channels for dynamic camera
    lifecycle events and starts/stops/reloads workers accordingly.
    """
    pubsub = redis_client.pubsub()
    await pubsub.psubscribe(
        "camera:added:*",
        "camera:updated:*",
        "camera:removed:*",
    )
    logger.info("config_subscriber_started listening for camera lifecycle events")

    async for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        channel = message["channel"]
        if isinstance(channel, bytes):
            channel = channel.decode()

        # channel format: camera:{action}:{camera_id}
        parts = channel.split(":")
        if len(parts) < 3:
            continue
        action = parts[1]
        try:
            camera_id = UUID(parts[2])
        except ValueError:
            logger.warning("config_subscriber: invalid camera_id in channel %s", channel)
            continue

        if action == "added":
            await _handle_camera_added(camera_id, cfg, redis_client, frame_store, publisher, db_engine)
        elif action == "updated":
            await _handle_camera_updated(camera_id, cfg, redis_client, frame_store, publisher, db_engine)
        elif action == "removed":
            await _handle_camera_removed(camera_id)


async def _handle_camera_added(
    camera_id: UUID, cfg, redis_client, frame_store, publisher, db_engine
) -> None:
    if camera_id in _workers:
        logger.info("camera_already_active camera_id=%s — skipping add", camera_id)
        return

    camera = await get_camera_by_id(db_engine, camera_id)
    if camera is None:
        logger.warning("camera_not_found camera_id=%s — cannot add", camera_id)
        return

    _start_worker(camera, cfg, redis_client, frame_store, publisher, db_engine)
    logger.info("camera_added camera_id=%s", camera_id)


async def _handle_camera_updated(
    camera_id: UUID, cfg, redis_client, frame_store, publisher, db_engine
) -> None:
    # Gracefully stop old worker, re-read config from DB, start new worker
    await _handle_camera_removed(camera_id)
    await _handle_camera_added(camera_id, cfg, redis_client, frame_store, publisher, db_engine)
    logger.info("camera_config_reloaded camera_id=%s", camera_id)


async def _handle_camera_removed(camera_id: UUID) -> None:
    task = _workers.pop(camera_id, None)
    hb = _heartbeats.pop(camera_id, None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    if hb:
        hb.cancel()
        try:
            await hb
        except asyncio.CancelledError:
            pass
    logger.info("camera_removed camera_id=%s", camera_id)


# ── Worker lifecycle helper ───────────────────────────────────────────────


def _start_worker(camera, cfg, redis_client, frame_store, publisher, db_engine) -> None:
    camera_id = camera["id"]
    task = asyncio.create_task(
        camera_worker(camera, cfg, redis_client, frame_store, publisher, db_engine),
        name=f"worker-{camera_id}",
    )
    hb = asyncio.create_task(
        heartbeat_loop(redis_client, camera_id, cfg.heartbeat_interval_s),
        name=f"heartbeat-{camera_id}",
    )
    _workers[camera_id] = task
    _heartbeats[camera_id] = hb


# ── Entrypoint ────────────────────────────────────────────────────────────


async def run_service() -> None:
    cfg = load_config()

    # ── Infrastructure clients ────────────────────────────────────────
    redis_client = aioredis.from_url(cfg.redis_url, decode_responses=False)
    db_engine = await create_db_engine(cfg.database_url)
    frame_store = FrameStore(
        endpoint=cfg.minio_endpoint,
        access_key=cfg.minio_access_key,
        secret_key=cfg.minio_secret_key,
        secure=cfg.minio_secure,
        bucket=cfg.minio_bucket,
    )
    publisher = FramePublisher(redis_client, maxlen=cfg.stream_maxlen)

    # ── Load cameras and spawn workers ────────────────────────────────
    cameras = await load_cameras(db_engine)
    for cam in cameras:
        _start_worker(cam, cfg, redis_client, frame_store, publisher, db_engine)

    register_workers(_workers)
    logger.info("ingestion_service_started cameras=%d", len(cameras))

    # ── Background tasks ─────────────────────────────────────────────
    config_task = asyncio.create_task(
        config_subscriber(cfg, redis_client, frame_store, publisher, db_engine),
        name="config-subscriber",
    )

    # ── Health server (uvicorn in-process) ────────────────────────────
    uvi_config = uvicorn.Config(
        health_app,
        host="0.0.0.0",
        port=cfg.health_port,
        log_level="warning",
    )
    server = uvicorn.Server(uvi_config)
    health_task = asyncio.create_task(server.serve(), name="health-server")

    # ── Wait forever (or until a fatal signal) ────────────────────────
    try:
        await asyncio.gather(config_task, health_task)
    except asyncio.CancelledError:
        pass
    finally:
        # Graceful shutdown
        for cid in list(_workers):
            await _handle_camera_removed(cid)
        await redis_client.aclose()
        await db_engine.dispose()
        logger.info("ingestion_service_stopped")


def main() -> None:
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
