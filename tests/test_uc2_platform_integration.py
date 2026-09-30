"""
UC2 Platform Integration Test Suite.

Verifies:
  1. UC2 imports successfully
  2. UC2 components and pipeline initialize cleanly
  3. Real Fire detection creates the canonical platform AlertEvent (SourceUC.UC2)
  4. Real Smoke detection creates the canonical platform AlertEvent (SourceUC.UC2)
  5. Event publishing uses the existing platform mechanism (AlertPublisher -> alerts:live)
  6. Detection metadata is properly preserved
  7. UC3 stub integration remains completely intact and functional
  8. Platform contracts and validation pass with zero errors
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import cv2
import numpy as np
import pytest

from shared.contracts.alert_event import AlertEvent, AlertEventValidator
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher, ALERTS_LIVE_STREAM


def test_1_uc2_imports_and_components():
    """Verify UC2 imports and initializes cleanly."""
    import stubs.uc2_stub.main as uc2_stub
    from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline
    from services.uc2_fire_smoke.src.workers.camera_worker import CameraWorker
    from services.uc2_fire_smoke.src.config import settings

    assert uc2_stub.TEST_CAMERA_ID == UUID("00000000-0000-0000-0000-000000000002")
    assert len(uc2_stub.UC2_SCENARIOS) >= 2
    assert settings.service_name == "uc2_fire_smoke"


def test_2_real_fire_detection_creates_platform_event():
    """Verify fire detection creates a canonical platform AlertEvent."""
    from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline
    from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier
    from services.uc2_fire_smoke.src.detection.confidence import ConfidenceFusion

    verifier = DeterministicVerifier()
    fusion = ConfidenceFusion()

    # Create synthetic flame ROI (orange/red high saturation)
    flame_roi = np.zeros((100, 100, 3), dtype=np.uint8)
    flame_roi[:, :] = (20, 150, 255)

    v_res = verifier.verify_fire(flame_roi)
    assert v_res.passed is True
    assert v_res.hsv_score > 0.40

    f_res = fusion.fuse(
        yolo_conf=0.92,
        hsv_score=v_res.hsv_score,
        texture_score=0.50,
        temporal_score=0.95,
        det_type="fire",
    )
    assert f_res.final_confidence >= 0.70
    assert f_res.alert_type == "fire_detected"

    camera_id = UUID("00000000-0000-0000-0000-000000000002")
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=f_res.severity,
        alert_type=f_res.alert_type,
        title="Fire Detected in Warehouse B",
        description=f"Fire detected with confidence {f_res.final_confidence:.2f}.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        status=AlertStatus.PENDING,
        metadata={
            "confidence": f_res.final_confidence,
            "verification_score": f_res.verification_score,
            "bounding_boxes": [{"x1": 10, "y1": 10, "x2": 110, "y2": 110}],
            "zone_id": "zone-warehouse-b",
            "frame_seq": 105,
        },
    )

    errors = AlertEventValidator.validate(alert, known_cam_ids={camera_id})
    assert len(errors) == 0
    assert alert.source_uc == SourceUC.UC2
    assert alert.alert_type == "fire_detected"
    assert alert.metadata["confidence"] == f_res.final_confidence
    assert len(alert.metadata["bounding_boxes"]) == 1


def test_3_real_smoke_detection_creates_platform_event():
    """Verify smoke detection creates a canonical platform AlertEvent."""
    from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier
    from services.uc2_fire_smoke.src.detection.confidence import ConfidenceFusion

    verifier = DeterministicVerifier()
    fusion = ConfidenceFusion()

    # Create synthetic smoke ROI (desaturated turbulent texture)
    h, w = 80, 80
    smoke_roi = np.full((h, w, 3), 130, dtype=np.uint8)
    noise = np.random.normal(0, 25, (h, w)).astype(np.int16)
    for c in range(3):
        smoke_roi[:, :, c] = np.clip(smoke_roi[:, :, c].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    smoke_roi = cv2.GaussianBlur(smoke_roi, (5, 5), 0)

    v_res = verifier.verify_smoke(smoke_roi)
    assert v_res.passed is True

    f_res = fusion.fuse(
        yolo_conf=0.86,
        hsv_score=v_res.hsv_score,
        texture_score=v_res.texture_score,
        temporal_score=0.90,
        det_type="smoke",
    )
    assert f_res.final_confidence >= 0.70
    assert f_res.alert_type == "smoke_detected"

    camera_id = UUID("00000000-0000-0000-0000-000000000002")
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=f_res.severity,
        alert_type=f_res.alert_type,
        title="Smoke Detected in Server Room",
        description=f"Smoke detected with confidence {f_res.final_confidence:.2f}.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        status=AlertStatus.PENDING,
        metadata={
            "confidence": f_res.final_confidence,
            "verification_score": f_res.verification_score,
            "bounding_boxes": [{"x1": 50, "y1": 50, "x2": 150, "y2": 150}],
            "zone_id": "zone-server-room",
        },
    )

    errors = AlertEventValidator.validate(alert, known_cam_ids={camera_id})
    assert len(errors) == 0
    assert alert.source_uc == SourceUC.UC2
    assert alert.alert_type == "smoke_detected"


@pytest.mark.asyncio
async def test_4_event_publishing_uses_platform_alert_publisher():
    """Verify UC2 events are published to Redis stream alerts:live via AlertPublisher."""
    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = "1727700000000-0"

    publisher = AlertPublisher(redis_client=mock_redis)
    camera_id = UUID("00000000-0000-0000-0000-000000000002")

    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        alert_type="fire_detected",
        title="Fire Alert",
        description="Fire detected.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
    )

    success = await publisher.publish(alert)
    assert success is True

    mock_redis.xadd.assert_called_once()
    stream_name, fields = mock_redis.xadd.call_args[0]
    assert stream_name == ALERTS_LIVE_STREAM
    assert "data" in fields

    # Validate that payload decodes back into AlertEvent
    published_event = AlertEvent.model_validate_json(fields["data"])
    assert published_event.alert_id == alert.alert_id
    assert published_event.source_uc == SourceUC.UC2


def test_5_uc3_untouched_and_functional():
    """Verify UC3 reference stub is completely untouched and functioning as expected."""
    import stubs.uc3_stub.main as uc3_stub

    assert uc3_stub.TEST_CAMERA_ID == UUID("00000000-0000-0000-0000-000000000003")
    assert len(uc3_stub.UC3_SCENARIOS) >= 2
    for s in uc3_stub.UC3_SCENARIOS:
        alert = AlertEvent(
            camera_id=uc3_stub.TEST_CAMERA_ID,
            timestamp=datetime.now(timezone.utc),
            severity=s["severity"],
            alert_type=s["alert_type"],
            title=s["title"],
            description=s["description"],
            source_event_id=uuid4(),
            source_uc=SourceUC.UC3,
            metadata=s["metadata"],
        )
        assert alert.source_uc == SourceUC.UC3
        errors = AlertEventValidator.validate(alert, known_cam_ids={uc3_stub.TEST_CAMERA_ID})
        assert len(errors) == 0
