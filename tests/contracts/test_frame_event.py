import pytest

from uuid import uuid4
from datetime import datetime, timezone

from shared.contracts.frame_event import FrameEvent, FrameEventSchema
from shared.contracts.enums import FrameProvider

def make_frame_event(**overrides) -> FrameEvent:
    defaults = dict(
        camera_id=uuid4(),
        frame_seq=1,
        timestamp=datetime.now(timezone.utc),
        frame_provider=FrameProvider.MINIO,
        frame_reference="frames/test-camera/00000001.jpg",
        frame_shape=(1080, 1920),
    )
    defaults.update(overrides)
    return FrameEvent(**defaults)

def test_minio_reference_must_start_with_frames():
    event = make_frame_event(frame_reference="wrong/path/frame.jpg")
    errors = FrameEventSchema.validated_reference_format(event)
    assert any("frames/" in e for e in errors)

def test_valid_minio_reference():
    event = make_frame_event(
        frame_reference="frames/cam-001/00000042.jpg"
    )
    errors = FrameEventSchema.validated_reference_format(event)
    assert errors == []

def test_invalid_frame_shape():
    event = make_frame_event(frame_shape=(0, 1920))
    errors = FrameEventSchema.validated_reference_format(event)
    assert any("frame_shape" in e for e in errors)

def test_json_roundtrip():
    event = make_frame_event()
    restored = FrameEvent.model_validate_json(event.model_dump_json())
    assert restored.event_id == event.event_id
    assert restored.frame_seq == event.frame_seq