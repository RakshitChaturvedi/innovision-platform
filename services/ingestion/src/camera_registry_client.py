from __future__ import annotations

import logging, httpx

from typing import Any
from services.ingestion.src.config import settings

logger = logging.getLogger(__name__)

class CameraRegistryError(Exception):
    """Raised when cam registry cant be reached or returns error"""

class CameraRegistryClient:
    # async http client
    def __init__(self) -> None:
        self._base_url = settings.camera_registry_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=5.0)
        )

    async def get_active_cameras(self) -> list[dict[str, Any]]:
        try:
            response = await self._client.get("/cameras")
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict):
                cameras = data.get("cameras", [])
            else:
                cameras = data

            if not isinstance(cameras, list):
                raise CameraRegistryError("Camera Registry returned invalid cam list")

            active_cameras = [camera for camera in cameras if camera.get("status") != "disabled"]
            logger.info("camera_registry_active_cameras count=%d", len(active_cameras))

            return active_cameras
        except httpx.HTTPError as e:
            logger.error("camera_registry_get_active_failed error=%s", e)
            raise CameraRegistryError("Failed to getch active cameras from camera registry") from e

    async def get_camera(self, camera_id: str) -> dict[str, Any] | None:
        try:
            response = await self._client.get(f"/cameras/{camera_id}")
            if response.status_code == 404:
                return None
            response.raise_for_status()

            data = response.json()
            if isinstance(data, dict) and "camera" in data:
                return data["camera"]
            return data
        except httpx.HTTPError as e:
            logger.error("camera_registry_get_cam_failed camera_id=%s error=%s", camera_id, e)
            raise CameraRegistryError(f"Failed to getch camera {camera_id}") from e

    async def update_status(self, camera_id: str, status:str) -> None:
        # report runtime cam status to cam registry (online, reconnecting, offline)
        try:
            response = await self._client.patch(f"/cameras/{camera_id}/status", json={"status": status})
            response.raise_for_status()

            logger.info("camera_status_updated camera_id=%s status=%s", camera_id, status)
        except httpx.HTTPError as e:
            logger.error("camera_registry_status_update_failed camera_id=%s status=%s error=%s",
                         camera_id, status, e)
            raise CameraRegistryError(f"Failed to update camera {camera_id} status") from e

    async def close(self) -> None:
        await self._client.aclose()
