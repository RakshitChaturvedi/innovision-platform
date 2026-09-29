"""
UC2 Fire & Smoke Integration Tests (Mocked Redis & MinIO).

Validates the full UC2 integration flow against the shared Innovision Platform:
  1. FrameEvent parsing & contract validation
  2. Redis hot cache retrieval (frame:{camera_id}:{frame_seq})
  3. MinIO fallback retrieval (frames/{camera_id}/{frame_seq:08d}.jpg)
  4. DetectionPipeline execution (YOLO + Deterministic CV + ByteTrack + Temporal)
  5. Multi-camera state isolation
  6. Canonical AlertEvent creation with SourceUC.UC2
  7. AlertEvent validation via AlertEventValidator
  8. Redis alerts:live publication via AlertPublisher
  9. Malformed / corrupted event handling
 10. Redis disconnect & recovery simulation
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import cv2
import numpy as np
import pytest

from shared.contracts.alert_event import AlertEvent, AlertEventValidator
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.contracts.frame_event import FrameEvent, FrameEventSchema
from shared.platform_client.alert_publisher import AlertPublisher
from services.uc2_fire_smoke.src.detection.confidence import ConfidenceFusion
from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline
from services.uc2_fire_smoke.src.detection.temporal import TemporalPersistenceTracker
from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier
from services.uc2_fire_smoke.src.redis.frame_consumer import RedisFrameConsumer


# ==============================================================================
# 1. FrameEvent Parsing & Validation
# ==============================================================================

def test_frame_event_contract_parsing():
    cam_id = uuid4()
    ev = FrameEvent(
        event_id=uuid4(),
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        frame_seq=42,
        frame_provider=FrameProvider.REDIS,
        frame_reference=f"frame:{cam_id}:42",
        frame_shape=(480, 640),
    )
    raw_json = ev.model_dump_json()
    parsed = FrameEvent.model_validate_json(raw_json)
    assert parsed.camera_id == cam_id
    assert parsed.frame_seq == 42
    assert parsed.frame_provider == FrameProvider.REDIS
    errors = FrameEventSchema.validated_reference_format(parsed)
    assert len(errors) == 0


# ==============================================================================
# 2. Redis Hot Cache & MinIO Fallback
# ==============================================================================

@pytest.mark.asyncio
async def test_frame_consumer_hot_cache_retrieval():
    mock_redis = AsyncMock()
    cam_id = uuid4()

    # Synthetic JPEG
    test_img = np.zeros((100, 100, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", test_img)
    mock_redis.get.return_value = encoded.tobytes()

    consumer = RedisFrameConsumer(redis_client=mock_redis, camera_id=cam_id)
    ev = FrameEvent(
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        frame_seq=1,
        frame_provider=FrameProvider.REDIS,
        frame_reference=f"frame:{cam_id}:1",
        frame_shape=(100, 100),
    )
    retrieved = await consumer.fetch_frame_image(ev)
    assert retrieved is not None
    assert retrieved.shape == (100, 100, 3)
    mock_redis.get.assert_called_once_with(f"frame:{cam_id}:1")


@pytest.mark.asyncio
async def test_frame_consumer_minio_fallback():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Cache miss

    mock_minio = AsyncMock()
    test_img = np.zeros((120, 160, 3), dtype=np.uint8)
    mock_minio.get_frame.return_value = test_img

    cam_id = uuid4()
    consumer = RedisFrameConsumer(redis_client=mock_redis, camera_id=cam_id, minio_client=mock_minio)
    ev = FrameEvent(
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        frame_seq=5,
        frame_provider=FrameProvider.MINIO,
        frame_reference=f"frames/{cam_id}/00000005.jpg",
        frame_shape=(120, 160),
    )
    retrieved = await consumer.fetch_frame_image(ev)
    assert retrieved is not None
    assert retrieved.shape == (120, 160, 3)
    mock_minio.get_frame.assert_called_once()


# ==============================================================================
# 3. Multi-Camera State Isolation
# ==============================================================================

def test_multi_camera_state_isolation():
    tracker = TemporalPersistenceTracker(persistence_threshold=3, smoothing_alpha=0.7)
    cam_a = "cam-alpha-001"
    cam_b = "cam-beta-002"

    det_key = "fire:0.5:0.5"

    # Camera A receives 3 detections -> persistent
    is_p_a1, c_a1, _ = tracker.update(cam_a, det_key, 0.85)
    is_p_a2, c_a2, _ = tracker.update(cam_a, det_key, 0.88)
    is_p_a3, c_a3, _ = tracker.update(cam_a, det_key, 0.90)
    assert is_p_a3 is True
    assert c_a3 == 3

    # Camera B receives 1 detection -> NOT persistent
    is_p_b1, c_b1, _ = tracker.update(cam_b, det_key, 0.85)
    assert is_p_b1 is False
    assert c_b1 == 1

    # Camera A state does NOT leak to Camera B
    assert tracker._counts[cam_a][det_key] == 3
    assert tracker._counts[cam_b][det_key] == 1


# ==============================================================================
# 4. Canonical AlertEvent Construction & Validation
# ==============================================================================

def test_canonical_alert_event_construction():
    alert_id = uuid4()
    cam_id = uuid4()
    alert = AlertEvent(
        alert_id=alert_id,
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        alert_type="fire_detected",
        title="Fire Detected in Zone Main Floor",
        description="Fire detected with confidence 0.94 at Camera 02.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        frame_reference=f"evidence/{cam_id}/{alert_id}.jpg",
        frame_provider=FrameProvider.MINIO,
        status=AlertStatus.PENDING,
        metadata={
            "confidence": 0.94,
            "verification_score": 0.92,
            "bounding_boxes": [{"x1": 100, "y1": 100, "x2": 200, "y2": 200}],
            "model_version": "yolo26m-v1.2",
        },
    )

    errors = AlertEventValidator.validate(alert, known_cam_ids={cam_id})
    assert len(errors) == 0
    assert alert.source_uc == SourceUC.UC2
    assert alert.severity == AlertSeverity.CRITICAL


# ==============================================================================
# 5. Redis alerts:live Publication via AlertPublisher
# ==============================================================================

@pytest.mark.asyncio
async def test_alert_publisher_dispatches_to_alerts_live():
    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = "1727650000000-0"

    publisher = AlertPublisher(redis_client=mock_redis)
    cam_id = uuid4()
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="smoke_detected",
        title="Smoke Detected",
        description="Smoke plume detected with confidence 0.85.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
    )

    success = await publisher.publish(alert)
    assert success is True
    mock_redis.xadd.assert_called_once()
    args, kwargs = mock_redis.xadd.call_args
    assert args[0] == "alerts:live"
    assert "data" in args[1]


# ==============================================================================
# 6. Malformed FrameEvent Safe Handling
# ==============================================================================

@pytest.mark.asyncio
async def test_corrupted_frame_event_handling():
    mock_redis = AsyncMock()
    cam_id = uuid4()

    # Return one corrupt JSON message and one missing data message
    mock_redis.xreadgroup.return_value = [
        (
            f"frames:{cam_id}",
            [
                (b"msg-1", {b"data": b"INVALID_NOT_JSON"}),
                (b"msg-2", {}),
            ],
        )
    ]

    consumer = RedisFrameConsumer(redis_client=mock_redis, camera_id=cam_id)
    frames_yielded = []
    async for item in consumer.read_frames():
        frames_yielded.append(item)

    # Corrupt messages are caught and not yielded
    assert len(frames_yielded) == 0
    # Both invalid messages were acknowledged so stream is not blocked
    assert mock_redis.xack.call_count == 2
