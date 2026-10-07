"""
UC3 PPE Detection Microservice — Main Orchestrator
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import sys

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.uc3.src.consumer import UC3ConsumerManager
from services.uc3.src.publisher import UC3EventPublisher
from services.uc3.src import router as uc3_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("uc3_main")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
CAMERA_REGISTRY_URL = os.environ.get("CAMERA_REGISTRY_URL", "http://camera_registry:8011")

redis_client: aioredis.Redis | None = None
publisher: UC3EventPublisher | None = None
consumer_manager: UC3ConsumerManager | None = None
consumer_task: asyncio.Task | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, publisher, consumer_manager, consumer_task

    logger.info("uc3_service_starting")

    # 1. Connect Redis
    redis_client = aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    await redis_client.ping()
    logger.info("redis_connected host=%s port=%d", REDIS_HOST, REDIS_PORT)

    # 2. Init Publisher & Consumer
    publisher = UC3EventPublisher(redis_client)
    consumer_manager = UC3ConsumerManager(
        redis_client=redis_client,
        publisher=publisher,
        camera_registry_url=CAMERA_REGISTRY_URL,
    )
    uc3_router.consumer_manager = consumer_manager

    # 3. Start background XREADGROUP loop
    consumer_task = asyncio.create_task(consumer_manager.run(), name="uc3-consumer")
    logger.info("uc3_consumer_task_started")

    try:
        yield
    finally:
        logger.info("uc3_service_shutting_down")
        if consumer_manager:
            consumer_manager.stop()
        if consumer_task:
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
        if publisher:
            await publisher.close()
        if redis_client:
            await redis_client.aclose()
        logger.info("uc3_service_stopped")

app = FastAPI(title="Innovision UC3 PPE Detection Service", version="1.0.0-phase3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(uc3_router.router)
app.add_api_route("/health", uc3_router.get_health, methods=["GET"])
app.add_api_route("/metrics", uc3_router.get_metrics, methods=["GET"])
