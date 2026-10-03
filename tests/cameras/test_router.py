import pytest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.auth.src.jwt import create_access_token
from services.camera_registry.src.router import router, get_service


class DummyCameraRegistryService:
    def __init__(self):
        self.cameras = {
            "cam-1": {
                "id": "cam-1",
                "name": "Entrance",
                "rtsp_url": "rtsp://secret-url:554/live",
                "status": "online",
                "use_cases": ["uc3"],
            }
        }

    async def get_active_cameras(self):
        return list(self.cameras.values())

    async def get_camera(self, camera_id: str):
        return self.cameras.get(camera_id)

    async def update_status(self, camera_id: str, status: str):
        if camera_id in self.cameras:
            self.cameras[camera_id]["status"] = status
        return True


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    dummy_service = DummyCameraRegistryService()
    app.dependency_overrides[get_service] = lambda: dummy_service
    return TestClient(app)


def test_get_camera_by_id_hides_rtsp_url_unauthenticated(client):
    res = client.get("/cameras/cam-1")
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == "cam-1"
    assert "rtsp_url" not in data


def test_get_camera_by_id_includes_rtsp_url_admin(client):
    token = create_access_token("admin1", "admin", [])
    res = client.get("/cameras/cam-1", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["rtsp_url"] == "rtsp://secret-url:554/live"


def test_get_camera_with_internal_key(client):
    with patch("services.camera_registry.src.router.settings.internal_service_key", "secret-key-123"):
        # Valid internal key
        res = client.get("/cameras/cam-1", headers={"X-Internal-Key": "secret-key-123"})
        assert res.status_code == 200
        assert res.json()["rtsp_url"] == "rtsp://secret-url:554/live"

        # Wrong internal key
        res = client.get("/cameras/cam-1", headers={"X-Internal-Key": "wrong-key"})
        assert res.status_code == 200
        assert "rtsp_url" not in res.json()

    # Empty internal key setting
    with patch("services.camera_registry.src.router.settings.internal_service_key", ""):
        res = client.get("/cameras/cam-1", headers={"X-Internal-Key": "secret-key-123"})
        assert res.status_code == 200
        assert "rtsp_url" not in res.json()


def test_get_camera_by_id_not_found(client):
    res = client.get("/cameras/nonexistent")
    assert res.status_code == 404


def test_list_cameras_hides_rtsp_url_unauthenticated(client):
    res = client.get("/cameras")
    assert res.status_code == 200
    cameras = res.json()
    assert len(cameras) == 1
    assert "rtsp_url" not in cameras[0]


def test_list_cameras_includes_rtsp_url_admin(client):
    token = create_access_token("admin1", "admin", [])
    res = client.get("/cameras", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    cameras = res.json()
    assert cameras[0]["rtsp_url"] == "rtsp://secret-url:554/live"


def test_list_cameras_with_internal_key(client):
    with patch("services.camera_registry.src.router.settings.internal_service_key", "secret-key-123"):
        res = client.get("/cameras", headers={"X-Internal-Key": "secret-key-123"})
        assert res.status_code == 200
        cameras = res.json()
        assert cameras[0]["rtsp_url"] == "rtsp://secret-url:554/live"


def test_patch_status_requires_admin_or_internal_key(client):
    with patch("services.camera_registry.src.router.settings.internal_service_key", "secret-key-123"):
        # Unauthenticated without key -> 401
        res = client.patch("/cameras/cam-1/status", json={"status": "offline"})
        assert res.status_code == 401

        # Viewer without key -> 403
        viewer_token = create_access_token("user1", "viewer", [])
        res = client.patch(
            "/cameras/cam-1/status",
            json={"status": "offline"},
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        assert res.status_code == 403

        # Viewer with internal key -> 200
        res = client.patch(
            "/cameras/cam-1/status",
            json={"status": "offline"},
            headers={"X-Internal-Key": "secret-key-123"},
        )
        assert res.status_code == 200

        # Admin -> 200
        admin_token = create_access_token("admin1", "admin", [])
        res = client.patch(
            "/cameras/cam-1/status",
            json={"status": "offline"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        assert res.json() == {"camera_id": "cam-1", "status": "offline"}
