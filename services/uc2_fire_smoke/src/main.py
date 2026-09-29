"""
UC2 Fire & Smoke Analytics Service — Main Application Entry Point.

FastAPI service listening on port 8030.
Manages application lifespan, async Redis connection pool, MinIO client,
multi-camera PipelineManager, and API endpoints.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.uc2_fire_smoke.src.api.router import router as api_router
from services.uc2_fire_smoke.src.config import settings
from services.uc2_fire_smoke.src.redis.client import RedisClientManager
from services.uc2_fire_smoke.src.storage.minio_client import MinIOClient
from services.uc2_fire_smoke.src.workers.pipeline_manager import PipelineManager

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("innovision.uc2.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Service lifespan manager:
      1. Connect Redis pool
      2. Initialize MinIO client
      3. Start PipelineManager (discovers cameras, launches workers)
      4. On shutdown: Stop PipelineManager, close Redis
    """
    logger.info("Initializing UC2 Fire & Smoke Analytics Service...")

    # 1. Connect Redis
    redis_mgr = RedisClientManager(host=settings.redis_host, port=settings.redis_port)
    redis_client = await redis_mgr.connect()
    app.state.redis_manager = redis_mgr
    app.state.redis_client = redis_client

    # 2. MinIO client
    minio_client = MinIOClient()
    app.state.minio_client = minio_client

    # 3. PipelineManager
    pipeline_mgr = PipelineManager(
        redis_client=redis_client,
        minio_client=minio_client,
    )
    app.state.pipeline_manager = pipeline_mgr
    await pipeline_mgr.start()

    logger.info(f"UC2 Service started successfully on port {settings.service_port}")

    yield

    # Shutdown sequence
    logger.info("Shutting down UC2 Service...")
    await pipeline_mgr.stop()
    await redis_mgr.close()
    logger.info("UC2 Service shutdown complete.")


app = FastAPI(
    title="Innovision UC2 — Fire & Smoke Analytics Service",
    description="Microservice for real-time fire and smoke video analytics, multi-stage verification, and alert publishing.",
    version=settings.pipeline_version,
    lifespan=lifespan,
)

# CORS middleware for operator dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount internal UC API routes
app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.uc2_fire_smoke.src.main:app",
        host="0.0.0.0",
        port=settings.service_port,
        reload=False,
    )
