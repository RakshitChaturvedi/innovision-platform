"""
Unit & Integration tests for UC2 DetectionPipeline.
Tests multi-stage inference, deterministic verification gating,
suppression of false alarms, and alert event contract adherence.
"""
from datetime import datetime, timezone
from uuid import uuid4
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from shared.contracts.frame_event import FrameEvent
from shared.contracts.enums import FrameProvider, SourceUC, AlertSeverity
from shared.platform_client.alert_publisher import AlertPublisher
from stubs.uc2_stub.cv_engine.pipeline import DetectionPipeline, ConfirmedDetection
from stubs.uc2_stub.alert_builder import build_alert_from_detection
from stubs.uc2_stub.cv_engine.zone_engine import ZoneMatch


def test_pipeline_suppresses_unverified_spark_candidates():
    pipeline = DetectionPipeline()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # Inject an illuminated screen / ceiling lamp candidate into Stage 1 YOLO mock
    # Centered at (100, 100, 300, 300) with bright white illumination inside frame
    frame[100:300, 100:300] = 230  # bright screen

    mock_candidates = [
        {
            "detection_type": "sparks",
            "bbox": {"x1": 100, "y1": 100, "x2": 300, "y2": 300},
            "confidence": 0.88,
        }
    ]

    with patch.object(pipeline.yolo, "infer", return_value=(mock_candidates, 5.0)):
        result = pipeline.process_frame(
            camera_id="cam-001",
            frame_seq=1,
            frame_bgr=frame,
            single_frame=True,
        )

    # Since candidate is an oversized / screen ROI, it must be suppressed by Stage 2/3
    assert len(result.confirmed_detections) == 0
    assert len(result.suppressed_detections) == 1
    assert result.suppressed_detections[0]["detection_type"] == "sparks"
    reason = result.suppressed_detections[0]["reason"]
    assert any(term in reason for term in ["spark_box_too_large", "illuminated", "uniform_daylight_or_sky", "broad_light_field"])


def test_pipeline_confirms_genuine_fire():
    pipeline = DetectionPipeline()
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw fire: orange-red flame at (50, 50, 120, 120)
    frame[50:120, 50:120, 2] = 255
    frame[50:120, 50:120, 1] = 120

    mock_candidates = [
        {
            "detection_type": "fire",
            "bbox": {"x1": 50, "y1": 50, "x2": 120, "y2": 120},
            "confidence": 0.90,
        }
    ]

    with patch.object(pipeline.yolo, "infer", return_value=(mock_candidates, 5.0)):
        result = pipeline.process_frame(
            camera_id="cam-001",
            frame_seq=1,
            frame_bgr=frame,
            single_frame=True,
        )

    assert len(result.confirmed_detections) == 1
    assert result.confirmed_detections[0].detection_type == "fire"
    assert result.confirmed_detections[0].final_confidence > 0.50


def test_build_alert_from_detection_contract():
    det = ConfirmedDetection(
        detection_type="fire",
        severity=AlertSeverity.HIGH,
        final_confidence=0.88,
        bbox={"x1": 50, "y1": 50, "x2": 120, "y2": 120},
        yolo_confidence=0.90,
        verification_score=0.85,
        zone=ZoneMatch(
            zone_id="zone-01",
            zone_name="Assembly Area",
            zone_priority="HIGH",
            overlap_ratio=1.0,
            is_inside=True,
        ),
        persistence_count=3,
        verification_details={"hsv_score": 0.9},
        metadata={"model_version": "v1.0"},
    )

    cam_id = uuid4()
    src_event_id = uuid4()

    alert = build_alert_from_detection(
        camera_id=cam_id,
        source_event_id=src_event_id,
        detection_type=det.detection_type,
        severity=det.severity,
        final_confidence=det.final_confidence,
        bbox=det.bbox,
        zone_id=det.zone.zone_id,
        zone_name=det.zone.zone_name,
        verification_score=det.verification_score,
        persistence_count=det.persistence_count,
        verification_details=det.verification_details,
        detection_metadata=det.metadata,
        frame_reference="frame:test:10",
        frame_provider=FrameProvider.REDIS,
    )

    assert alert.camera_id == cam_id
    assert alert.source_event_id == src_event_id
    assert alert.source_uc == SourceUC.UC2
    assert alert.alert_type == "fire_detected"
    assert alert.severity == AlertSeverity.HIGH
    assert alert.metadata["confidence"] == 0.88
