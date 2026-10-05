import asyncio
import json
import pytest
import cv2
import numpy as np
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from shared.contracts.frame_event import FrameEvent
from shared.contracts.enums import FrameProvider, SourceUC, AlertSeverity
from shared.platform_client.alert_publisher import AlertPublisher
from stubs.uc3_stub.main import process_frame_message


@pytest.fixture
def sample_frame_event():
    return FrameEvent(
        event_id=uuid4(),
        camera_id=uuid4(),
        frame_seq=42,
        timestamp=datetime.now(timezone.utc),
        frame_provider=FrameProvider.REDIS,
        frame_reference="frame:00000000-0000-0000-0000-000000000003:42",
        frame_shape=(480, 640),
    )


@pytest.fixture
def fake_jpeg_bytes():
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    _, encoded = cv2.imencode(".jpg", img)
    return encoded.tobytes()


@pytest.mark.asyncio
async def test_process_frame_message_emits_valid_alert_event(sample_frame_event, fake_jpeg_bytes):
    mock_redis = AsyncMock()
    mock_redis.get.return_value = fake_jpeg_bytes
    mock_redis.xack.return_value = 1

    published_alerts = []

    async def mock_publish(alert):
        published_alerts.append(alert)
        return True

    mock_publisher = MagicMock(spec=AlertPublisher)
    mock_publisher.publish = AsyncMock(side_effect=mock_publish)

    fields = {
        "data": sample_frame_event.model_dump_json()
    }

    mock_violations = [{
        "worker_id": 7,
        "ppe_type": "helmet",
        "violation": "no-head-protection",
        "confidence": 0.85,
    }]

    # Patch evaluation and presence cascade to isolate pipeline logic
    with patch("stubs.uc3_stub.src.motion_gate.frame_has_motion", return_value=True), \
         patch("stubs.uc3_stub.src.person_gate.detect_persons", return_value=[(0, 0, 640, 480)]), \
         patch("stubs.uc3_stub.src.motion_gate.should_run_inference", return_value=True), \
         patch("stubs.uc3_stub.src.compliance.evaluate_compliance", return_value=("medium", ["no-head-protection"], mock_violations)):

        session_models = {"str": MagicMock()}
        motion_states = {}
        worker_states_map = {}

        # Pre-seed session model to avoid loading real YOLO weights during test
        cam_id_str = str(sample_frame_event.camera_id)
        mock_yolo = MagicMock()
        session_models[cam_id_str] = mock_yolo

        await process_frame_message(
            redis_client=mock_redis,
            publisher=mock_publisher,
            session_models=session_models,
            motion_states=motion_states,
            worker_states_map=worker_states_map,
            stream_name=f"frames:{cam_id_str}",
            msg_id="1700000000000-0",
            fields=fields,
        )

    # Verification assertions
    assert len(published_alerts) == 1
    alert = published_alerts[0]

    # CRITICAL CONTRACT VERIFICATIONS:
    assert alert.source_event_id == sample_frame_event.event_id  # Must match trigger FrameEvent!
    assert alert.camera_id == sample_frame_event.camera_id
    assert alert.frame_reference == sample_frame_event.frame_reference
    assert alert.frame_provider == sample_frame_event.frame_provider
    assert alert.source_uc == SourceUC.UC3
    assert alert.alert_type == "ppe_violation"
    assert alert.metadata["track_id"] == 7
    assert alert.metadata["missing_ppe"] == ["helmet"]
    assert alert.metadata["frame_seq"] == 42
