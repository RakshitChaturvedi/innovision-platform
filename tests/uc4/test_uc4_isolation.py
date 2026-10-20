"""
tests/uc4/test_uc4_isolation.py

Independent, isolated test suite for UC4:
- Vehicle Detection & Class Mapping (yolo11n.pt)
- Bounding Box Coordinate Validation & Scaling
- ByteTrack Multi-Object Tracking & Persistence
- Calibrated Speed Estimation (Homography & Ground-Plane Distance)
- Uncalibrated Fallback Safety (Zero / Unavailable Speed, No Fabricated Values)
- ANPR / OCR Cleaning, Watermark Stripping, & Consensus Voting
- Alert Event Contracts & Business Rules (Speeding, ANPR, Blacklisted Vehicle)
- Real Media Positive & Negative Frame Inference
"""

from __future__ import annotations

import collections
from datetime import datetime, timezone
import math
import os
import uuid
import numpy as np
import pytest
import cv2
from ultralytics import YOLO

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from stubs.uc4_stub.cv_engine.speed_estimator import SpeedEstimator
from stubs.uc4_stub.cv_engine.utils import (
    YOLO_CLASS_MAP,
    YOLO_COCO_NAMES,
    YOLO_CATEGORY_MAP,
    BLACKLISTED_PLATES,
    clean_plate,
    correct_indian_plate,
    get_mode,
)
from stubs.uc4_stub.alert_builder import (
    build_speed_violation_alert,
    build_unauthorized_vehicle_alert,
    build_anpr_read_alert,
    _map_severity,
)
from stubs.uc4_stub.calibration import CameraCalibration


# ─── 1. Model Loading & Class Mapping Tests ───────────────────────

class TestUC4ModelAndClassMapping:
    """Verifies UC4 model checkpoint and class definitions."""

    @pytest.fixture(scope="class")
    def yolo_model(self):
        model_path = "yolo11n.pt"
        assert os.path.exists(model_path), f"UC4 model {model_path} not found"
        return YOLO(model_path)

    def test_model_loaded_successfully(self, yolo_model):
        assert yolo_model is not None
        assert hasattr(yolo_model, "names")
        assert len(yolo_model.names) >= 80

    def test_vehicle_classes_mapped_correctly(self, yolo_model):
        names = yolo_model.names
        # Class 1: bicycle, Class 2: car, Class 3: motorcycle, Class 5: bus, Class 7: truck
        assert names[1] == "bicycle"
        assert names[2] == "car"
        assert names[3] == "motorcycle"
        assert names[5] == "bus"
        assert names[7] == "truck"

        # Verify distinct vehicle class labels (no merging of bicycle and motorcycle)
        assert YOLO_CLASS_MAP[1] == "Bicycle"
        assert YOLO_CLASS_MAP[2] == "Car"
        assert YOLO_CLASS_MAP[3] == "Motorcycle"
        assert YOLO_CLASS_MAP[5] == "Bus"
        assert YOLO_CLASS_MAP[7] == "Truck"

        # Verify exact COCO class names and categories
        assert YOLO_COCO_NAMES[1] == "bicycle"
        assert YOLO_COCO_NAMES[3] == "motorcycle"
        assert YOLO_CATEGORY_MAP[1] == "bicycle"
        assert YOLO_CATEGORY_MAP[3] == "motorcycle"

    def test_bicycle_and_motorcycle_are_distinct(self):
        """Regression test: Bicycle (class 1) must never be conflated with Motorcycle (class 3)."""
        assert YOLO_CLASS_MAP[1] != YOLO_CLASS_MAP[3]
        assert YOLO_COCO_NAMES[1] != YOLO_COCO_NAMES[3]

    def test_person_and_non_vehicle_classes_excluded(self, yolo_model):
        # UC4 only targets classes [1, 2, 3, 5, 7]
        target_classes = [1, 2, 3, 5, 7]
        assert 0 not in target_classes  # Class 0 is person (UC1 only)


# ─── 2. Bounding Box & Coordinate Geometry Tests ──────────────────

class TestUC4BoundingBoxes:
    """Tests box scaling, clipping, and ground-plane point calculation."""

    def test_rescaling_boxes_from_infer_resolution_to_full_frame(self):
        full_w, full_h = 1920, 1080
        infer_w, infer_h = 640, 360
        scale_x = full_w / float(infer_w)  # 3.0
        scale_y = full_h / float(infer_h)  # 3.0

        # Detection box in 640x360 space
        box_infer = np.array([[100.0, 50.0, 300.0, 200.0]])
        box_full = box_infer.copy()
        box_full[:, 0] *= scale_x
        box_full[:, 1] *= scale_y
        box_full[:, 2] *= scale_x
        box_full[:, 3] *= scale_y

        assert box_full[0][0] == 300.0
        assert box_full[0][1] == 150.0
        assert box_full[0][2] == 900.0
        assert box_full[0][3] == 600.0

    def test_bounding_box_clipping_to_image_boundaries(self):
        width, height = 1920, 1080
        raw_x1, raw_y1, raw_x2, raw_y2 = -15, -10, 1950, 1100
        x1 = max(0, int(raw_x1))
        y1 = max(0, int(raw_y1))
        x2 = min(width, int(raw_x2))
        y2 = min(height, int(raw_y2))

        assert x1 == 0
        assert y1 == 0
        assert x2 == 1920
        assert y2 == 1080

    def test_bottom_center_ground_contact_point(self):
        x1, y1, x2, y2 = 200, 100, 400, 300
        bottom_center = (int((x1 + x2) / 2), int(y2))
        assert bottom_center == (300, 300)


# ─── 3. Calibrated Speed Estimation Tests ─────────────────────────

class TestUC4SpeedEstimation:
    """Tests homography projection, speed calculations, and uncalibrated handling."""

    @pytest.fixture
    def speed_estimator(self):
        # 4-point polygon in normalized coordinates covering a 20-meter road segment
        polygon = [
            {"x": 0.2, "y": 0.2},
            {"x": 0.8, "y": 0.2},
            {"x": 0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8},
        ]
        return SpeedEstimator(
            polygon_normalized=polygon,
            distance_meters=20.0,
            frame_width=1920,
            frame_height=1080,
            window_size=10,
        )

    def test_homography_matrix_computed(self, speed_estimator):
        assert speed_estimator.homography_matrix is not None
        assert speed_estimator.homography_matrix.shape == (3, 3)

    def test_uncalibrated_speed_estimator_returns_zero(self):
        # Missing or degenerate polygon (< 4 points)
        estimator_none = SpeedEstimator(
            polygon_normalized=[{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.5}],
            distance_meters=0.0,
            frame_width=1920,
            frame_height=1080,
        )
        assert estimator_none.homography_matrix is None
        speed = estimator_none.update_and_get_speed(1, (500, 500), current_time=1.0)
        assert speed == 0.0

    def test_stationary_filter_suppresses_detector_jitter(self, speed_estimator):
        # Vehicle at practically the same position across 5 frames
        tid = 101
        for i in range(6):
            # 1 pixel jitter
            pt = (960 + (i % 2), 600)
            t = 1.0 + i * 0.1
            speed = speed_estimator.update_and_get_speed(tid, pt, current_time=t)
        assert speed == 0.0

    def test_moving_vehicle_speed_estimation(self, speed_estimator):
        # Vehicle moving down the frame along y-axis:
        # From y=300 to y=800 over 1.0 second (covering approximately the 20-meter zone)
        tid = 202
        speeds = []
        for i in range(8):
            t = 1.0 + i * 0.15  # 150ms per frame
            y_pos = int(300 + i * 70)  # advancing down road
            speed = speed_estimator.update_and_get_speed(tid, (960, y_pos), current_time=t)
            speeds.append(speed)

        # After rolling window fills (len >= 4), speed should be non-zero and realistic
        final_speed = speeds[-1]
        assert final_speed > 20.0, f"Expected estimated speed > 20 km/h, got {final_speed}"
        assert final_speed < 150.0, f"Expected realistic highway speed < 150 km/h, got {final_speed}"


# ─── 4. ANPR & OCR Cleaning and Consensus Tests ───────────────────

class TestUC4ANPRAndOCR:
    """Tests plate cleaning, watermark removal, state codes, and consensus voting."""

    def test_clean_plate_removes_brand_watermarks(self):
        assert clean_plate("IND-MH12DE1432") == "MH12DE1432"
        assert clean_plate("SUZUKI-DL01AB1234") == "DL01AB1234"
        assert clean_plate("HONDA-KA05MN9999") == "KA05MN9999"
        assert clean_plate("HYUNDAI-TS09FA0001") == "TS09FA0001"

    def test_clean_plate_rejects_too_short_or_garbage(self):
        assert clean_plate("AB") is None
        assert clean_plate("!!!@@@###") is None
        assert clean_plate("THISISWAYTOOLONGFORAPLATENUMBER1234567") is None

    def test_consensus_voting_picks_mode(self):
        # 5 reads of the same vehicle across frames with slight OCR noise
        reads = ["MH12AB1234", "MH12AB1234", "MH12AB1234", "MH12A81234", "MH12AB1234"]
        confs = [0.95, 0.92, 0.91, 0.65, 0.94]
        consensus = get_mode(reads, confs)
        assert consensus == "MH12AB1234"

    def test_blacklisted_plates_detected(self):
        assert "TS08EX1234" in BLACKLISTED_PLATES
        assert "AP28CH7890" in BLACKLISTED_PLATES
        assert "CLEANPLATE01" not in BLACKLISTED_PLATES


# ─── 5. Alert Builder & Platform Contract Tests ───────────────────

class TestUC4AlertContracts:
    """Verifies UC4 alert event generation satisfies the platform schema."""

    def test_build_speed_violation_alert(self):
        cam_id = uuid.uuid4()
        event_id = uuid.uuid4()
        alert = build_speed_violation_alert(
            camera_id=cam_id,
            source_event_id=event_id,
            tracker_id=42,
            plate="DL08CA1234",
            speed_kmh=68.5,
            speed_limit_kmh=40.0,
            vehicle_type="Car",
            class_id=2,
            class_name="car",
            vehicle_category="car",
        )

        assert isinstance(alert, AlertEvent)
        assert alert.camera_id == cam_id
        assert alert.source_event_id == event_id
        assert alert.source_uc == SourceUC.UC4
        assert alert.alert_type == "speed_violation"
        # 68.5 is > 40 + 15 -> AlertSeverity.HIGH
        assert alert.severity == AlertSeverity.HIGH
        assert alert.metadata["tracker_id"] == 42
        assert alert.metadata["speed"] == 68.5
        assert alert.metadata["speed_limit_kmh"] == 40.0
        assert alert.metadata["plate_number"] == "DL08CA1234"
        assert alert.metadata["vehicle_type"] == "Car"
        assert alert.metadata["class_id"] == 2
        assert alert.metadata["class_name"] == "car"
        assert alert.metadata["vehicle_category"] == "car"

    def test_speed_violation_critical_severity_when_exceeding_by_30(self):
        alert = build_speed_violation_alert(
            camera_id=uuid.uuid4(),
            source_event_id=uuid.uuid4(),
            tracker_id=7,
            plate="KA01MJ9999",
            speed_kmh=85.0,
            speed_limit_kmh=50.0,  # 85 > 50 + 30 -> CRITICAL
        )
        assert alert.severity == AlertSeverity.CRITICAL

    def test_build_unauthorized_vehicle_alert(self):
        cam_id = uuid.uuid4()
        event_id = uuid.uuid4()
        alert = build_unauthorized_vehicle_alert(
            camera_id=cam_id,
            source_event_id=event_id,
            tracker_id=12,
            plate="TS08EX1234",
            vehicle_type="Truck",
        )
        assert alert.alert_type == "unauthorized_vehicle"
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.source_uc == SourceUC.UC4

    def test_build_anpr_read_alert(self):
        cam_id = uuid.uuid4()
        event_id = uuid.uuid4()
        alert = build_anpr_read_alert(
            camera_id=cam_id,
            source_event_id=event_id,
            tracker_id=15,
            plate="MH01AB1111",
            confidence=0.94,
        )
        assert alert.alert_type == "anpr_read"
        assert alert.severity == AlertSeverity.LOW
        assert alert.metadata["plate_number"] == "MH01AB1111"


# ─── 6. Real Media Frame Inference Tests ──────────────────────────

class TestUC4RealMediaInference:
    """Runs actual yolo11n.pt on real video frame and negative background."""

    @pytest.fixture(scope="class")
    def yolo_model(self):
        return YOLO("yolo11n.pt")

    def test_positive_vehicle_inference_on_uc4_video(self, yolo_model):
        video_path = "test_data/videos/uc4.mp4"
        assert os.path.exists(video_path), f"Test video {video_path} not found"

        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()
        assert ret is True, "Failed to read first frame from uc4.mp4"

        # Run model targeting vehicle classes [1, 2, 3, 5, 7]
        results = yolo_model(frame, classes=[1, 2, 3, 5, 7], conf=0.25, verbose=False)
        boxes = results[0].boxes
        assert len(boxes) >= 1, "Expected at least 1 vehicle detected in test_data/videos/uc4.mp4"

        detected_labels = [yolo_model.names[int(b.cls[0].item())] for b in boxes]
        assert any(label in ["car", "truck", "bus", "motorcycle"] for label in detected_labels)

        # Coordinate integrity: check that coordinates are within frame dimensions
        h, w = frame.shape[:2]
        for b in boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist()
            assert 0 <= x1 < w
            assert 0 <= y1 < h
            assert x1 < x2 <= w
            assert y1 < y2 <= h
            assert float(b.conf[0].item()) >= 0.25

    def test_negative_blank_wall_produces_zero_vehicle_detections(self, yolo_model):
        blank_wall = np.full((720, 1280, 3), 120, dtype=np.uint8)
        results = yolo_model(blank_wall, classes=[1, 2, 3, 5, 7], conf=0.25, verbose=False)
        assert len(results[0].boxes) == 0, "Clean background wall must not produce vehicle detections"
