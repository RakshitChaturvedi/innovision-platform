import sys
from unittest.mock import patch, AsyncMock, MagicMock

# Mock numpy and cv2 if not installed in local venv
for mod in ["numpy", "cv2"]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import pytest
import httpx

from services.ingestion.src.camera_registry_client import CameraRegistryClient
from services.ingestion.src.camera_manager import CameraManager


@pytest.mark.asyncio
async def test_ingestion_client_sends_internal_key():
    """CameraRegistryClient includes X-Internal-Key when internal_service_key is configured."""
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        if request.url.path == "/cameras":
            return httpx.Response(200, json=[{"id": "cam-1", "rtsp_url": "rtsp://live:554/feed", "status": "online"}])
        elif request.url.path == "/cameras/cam-1":
            return httpx.Response(200, json={"id": "cam-1", "rtsp_url": "rtsp://live:554/feed", "status": "online"})
        elif request.url.path == "/cameras/cam-1/status":
            return httpx.Response(200, json={"camera_id": "cam-1", "status": "online"})
        return httpx.Response(404)

    mock_transport = httpx.MockTransport(mock_handler)

    with patch("services.ingestion.src.camera_registry_client.settings.internal_service_key", "my-secret-key"):
        client = CameraRegistryClient()
        client._client = httpx.AsyncClient(
            base_url="http://camera_registry:8011",
            transport=mock_transport,
            headers={"X-Internal-Key": "my-secret-key"},
        )

        cams = await client.get_active_cameras()
        assert len(cams) == 1

        cam = await client.get_camera("cam-1")
        assert cam["id"] == "cam-1"

        await client.update_status("cam-1", "online")

        await client.close()

    assert len(captured_requests) == 3
    for req in captured_requests:
        assert req.headers.get("X-Internal-Key") == "my-secret-key"


@pytest.mark.asyncio
async def test_camera_manager_starts_task_only_when_rtsp_url_present():
    """CameraManager starts a task for a camera only when rtsp_url is present."""
    mock_registry = AsyncMock()
    mock_registry.get_active_cameras = AsyncMock(return_value=[
        {"id": "cam-with-rtsp", "name": "Cam 1", "rtsp_url": "rtsp://stream:554/live", "status": "online"},
        {"id": "cam-without-rtsp", "name": "Cam 2", "status": "online"},
    ])

    mock_redis = AsyncMock()
    mock_publisher = MagicMock()
    mock_frame_cache = MagicMock()
    mock_frame_store = MagicMock()

    manager = CameraManager(
        registry_client=mock_registry,
        redis_client=mock_redis,
        publisher=mock_publisher,
        frame_cache=mock_frame_cache,
        frame_store=mock_frame_store,
    )

    with patch("services.ingestion.src.camera_manager.CameraIngestionTask") as mock_task_cls:
        mock_task_instance = AsyncMock()
        mock_task_instance.run = AsyncMock()
        mock_task_cls.return_value = mock_task_instance

        # Call _start_camera directly for both
        await manager._start_camera({"id": "cam-with-rtsp", "name": "Cam 1", "rtsp_url": "rtsp://stream:554/live", "status": "online"})
        await manager._start_camera({"id": "cam-without-rtsp", "name": "Cam 2", "status": "online"})

        # Only cam-with-rtsp should be in active_camera_ids
        assert "cam-with-rtsp" in manager.active_camera_ids
        assert "cam-without-rtsp" not in manager.active_camera_ids
        assert manager.active_camera_count == 1

        # Clean up
        await manager._stop_camera("cam-with-rtsp")
