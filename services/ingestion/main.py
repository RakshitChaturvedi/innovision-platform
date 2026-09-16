"""
Ingestion Service — Main Orchestrator
Wires together:

    Camera Registry
          │
          ▼
    CameraManager
          │
          ├── CameraIngestionTask
          │       ├── StreamDecoder
          │       ├── FrameSampler
          │       ├── JpegEncoder
          │       ├── FrameCache
          │       ├── FrameStore
          │       ├── FramePublisher
          │       └── Heartbeat
          │
          └── OfflineMonitor

The service exposes /health through the FastAPI application.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import redis.asyncio as aioredis
from fastapi import FastAPI
from contextlib import asynccontextmanager

from services.ingestion.src.camera_manager import CameraManager
from services.ingestion.src.camera_registry_client import CameraRegistryClient
from services.ingestion.src.config import settings
from services.ingestion.src.frame_cache import FrameCache
from services.ingestion.src.frame_store import FrameStore
from services.ingestion.src.health import register_workers, router as health_router
from services.ingestion.src.offline_monitor import OfflineMonitor
from services.ingestion.src.publisher import FramePublisher
from services.ingestion.src.streaming import router as streaming_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("__name__")

# ── Application State ──────────────────────────────
redis_client: aioredis.Redis | None = None
registry_client: CameraRegistryClient | None = None
camera_manager: CameraManager | None = None
offline_monitor: OfflineMonitor | None = None
offline_monitor_task = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Start and stop the complete ingestion service.
    """

    global redis_client
    global registry_client
    global camera_manager
    global offline_monitor
    global offline_monitor_task

    logger.info("ingestion_service_starting")

    # 1. Redis
    redis_client = aioredis.from_url(
        f"redis://{settings.redis_host}:{settings.redis_port}",
        decode_responses=False,
    )
    await redis_client.ping() # verify redis is reachable
    logger.info("redis_connected")

    # 2. Camera Registry
    registry_client = CameraRegistryClient()
    logger.info(
        "camera_registry_client_initialized url=%s",
        settings.camera_registry_url,
    )

    # 3. Frame Infra
    frame_publisher = FramePublisher(redis_client=redis_client)
    frame_cache = FrameCache(redis_client=redis_client)
    frame_store = FrameStore()

    # 4. Camera manager
    camera_manager = CameraManager(
        registry_client=registry_client,
        redis_client=redis_client,
        publisher=frame_publisher,
        frame_cache=frame_cache,
        frame_store=frame_store,
    )
    register_workers(camera_manager._camera_tasks) # register managers live cam dict with health.py
    await camera_manager.start()

    # 5. Offline monitor
    offline_monitor = OfflineMonitor( redis_client=redis_client, registry_client=registry_client)
    offline_monitor_task = asyncio.create_task(offline_monitor.run(),name="offline-monitor")
    logger.info(
        "ingestion_service_started active_cameras=%d", camera_manager.active_camera_count
    )

    try:
        yield

    finally:
        logger.info("ingestion_service_shutting_down")

        # stop offline monitor first so it doesnt try to update cameras while the rest of the service is shutting down.
        if offline_monitor_task is not None:
            offline_monitor_task.cancel()
            try:
                await offline_monitor_task
            except asyncio.CancelledError:
                pass

        # stop cam workers
        if camera_manager is not None:
            await camera_manager.stop()

        # close cam registry http client
        if registry_client is not None:
            await registry_client.close()

        # close redis
        if redis_client is not None:
            await redis_client.aclose()
        logger.info("ingestion_service_stopped")

app = FastAPI(title="Innovision Ingestion Service", version="1.0.0-phase2", lifespan=lifespan)
app.include_router(health_router)
app.include_router(streaming_router)