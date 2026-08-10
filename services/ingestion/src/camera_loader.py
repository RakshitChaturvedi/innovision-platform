"""
Camera Loader — reads camera records from PostgreSQL and provides
helpers to update camera status in the database.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, async_sessionmaker

from shared.contracts.enums import CameraStatus

logger = logging.getLogger(__name__)


async def create_db_engine(database_url: str) -> AsyncEngine:
    """Create and return an async SQLAlchemy engine."""
    return create_async_engine(database_url, pool_size=5, max_overflow=5)


async def load_cameras(engine: AsyncEngine) -> list[dict[str, Any]]:
    """
    Fetch all non-disabled cameras from the cameras table.

    Returns a list of dicts with keys:
        id (UUID), name, rtsp_url, fps, status, use_cases, location
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            text(
                "SELECT id, name, rtsp_url, fps, status, use_cases, location "
                "FROM cameras WHERE status != 'disabled'"
            )
        )
        cameras = []
        for row in result.fetchall():
            cameras.append(
                {
                    "id": row.id if isinstance(row.id, UUID) else UUID(str(row.id)),
                    "name": row.name,
                    "rtsp_url": row.rtsp_url,
                    "fps": row.fps or 10,
                    "status": row.status,
                    "use_cases": row.use_cases or [],
                    "location": row.location,
                }
            )
        logger.info("loaded %d cameras from database", len(cameras))
        return cameras


async def update_camera_status(
    engine: AsyncEngine, camera_id: UUID, status: CameraStatus
) -> None:
    """Update the status column for a single camera."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            await session.execute(
                text("UPDATE cameras SET status = :status, updated_at = now() WHERE id = :id"),
                {"status": status.value, "id": str(camera_id)},
            )
    logger.info("camera_status_updated camera_id=%s status=%s", camera_id, status.value)


async def get_camera_by_id(engine: AsyncEngine, camera_id: UUID) -> dict[str, Any] | None:
    """Fetch a single camera record by ID."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        result = await session.execute(
            text("SELECT id, name, rtsp_url, fps, status, use_cases, location FROM cameras WHERE id = :id"),
            {"id": str(camera_id)},
        )
        row = result.fetchone()
        if row is None:
            return None
        return {
            "id": row.id if isinstance(row.id, UUID) else UUID(str(row.id)),
            "name": row.name,
            "rtsp_url": row.rtsp_url,
            "fps": row.fps or 10,
            "status": row.status,
            "use_cases": row.use_cases or [],
            "location": row.location,
        }
