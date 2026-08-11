import os
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
)

from services.camera_registry.src import router as router_module
from services.camera_registry.src.service import CameraRegistryService


DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get(
    "REDIS_URL",
    "redis://redis:6379",
)


# ── Database ──────────────────────────────────────────────────────

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=5,
)

SessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


# ── Redis ─────────────────────────────────────────────────────────

redis_client = aioredis.from_url(
    REDIS_URL,
    decode_responses=True,
)


# ── Service ───────────────────────────────────────────────────────

camera_registry_service = CameraRegistryService(
    session_factory=SessionFactory,
    redis_client=redis_client,
)


def get_service() -> CameraRegistryService:
    return camera_registry_service


# ── Lifespan ──────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

    await redis_client.aclose()
    await engine.dispose()


# ── FastAPI ───────────────────────────────────────────────────────

app = FastAPI(
    title="Camera Registry Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router_module.router)

app.dependency_overrides[
    router_module.get_service
] = get_service


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "camera_registry",
    }