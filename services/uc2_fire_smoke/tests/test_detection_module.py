import io
import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from services.uc2_fire_smoke.src.main import app


def test_detection_status():
    """Test GET /detection/status returns valid module metadata."""
    client = TestClient(app)
    res = client.get("/detection/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ready"
    assert data["service"] == "detection_module"
    assert "fire" in data["supported_classes"]
    assert "smoke" in data["supported_classes"]
    assert "sparks" in data["supported_classes"]
    assert "image" in data["supported_modes"]
    assert "video" in data["supported_modes"]
    assert "rtsp" in data["supported_modes"]


def test_detection_image_upload():
    """Test POST /detection/image with real OpenCV image upload."""
    client = TestClient(app)
    # Create test image with simulated flame
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    cv2.circle(img, (150, 150), 50, (0, 140, 255), -1)  # bright orange flame-like blob
    ok, buf = cv2.imencode(".jpg", img)
    assert ok

    files = {"file": ("test_flame.jpg", io.BytesIO(buf.tobytes()), "image/jpeg")}
    res = client.post("/detection/image", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["input_mode"] == "image"
    assert "annotated_image" in data
    assert data["annotated_image"].startswith("data:image/jpeg;base64,")
    assert "summary" in data
    assert "inference_latency_ms" in data


def test_detection_rtsp_lifecycle():
    """Test RTSP status and stop endpoints."""
    client = TestClient(app)
    # Initial status
    res = client.get("/detection/rtsp/status")
    assert res.status_code == 200
    data = res.json()
    assert "connected" in data
    assert data["connected"] is False

    # Stop when none active
    res = client.post("/detection/rtsp/stop")
    assert res.status_code == 200
    assert res.json()["status"] == "stopped"


def test_detection_video_upload():
    """Test POST /detection/video with actual test video."""
    client = TestClient(app)
    video_path = "test_data/videos/uc2.mp4"
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    files = {"file": ("demo_test.mp4", io.BytesIO(video_bytes), "video/mp4")}
    res = client.post("/detection/video", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["input_mode"] == "video"
    assert "sampled_frames_processed" in data
    assert data["sampled_frames_processed"] > 0
    assert "summary" in data
    assert "duration_seconds" in data

