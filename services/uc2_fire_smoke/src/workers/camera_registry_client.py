"""
HTTP Client for Camera Registry Service.
Discovers active cameras and listens for configuration updates.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import httpx

from services.uc2_fire_smoke.src.config import settings

logger = logging.getLogger("innovision.uc2.camera_registry_client")


class CameraRegistryClient:
    """
    Communicates with Camera Registry (host port 8011).
    """

    def __init__(self, base_url: Optional[str] = None) -> None:
        self.base_url = (base_url or settings.camera_registry_url).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=5.0,
            )
        return self._client

    async def get_active_cameras(self, uc_id: str = "uc2") -> List[Dict[str, Any]]:
        """
        Fetch active cameras assigned to or relevant for UC2.
        Queries GET /cameras or GET /cameras/by-uc/{uc_id}.
        """
        client = await self._get_client()
        try:
            # First try general GET /cameras
            response = await client.get("/cameras")
            if response.status_code == 200:
                cameras = response.json()
                if isinstance(cameras, list):
                    # Filter cameras that include uc2 or have no specific UC filter
                    filtered = [
                        c for c in cameras
                        if isinstance(c, dict) and (
                            not c.get("use_cases")
                            or uc_id in c.get("use_cases", [])
                            or "*" in c.get("use_cases", [])
                        ) and c.get("status") != "disabled"
                    ]
                    return filtered if filtered else cameras
            logger.warning(f"GET /cameras returned status {response.status_code}")
        except Exception as exc:
            logger.error(f"Failed to query Camera Registry at {self.base_url}: {exc}")

        return []

    async def get_camera(self, camera_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch details for a specific camera.
        """
        client = await self._get_client()
        try:
            response = await client.get(f"/cameras/{camera_id}")
            if response.status_code == 200:
                return response.json()
        except Exception as exc:
            logger.debug(f"Failed to get camera {camera_id}: {exc}")
        return None

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
