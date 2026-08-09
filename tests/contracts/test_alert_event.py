import pytest

from uuid import uuid4
from datetime import datetime, timezone

from shared.contracts.alert_event import AlertEvent, AlertEventValidator
from shared.contracts.enums import AlertSeverity, AlertStatus, SourceUC, FrameProvider

def make_valid_alert(**overrides) -> AlertEvent:
    defaults = dict(
        camera_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="intruder",
        title="Intruder Detected -- server room",
        description="unknown individual entered restricted zone 'server room'.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC1
    )
    defaults.update(overrides)
    return AlertEvent(**defaults)

def test_valid_alert_constructs():
    alert = make_valid_alert()
    assert alert.status == AlertStatus.PENDING
    assert alert.metadata=={}

def test_empty_title_rejected():
    with pytest.raises(Exception):
        make_valid_alert(title="")

def test_empty_description_rejected():
    with pytest.raises(Exception):
        make_valid_alert(description="")

def test_frame_reference_without_provider_rejected():
    with pytest.raises(ValueError, match="frame_reference and frame_provider"):
        make_valid_alert(
            frame_reference="uc1/alerts/2026-05-22/test.jpg",
            frame_provider=None
        )

def test_frame_provider_without_reference_rejected():
    with pytest.raises(ValueError, match="frame_reference and frame_provider"):
        make_valid_alert(
            frame_reference=None,
            frame_provider=FrameProvider.MINIO,
        )


def test_frame_reference_and_provider_both_set():
    alert = make_valid_alert(
        frame_reference="uc1/alerts/2026-05-22/test.jpg",
        frame_provider=FrameProvider.MINIO,
    )
    assert alert.frame_reference is not None
    assert alert.frame_provider == FrameProvider.MINIO


def test_frame_reference_and_provider_both_omitted():
    alert = make_valid_alert(frame_reference=None, frame_provider=None)
    assert alert.frame_reference is None
    assert alert.frame_provider is None


def test_metadata_uc_specific_data():
    alert = make_valid_alert(metadata={
        "zone_id": "server-room",
        "track_id": 42,
        "classification_reason": "unknown_in_restricted",
    })
    assert alert.metadata["zone_id"] == "server-room"


def test_json_roundtrip():
    alert = make_valid_alert()
    json_str = alert.model_dump_json()
    restored = AlertEvent.model_validate_json(json_str)
    assert restored.alert_id == alert.alert_id
    assert restored.severity == alert.severity
    assert restored.source_uc == alert.source_uc


def test_validator_rejects_unknown_camera():
    alert = make_valid_alert()
    known_cameras = {uuid4(), uuid4()}  # alert.camera_id not in here
    errors = AlertEventValidator.validate(alert, known_cameras)
    assert any("camera_id" in e for e in errors)


def test_validator_accepts_known_camera():
    alert = make_valid_alert()
    known_cameras = {alert.camera_id}
    errors = AlertEventValidator.validate(alert, known_cameras)
    assert errors == []