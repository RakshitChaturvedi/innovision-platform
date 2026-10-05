"""
UC3 PPE Detection Analytics Service — Main Application Entry Point.

FastAPI service listening on port 8040 (or configured UC3_PORT).
Manages application lifespan, async Redis connection pool, MinIO client,
multi-camera PipelineManager, and API endpoints.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.uc3_ppe_detection.src.api.router import router as api_router
from services.uc3_ppe_detection.src import config
from services.uc3_ppe_detection.src.storage.minio_client import MinIOClient
from services.uc3_ppe_detection.src.workers.pipeline_manager import PipelineManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("innovision.uc3.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing UC3 PPE Detection Service...")

    minio_client = MinIOClient()
    app.state.minio_client = minio_client

    pipeline_mgr = PipelineManager(minio_client=minio_client)
    app.state.pipeline_manager = pipeline_mgr
    await pipeline_mgr.start()

    logger.info(f"UC3 Service started successfully on port {config.SERVICE_PORT}")

    yield

    logger.info("Shutting down UC3 Service...")
    await pipeline_mgr.stop()
    logger.info("UC3 Service shutdown complete.")


app = FastAPI(
    title="Innovision UC3 — PPE Detection Analytics Service",
    description="Microservice for real-time PPE detection, tracking, compliance analysis, and alert publishing.",
    version=config.PIPELINE_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "services.uc3_ppe_detection.src.main:app",
        host="0.0.0.0",
        port=config.SERVICE_PORT,
        reload=False,
    )
