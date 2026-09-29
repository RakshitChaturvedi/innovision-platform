"""
Tests for AlertEvent contract and validation.
"""
from datetime import datetime, timezone
from uuid import UUID, uuid4
import pytest

from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.contracts.alert_event import AlertEvent, AlertEventValidator


def test_alert_event_valid():
    cam_id = uuid4()
    alert = AlertEvent(
        camera_id=cam_id,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        alert_type="fire_detected",
        title="Critical Fire Detected in Sector 1",
        description="Fire detected with high confidence.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        frame_reference=f"evidence/{cam_id}/snapshot.jpg",
        frame_provider=FrameProvider.MINIO,
        metadata={"confidence": 0.95, "zone_id": "zone-1"},
    )
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.source_uc == SourceUC.UC2
    errors = AlertEventValidator.validate(alert, known_cam_ids={cam_id})
    assert len(errors) == 0


def test_alert_event_validation_errors():
    cam_unknown = uuid4()
    known_cam = uuid4()
    alert = AlertEvent(
        camera_id=cam_unknown,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="smoke_detected",
        title="   ",  # Whitespace title
        description="   ",  # Whitespace description
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
    )
    errors = AlertEventValidator.validate(alert, known_cam_ids={known_cam})
    assert len(errors) >= 3
    assert any("not registered in Camera Registry" in e for e in errors)
    assert any("title cant be whitespace only" in e for e in errors)
    assert any("description cant be whitespace only" in e for e in errors)
