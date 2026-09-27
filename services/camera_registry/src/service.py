import logging
import uuid
import redis.asyncio as aioredis

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from services.camera_registry.src.schemas import CameraCreate, CameraConfigUpdate

logger = logging.getLogger(__name__)

class CameraRegistryService:
    def __init__(self, session_factory, redis_client: aioredis.Redis):
        self._session_factory = session_factory
        self._redis = redis_client

    async def create_camera(self, data: CameraCreate) -> dict:
        camera_id = str(uuid.uuid4())

        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    INSERT INTO cameras
                        (id, name, location, rtsp_url, status, use_cases, fps)
                    VALUES
                        (:id, :name, :location, :rtsp_url, 'offline', :use_cases, :fps)
                """), {
                    "id": camera_id,
                    "name": data.name,
                    "location": data.location,
                    "rtsp_url": data.rtsp_url,
                    "use_cases": data.use_cases,
                    "fps": data.fps
                })
        await self._redis.publish(f"camera:added:{camera_id}", camera_id)
        logger.info("camera_created id=%s name=%s use_cases=%s", camera_id, data.name, data.use_cases)
        return {"id": camera_id, **data.model_dump()}

    async def update_config(self, camera_id: str, data: CameraConfigUpdate) -> None:
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    text(f"UPDATE cameras SET {set_clause}, updated_at = now() "
                         f"WHERE id = :camera_id"), {**updates, "camera_id": camera_id},
                )
        await self._redis.publish(f"camera:updated:{camera_id}", camera_id)
        logger.info("camera_updated id=%s field=%s", camera_id, list(updates.keys()))

    async def delete_camera(self, camera_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    text("UPDATE cameras SET status = 'disabled' WHERE id = :id"),
                    {"id": camera_id},
                )
        await self._redis.publish(f"camera:removed:{camera_id}", camera_id)
        logger.info("camera_removed id=%s", camera_id)

    async def get_cameras_for_uc(self, uc_id: str) -> list[str]:
        async with self._session_factory() as session:
            rows = await session.execute(
                text("SELECT id FROm cameras WHERE :uc_id = ANY(use_cases) AND status != 'disabled'"),
                {"uc_id": uc_id}
            )
            return [str(r.id) for r in rows.fetchall()]

    async def get_active_cameras(self) -> list[dict]:
        # used by ingestion service on startup to know what to connect to
        async with self._session_factory() as session:
            rows = await session.execute(
                text("""
                    SELECT id, name, location, rtsp_url, status, fps, use_cases
                    FROM cameras
                    WHERE status != 'disabled'
                """))
            return [dict(r._mapping) for r in rows.fetchall()]

    async def update_status(self, camera_id: str, status: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    UPDATE cameras SET status = :status, updated_at = now() WHERE id = :id
                """), {"status": status, "id": camera_id})

    async def get_camera(self, camera_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.execute(
                text("""
                    SELECT id, name, location, rtsp_url, status, fps, use_cases
                    FROM cameras
                    WHERE id = :id
                    AND status != 'disabled'
                """),
                {"id": camera_id},
            )

            camera = row.fetchone()

            if not camera:
                return None

            return dict(camera._mapping)