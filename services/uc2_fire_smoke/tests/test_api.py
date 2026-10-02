"""
Tests for UC2 API endpoints and AlertPublisher.
"""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher
from services.uc2_fire_smoke.src.api.router import router
from services.uc2_fire_smoke.src.main import app


@pytest.mark.asyncio
async def test_alert_publisher_success():
    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = b"1600000000000-0"

    publisher = AlertPublisher(redis_client=mock_redis)
    event = AlertEvent(
        camera_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="fire_detected",
        title="Fire Test Alert",
        description="Test fire detection.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
    )

    success = await publisher.publish(event)
    assert success is True
    assert mock_redis.xadd.called
    args, kwargs = mock_redis.xadd.call_args
    assert args[0] == "alerts:live"
    assert "data" in args[1]


def test_api_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "uc2_fire_smoke"


def test_api_compliance_metrics():
    client = TestClient(app)
    response = client.get("/metrics/compliance")
    assert response.status_code == 200
    data = response.json()
    assert data["use_case"] == "uc2"
    assert "compliance_score" in data


def test_api_mode_switch():
    client = TestClient(app)
    response = client.post("/mode", json={"mode": "SENSITIVE"})
    assert response.status_code == 200
    assert response.json()["detection_mode"] == "SENSITIVE"


def test_api_liveness():
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "alive"
    assert data["service"] == "uc2_fire_smoke"


def test_api_diagnostic_and_metrics():
    client = TestClient(app)
    # Mock pipeline manager on app.state
    mock_pm = MagicMock()
    mock_pm.get_pipeline_status.return_value = {"active_workers": 1}
    mock_pm.yolo_engine.get_model_info.return_value = {"model": "fireguard"}
    mock_pm.yolo_engine.is_ready.return_value = True
    mock_pm.yolo_engine.device = "cpu"
    mock_pm.yolo_engine.class_names = ["fire", "smoke", "sparks"]
    mock_pm.redis.ping = AsyncMock(return_value=True)
    mock_pm.minio.check_health = AsyncMock(return_value=True)
    mock_pm._workers = {"cam-1": MagicMock()}

    app.state.pipeline_manager = mock_pm

    # Test /health/ready
    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200
    assert res_ready.json()["ready"] is True

    # Test /health/diagnostic
    res_diag = client.get("/health/diagnostic")
    assert res_diag.status_code == 200
    assert res_diag.json()["settings"]["device"] == "auto"

    # Test /metrics
    res_metrics = client.get("/metrics")
    assert res_metrics.status_code == 200
    assert b"uc2_frames_processed_total" in res_metrics.content

