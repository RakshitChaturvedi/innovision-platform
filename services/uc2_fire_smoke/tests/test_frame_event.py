"""
Tests for FrameEvent contract validation.
"""
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from pydantic import ValidationError

from shared.contracts.enums import FrameProvider
from shared.contracts.frame_event import FrameEvent, FrameEventSchema


def test_frame_event_creation():
    cam_id = uuid4()
    event = FrameEvent(
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        frame_seq=42,
        frame_provider=FrameProvider.REDIS,
        frame_reference=f"frame:{cam_id}:42",
        frame_shape=(1080, 1920),
    )
    assert event.camera_id == cam_id
    assert event.frame_seq == 42
    assert event.frame_provider == FrameProvider.REDIS
    assert event.frame_shape == (1080, 1920)
    assert len(FrameEventSchema.validated_reference_format(event)) == 0


def test_frame_event_invalid_reference():
    cam_id = uuid4()
    event = FrameEvent(
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        frame_seq=1,
        frame_provider=FrameProvider.MINIO,
        frame_reference="invalid_path.jpg",
        frame_shape=(1080, 1920),
    )
    errors = FrameEventSchema.validated_reference_format(event)
    assert len(errors) > 0
    assert any("frames/" in e for e in errors)


def test_frame_event_json_roundtrip():
    cam_id = uuid4()
    event = FrameEvent(
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        frame_seq=100,
        frame_provider=FrameProvider.MINIO,
        frame_reference=f"frames/{cam_id}/00000100.jpg",
        frame_shape=(720, 1280),
    )
    json_str = event.model_dump_json()
    loaded = FrameEvent.model_validate_json(json_str)
    assert loaded.camera_id == event.camera_id
    assert loaded.frame_seq == event.frame_seq
    assert loaded.frame_reference == event.frame_reference
