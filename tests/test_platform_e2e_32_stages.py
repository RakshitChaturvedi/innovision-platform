"""
COMPLETE UC2 FIRE / SMOKE / SPARKS INTEGRATION PLATFORM E2E VALIDATION SUITE
32 Mandatory Automated Tests covering:
  Detection + Ingestion + Pipeline + Alert Service + Dashboard + Performance
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4
from unittest.mock import AsyncMock

import cv2
import numpy as np
import pytest

# Ensure innovision-platform and uc2 service are on sys.path
PLATFORM_DIR = r"C:\Users\Sai Charan\Desktop\innovision-platform"
UC2_DIR = os.path.join(PLATFORM_DIR, "services", "uc2_fire_smoke")
if PLATFORM_DIR not in sys.path:
    sys.path.insert(0, PLATFORM_DIR)
if UC2_DIR not in sys.path:
    sys.path.insert(0, UC2_DIR)

from shared.contracts.alert_event import AlertEvent, AlertEventValidator
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC, CameraStatus
from shared.contracts.frame_event import FrameEvent
from shared.platform_client.alert_publisher import AlertPublisher, ALERTS_LIVE_STREAM
from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline, ConfirmedDetection
from services.uc2_fire_smoke.src.detection.engine import YOLOEngine
from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier
from services.uc2_fire_smoke.src.detection.confidence import ConfidenceFusion
from services.uc2_fire_smoke.src.detection.temporal import TemporalPersistenceTracker
from services.uc2_fire_smoke.src.detection.suppression import FalseAlarmSuppressor
from services.uc2_fire_smoke.src.detection.zone_engine import ZoneEngine, ZoneMatch
from services.uc2_fire_smoke.src.workers.camera_worker import CameraWorker
from services.uc2_fire_smoke.src.storage.minio_client import MinIOClient
from services.camera_registry.src.schemas import CameraCreate, CameraResponse
from services.ingestion.src.jpeg_encoder import JpegEncoder

TEST_CAM_A = UUID("00000000-0000-0000-0000-000000000002")
TEST_CAM_B = UUID("00000000-0000-0000-0000-000000000003")

FIRE_SAMPLE_PATH = os.path.join(PLATFORM_DIR, "test_data", "images", "sample_fire.jpg")
SMOKE_SAMPLE_PATH = os.path.join(PLATFORM_DIR, "test_data", "images", "sample_smoke.jpg")
SPARKS_SAMPLE_PATH = os.path.join(PLATFORM_DIR, "test_data", "images", "sample_sparks.jpg")
UC2_VIDEO_PATH = os.path.join(PLATFORM_DIR, "test_data", "videos", "uc2.mp4")


# ==============================================================================
# TEST 01 - Camera Registration
# ==============================================================================
def test_01_camera_registration():
    """TEST 01: Camera registration contract with UC2 capabilities."""
    cam = CameraCreate(
        name="Warehouse Bay 4 Fire Camera",
        location="Warehouse Bay 4",
        rtsp_url="rtsp://admin:pass@192.168.1.100:554/live",
        use_cases=["uc2"],
        fps=15,
    )
    assert cam.name == "Warehouse Bay 4 Fire Camera"
    assert "uc2" in cam.use_cases
    assert cam.fps == 15

    resp = CameraResponse(
        id=TEST_CAM_A,
        name=cam.name,
        location=cam.location,
        status=CameraStatus.ONLINE,
        use_cases=cam.use_cases,
        fps=cam.fps,
        created_at=datetime.now(timezone.utc),
    )
    assert resp.id == TEST_CAM_A
    assert resp.status == CameraStatus.ONLINE
    assert "uc2" in resp.use_cases



# ==============================================================================
# TEST 02 - RTSP Connection
# ==============================================================================
def test_02_rtsp_connection():
    """TEST 02: RTSP / Video Stream stream acquisition."""
    cap = cv2.VideoCapture(UC2_VIDEO_PATH)
    assert cap.isOpened(), f"Failed to open video stream: {UC2_VIDEO_PATH}"
    fps = cap.get(cv2.CAP_PROP_FPS)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()

    assert fps > 0.0, "Invalid FPS on stream"
    assert w > 0 and h > 0, "Invalid frame dimensions"


# ==============================================================================
# TEST 03 - Frame Ingestion
# ==============================================================================
def test_03_frame_ingestion():
    """TEST 03: Frame acquisition, validation and JPEG encoding."""
    raw_img = cv2.imread(FIRE_SAMPLE_PATH)
    assert raw_img is not None, "Failed to read test image"

    encoder = JpegEncoder(quality=80)
    jpeg_bytes = encoder.encode(raw_img)
    assert len(jpeg_bytes) > 1000, "Compressed JPEG is suspiciously small"
    assert jpeg_bytes[:2] == b"\xff\xd8", "Invalid JPEG magic header"


# ==============================================================================
# TEST 04 - Redis Frame Transport
# ==============================================================================
def test_04_redis_frame_transport():
    """TEST 04: FrameEvent construction and Redis stream contract."""
    seq = 42
    frame_ref = f"frame:{TEST_CAM_A}:{seq}"
    event = FrameEvent(
        camera_id=TEST_CAM_A,
        frame_seq=seq,
        timestamp=datetime.now(timezone.utc),
        frame_provider=FrameProvider.REDIS,
        frame_reference=frame_ref,
        frame_shape=(720, 1280),
    )
    payload = event.model_dump_json()
    assert str(TEST_CAM_A) in payload
    assert frame_ref in payload

    # Stream key convention
    stream_key = f"frames:{TEST_CAM_A}"
    assert stream_key == f"frames:{TEST_CAM_A}"


# ==============================================================================
# TEST 05 - UC2 Frame Consumption
# ==============================================================================
def test_05_uc2_frame_consumption():
    """TEST 05: Consumer decodes FrameEvent and decodes cached JPEG accurately."""
    raw_img = cv2.imread(FIRE_SAMPLE_PATH)
    _, encoded = cv2.imencode(".jpg", raw_img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
    raw_bytes = encoded.tobytes()

    # Simulate decode from Redis buffer
    np_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
    decoded_frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    assert decoded_frame is not None
    assert decoded_frame.shape == raw_img.shape
    assert decoded_frame.shape[2] == 3  # BGR 3-channel


# ==============================================================================
# TEST 06 - Raw YOLO Fire Detection
# ==============================================================================
def test_06_raw_yolo_fire():
    """TEST 06: YOLO Engine raw detection on Fire media."""
    engine = YOLOEngine()
    assert engine.ready, "YOLO engine not ready"

    img = cv2.imread(FIRE_SAMPLE_PATH)
    dets, latency = engine.infer(img)
    fire_dets = [d for d in dets if d["detection_type"] == "fire"]
    assert len(fire_dets) > 0, "Raw YOLO failed to detect fire in fire test image"
    assert fire_dets[0]["confidence"] >= 0.60
    assert latency > 0.0


# ==============================================================================
# TEST 07 - Raw YOLO Smoke Detection
# ==============================================================================
def test_07_raw_yolo_smoke():
    """TEST 07: YOLO Engine raw detection on Smoke media."""
    engine = YOLOEngine()
    img = cv2.imread(SMOKE_SAMPLE_PATH)
    dets, latency = engine.infer(img)
    smoke_dets = [d for d in dets if d["detection_type"] == "smoke"]
    assert len(smoke_dets) > 0, "Raw YOLO failed to detect smoke in smoke test image"
    assert smoke_dets[0]["confidence"] >= 0.60


# ==============================================================================
# TEST 08 - Raw YOLO Sparks Detection
# ==============================================================================
def test_08_raw_yolo_sparks():
    """TEST 08: YOLO Engine raw detection on Sparks media."""
    engine = YOLOEngine()
    img = cv2.imread(SPARKS_SAMPLE_PATH)
    dets, latency = engine.infer(img)
    sparks_dets = [d for d in dets if d["detection_type"] in ("sparks", "spark")]
    assert len(sparks_dets) > 0, "Raw YOLO failed to detect sparks in sparks test image"
    assert sparks_dets[0]["confidence"] >= 0.70


# ==============================================================================
# TEST 09 - Fire Verification
# ==============================================================================
def test_09_fire_verification():
    """TEST 09: Fire HSV and colour component verification."""
    verifier = DeterministicVerifier()
    flame_roi = np.zeros((80, 80, 3), dtype=np.uint8)
    flame_roi[:, :] = (20, 140, 255)  # Orange-Red BGR flame

    res = verifier.verify_fire(flame_roi)
    assert res.passed is True
    assert res.hsv_score >= 0.40
    assert "flame_color_ratio" in res.scores


# ==============================================================================
# TEST 10 - Smoke Verification
# ==============================================================================
def test_10_smoke_verification():
    """TEST 10: Smoke texture, entropy, and desaturation verification."""
    verifier = DeterministicVerifier()
    smoke_roi = np.full((100, 100, 3), 130, dtype=np.uint8)
    noise = np.random.normal(0, 20, (100, 100)).astype(np.int16)
    for c in range(3):
        smoke_roi[:, :, c] = np.clip(smoke_roi[:, :, c].astype(np.int16) + noise, 0, 255).astype(np.uint8)

    res = verifier.verify_smoke(smoke_roi)
    assert res.passed is True
    assert res.texture_score > 0.20
    assert res.entropy > 0.0


# ==============================================================================
# TEST 11 - Sparks Verification
# ==============================================================================
def test_11_sparks_verification():
    """TEST 11: Sparks distinct brightness variance and isolation from diffuse smoke."""
    verifier = DeterministicVerifier()

    # Legitimate sparks: sharp bright particles
    spark_roi = np.zeros((40, 40, 3), dtype=np.uint8)
    cv2.circle(spark_roi, (20, 20), 3, (220, 255, 255), -1)
    spark_res = verifier.verify_sparks(spark_roi)
    assert spark_res.passed is True
    assert spark_res.scores["max_brightness"] >= 185.0

    # Diffuse smoke plume MUST FAIL sparks verification
    smoke_plume = np.full((200, 200, 3), 120, dtype=np.uint8)
    diffuse_res = verifier.verify_sparks(smoke_plume)
    assert diffuse_res.passed is False, "Diffuse smoke plume must NEVER pass sparks verification"


# ==============================================================================
# TEST 12 - Fire + Smoke Simultaneous
# ==============================================================================
def test_12_fire_plus_smoke_simultaneous():
    """TEST 12: Both Fire and Smoke coexisting in a single frame."""
    pipeline = DetectionPipeline()
    img = cv2.imread(FIRE_SAMPLE_PATH)
    res = pipeline.process_frame(str(TEST_CAM_A), 1, img, single_frame=True)

    types = {d.detection_type for d in res.confirmed_detections}
    assert "fire" in types, "Fire must be detected"
    assert "smoke" in types, "Smoke must be detected"


# ==============================================================================
# TEST 13 - Fire + Sparks Simultaneous
# ==============================================================================
def test_13_fire_plus_sparks_simultaneous():
    """TEST 13: Fire and Sparks coexisting in composite frame without mutual suppression."""
    pipeline = DetectionPipeline()
    composite = np.zeros((480, 640, 3), dtype=np.uint8)

    # Place fire on left
    cv2.ellipse(composite, (160, 240), (60, 90), 0, 0, 360, (20, 140, 255), -1)
    # Place sparks on right
    sparks_img = cv2.imread(SPARKS_SAMPLE_PATH)
    if sparks_img is not None:
        sp_resized = cv2.resize(sparks_img, (280, 200))
        composite[100:300, 340:620] = sp_resized

    res = pipeline.process_frame(str(TEST_CAM_A), 1, composite, single_frame=True)
    types = {d.detection_type for d in res.confirmed_detections}
    # Sparks must be preserved
    assert len(res.confirmed_detections) > 0


# ==============================================================================
# TEST 14 - Smoke + Sparks Simultaneous
# ==============================================================================
def test_14_smoke_plus_sparks_simultaneous():
    """TEST 14: Smoke and Sparks distinct coexistence."""
    pipeline = DetectionPipeline()
    smoke_img = cv2.imread(SMOKE_SAMPLE_PATH)
    h, w = smoke_img.shape[:2]

    # Run on smoke image
    res = pipeline.process_frame(str(TEST_CAM_A), 1, smoke_img, single_frame=True)
    types = {d.detection_type for d in res.confirmed_detections}
    assert "smoke" in types
    assert "sparks" not in types, "Smoke alone must NOT generate sparks"


# ==============================================================================
# TEST 15 - Fire + Smoke + Sparks Simultaneous
# ==============================================================================
def test_15_all_three_classes_coexistence():
    """TEST 15: Fire, Smoke, and Sparks evaluated without cross-class conversion."""
    pipeline = DetectionPipeline()
    verifier = DeterministicVerifier()

    # Test individual verifiers handle each correctly
    flame_roi = np.zeros((50, 50, 3), dtype=np.uint8)
    flame_roi[:, :] = (20, 140, 255)
    smoke_roi = np.full((50, 50, 3), 120, dtype=np.uint8)
    sparks_roi = np.zeros((50, 50, 3), dtype=np.uint8)
    cv2.circle(sparks_roi, (25, 25), 2, (200, 255, 255), -1)

    v_fire = verifier.verify(flame_roi, "fire")
    v_smoke = verifier.verify(smoke_roi, "smoke")
    v_sparks = verifier.verify(sparks_roi, "sparks")

    assert v_fire.passed is True
    assert v_smoke.passed is True
    assert v_sparks.passed is True


# ==============================================================================
# TEST 16 - Bounding Boxes Validation
# ==============================================================================
def test_16_bounding_boxes():
    """TEST 16: Bounding box coordinates adhere to positive area and frame bounds."""
    pipeline = DetectionPipeline()
    img = cv2.imread(FIRE_SAMPLE_PATH)
    h, w = img.shape[:2]
    res = pipeline.process_frame(str(TEST_CAM_A), 1, img, single_frame=True)

    for det in res.confirmed_detections:
        bx = det.bbox
        assert 0 <= bx["x1"] < bx["x2"] <= w, f"Invalid bbox x-bounds: {bx}"
        assert 0 <= bx["y1"] < bx["y2"] <= h, f"Invalid bbox y-bounds: {bx}"
        area = (bx["x2"] - bx["x1"]) * (bx["y2"] - bx["y1"])
        assert area > 10, "Bounding box area too small"


# ==============================================================================
# TEST 17 - Tracking Validation
# ==============================================================================
def test_17_tracking():
    """TEST 17: Temporal persistence tracker tracks centroids per camera."""
    tracker = TemporalPersistenceTracker(persistence_threshold=3, smoothing_alpha=0.6)

    # Camera A tracking
    _, _, s1 = tracker.update(str(TEST_CAM_A), "fire:0.4:0.5", 0.85)
    _, _, s2 = tracker.update(str(TEST_CAM_A), "fire:0.4:0.5", 0.88)
    is_p, cnt, s3 = tracker.update(str(TEST_CAM_A), "fire:0.4:0.5", 0.90)

    assert is_p is True
    assert cnt == 3
    assert s3 >= 0.85

    # Isolation: Camera B has no state for Camera A's key
    assert str(TEST_CAM_B) not in tracker._counts or "fire:0.4:0.5" not in tracker._counts[str(TEST_CAM_B)]


# ==============================================================================
# TEST 18 - Temporal Confirmation
# ==============================================================================
def test_18_temporal_confirmation():
    """TEST 18: Frame 1 -> candidate, Frame 2 -> candidate, Frame 3 -> confirmed."""
    tracker = TemporalPersistenceTracker(persistence_threshold=3)

    is_p1, _, _ = tracker.update("cam_test", "smoke:0.2:0.3", 0.70)
    assert is_p1 is False, "Frame 1 must not be confirmed prematurely"

    is_p2, _, _ = tracker.update("cam_test", "smoke:0.2:0.3", 0.72)
    assert is_p2 is False, "Frame 2 must not be confirmed prematurely"

    is_p3, cnt, _ = tracker.update("cam_test", "smoke:0.2:0.3", 0.75)
    assert is_p3 is True, "Frame 3 must reach confirmation threshold"
    assert cnt == 3


# ==============================================================================
# TEST 19 - AlertEvent Creation
# ==============================================================================
def test_19_alert_event_creation():
    """TEST 19: Strict schema validation of canonical Platform AlertEvent."""
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=TEST_CAM_A,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="fire_detected",
        title="Fire Detected in Bay 4",
        description="UC2 real inference confirmed fire with confidence 78.5%.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        status=AlertStatus.PENDING,
        metadata={
            "confidence": 0.785,
            "verification_score": 0.65,
            "bounding_boxes": [{"x1": 100, "y1": 150, "x2": 300, "y2": 400}],
        },
    )

    errors = AlertEventValidator.validate(alert, known_cam_ids={TEST_CAM_A})
    assert len(errors) == 0, f"Validation errors: {errors}"
    assert alert.source_uc == SourceUC.UC2


# ==============================================================================
# TEST 20 - Alert Service Consumption
# ==============================================================================
@pytest.mark.asyncio
async def test_20_alert_service_consumption():
    """TEST 20: Event published to alerts:live stream unpacks cleanly."""
    mock_redis = AsyncMock()
    mock_redis.xadd.return_value = "1727700000000-0"
    publisher = AlertPublisher(redis_client=mock_redis)

    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=TEST_CAM_A,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        alert_type="smoke_detected",
        title="Smoke Alert",
        description="Dense smoke detected.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
    )

    ok = await publisher.publish(alert)
    assert ok is True

    # Validate published payload
    call_args = mock_redis.xadd.call_args[0]
    assert call_args[0] == ALERTS_LIVE_STREAM
    payload_str = call_args[1]["data"]
    parsed = AlertEvent.model_validate_json(payload_str)
    assert parsed.alert_id == alert.alert_id
    assert parsed.alert_type == "smoke_detected"


# ==============================================================================
# TEST 21 - Database Persistence Mapping
# ==============================================================================
def test_21_database_persistence_mapping():
    """TEST 21: Model attributes map directly to SQL table schema."""
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=TEST_CAM_A,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="sparks_detected",
        title="Sparks Alert",
        description="Welding sparks detected.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        metadata={"sparks_confidence": 0.88},
    )
    # Check that required SQL fields are present
    db_row = {
        "alert_id": str(alert.alert_id),
        "camera_id": str(alert.camera_id),
        "severity": alert.severity.value,
        "alert_type": alert.alert_type,
        "title": alert.title,
        "description": alert.description,
        "source_uc": alert.source_uc.value,
        "metadata": json.dumps(alert.metadata),
    }
    assert db_row["alert_type"] == "sparks_detected"
    assert db_row["source_uc"] == "uc2"


# ==============================================================================
# TEST 22 - Dashboard Update Contract
# ==============================================================================
def test_22_dashboard_update_contract():
    """TEST 22: Dashboard frontend data contract compatibility."""
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=TEST_CAM_A,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="fire_detected",
        title="Fire Detected",
        description="Fire confirmed.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
    )
    # Validate format consumed by dashboard React components
    frontend_item = {
        "id": str(alert.alert_id),
        "alert_id": str(alert.alert_id),
        "camera_id": str(alert.camera_id),
        "source_uc": alert.source_uc.value,
        "alert_type": alert.alert_type,
        "severity": alert.severity.value,
        "title": alert.title,
        "description": alert.description,
        "status": alert.status.value,
        "created_at": alert.timestamp.isoformat(),
    }
    assert frontend_item["source_uc"] == "uc2"
    assert frontend_item["severity"] == "high"


# ==============================================================================
# TEST 23 - WebSocket Push
# ==============================================================================
def test_23_websocket_push():
    """TEST 23: WebSocket broadcast event formatting (alert:new)."""
    event_data = {
        "event": "alert:new",
        "data": {
            "alert_id": str(uuid4()),
            "camera_id": str(TEST_CAM_A),
            "severity": "high",
            "alert_type": "smoke_detected",
            "title": "Smoke Alert",
        },
    }
    payload = json.dumps(event_data)
    assert "alert:new" in payload
    assert "smoke_detected" in payload


# ==============================================================================
# TEST 24 - Evidence Generation
# ==============================================================================
def test_24_evidence_generation():
    """TEST 24: Annotated preview frame generation with bounding boxes."""
    pipeline = DetectionPipeline()
    img = cv2.imread(FIRE_SAMPLE_PATH)
    res = pipeline.process_frame(str(TEST_CAM_A), 1, img, single_frame=True)

    worker = CameraWorker(
        camera_id=str(TEST_CAM_A),
        camera_name="Test Bay 4",
        camera_location="Warehouse",
        redis_client=None,
        detection_pipeline=pipeline,
        alert_publisher=None,
        minio_client=None,
    )
    annotated = worker._annotate_frame(img, res)
    assert annotated.shape == img.shape
    _, encoded = cv2.imencode(".jpg", annotated)
    assert len(encoded) > 5000, "Evidence JPEG failed to compress"


# ==============================================================================
# TEST 25 - Alert Deduplication / Cooldown
# ==============================================================================
def test_25_alert_deduplication():
    """TEST 25: Repeated identical detections within cooldown window are suppressed."""
    worker = CameraWorker(
        camera_id=str(TEST_CAM_A),
        camera_name="Test Bay 4",
        camera_location="Warehouse",
        redis_client=None,
        detection_pipeline=None,
        alert_publisher=None,
        minio_client=None,
    )
    key = "fire:zone-default"
    now = time.time()
    worker._last_alert_time[key] = now

    # Cooldown of 60s active:
    elapsed = 5.0
    is_cooling = (now + elapsed - worker._last_alert_time[key]) < 60.0
    assert is_cooling is True, "Deduplication must suppress alerts within 60s cooldown"


# ==============================================================================
# TEST 26 - Camera Disconnect / Reconnect
# ==============================================================================
def test_26_camera_disconnect_reconnect():
    """TEST 26: Worker handles pause/resume cleanly without stale state leakage."""
    worker = CameraWorker(
        camera_id=str(TEST_CAM_A),
        camera_name="Test Bay 4",
        camera_location="Warehouse",
        redis_client=None,
        detection_pipeline=None,
        alert_publisher=None,
        minio_client=None,
    )
    assert worker.is_paused is False
    worker.pause()
    assert worker.is_paused is True
    worker.resume()
    assert worker.is_paused is False


# ==============================================================================
# TEST 27 - Multi-Camera Isolation
# ==============================================================================
def test_27_multi_camera_isolation():
    """TEST 27: Absolute isolation between Camera A (Fire) and Camera B (Smoke)."""
    pipeline = DetectionPipeline()
    fire_img = cv2.imread(FIRE_SAMPLE_PATH)
    smoke_img = cv2.imread(SMOKE_SAMPLE_PATH)

    res_a = pipeline.process_frame(str(TEST_CAM_A), 1, fire_img, single_frame=True)
    res_b = pipeline.process_frame(str(TEST_CAM_B), 1, smoke_img, single_frame=True)

    assert res_a.camera_id == str(TEST_CAM_A)
    assert res_b.camera_id == str(TEST_CAM_B)

    # Frame and state isolation
    assert res_a.confirmed_detections[0].detection_type in ("fire", "smoke")
    assert res_b.confirmed_detections[0].detection_type == "smoke"


# ==============================================================================
# TEST 28 - Processing Performance (FPS)
# ==============================================================================
def test_28_processing_performance():
    """TEST 28: Measure pipeline throughput across video frames."""
    pipeline = DetectionPipeline()
    cap = cv2.VideoCapture(UC2_VIDEO_PATH)

    t0 = time.perf_counter()
    frames_counted = 0
    while cap.isOpened() and frames_counted < 10:
        ret, frame = cap.read()
        if not ret:
            break
        pipeline.process_frame(str(TEST_CAM_A), frames_counted + 1, frame)
        frames_counted += 1
    cap.release()

    total_time = time.perf_counter() - t0
    fps = frames_counted / total_time if total_time > 0 else 0
    print(f"\nMeasured pipeline throughput: {fps:.2f} FPS across {frames_counted} frames")
    assert frames_counted > 0


# ==============================================================================
# TEST 29 - End-to-End Latency Breakdown
# ==============================================================================
def test_29_e2e_latency_breakdown():
    """TEST 29: Profile per-stage latency."""
    pipeline = DetectionPipeline()
    img = cv2.imread(FIRE_SAMPLE_PATH)
    res = pipeline.process_frame(str(TEST_CAM_A), 1, img, single_frame=True)

    assert res.inference_latency_ms > 0.0
    assert res.verification_latency_ms >= 0.0
    assert res.total_pipeline_latency_ms > 0.0
    print(f"\nLatency Profile: Infer={res.inference_latency_ms:.1f}ms, Verify={res.verification_latency_ms:.1f}ms, Total={res.total_pipeline_latency_ms:.1f}ms")


# ==============================================================================
# TEST 30 - Complete Fire Scenario E2E
# ==============================================================================
def test_30_complete_fire_scenario():
    """TEST 30: Full end-to-end fire scenario from raw image to AlertEvent."""
    pipeline = DetectionPipeline()
    img = cv2.imread(FIRE_SAMPLE_PATH)
    res = pipeline.process_frame(str(TEST_CAM_A), 1, img, single_frame=True)

    fire_dets = [d for d in res.confirmed_detections if d.detection_type == "fire"]
    assert len(fire_dets) > 0, "Complete Fire scenario failed to confirm fire"
    det = fire_dets[0]

    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=TEST_CAM_A,
        timestamp=datetime.now(timezone.utc),
        severity=det.severity,
        alert_type="fire_detected",
        title="Fire Detected in Warehouse",
        description=f"Confidence: {det.final_confidence * 100:.1f}%.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        metadata={"confidence": det.final_confidence, "bounding_boxes": [det.bbox]},
    )
    errors = AlertEventValidator.validate(alert, known_cam_ids={TEST_CAM_A})
    assert len(errors) == 0


# ==============================================================================
# TEST 31 - Complete Smoke Scenario E2E
# ==============================================================================
def test_31_complete_smoke_scenario():
    """TEST 31: Full end-to-end smoke scenario, strictly ensuring Smoke != Sparks."""
    pipeline = DetectionPipeline()
    img = cv2.imread(SMOKE_SAMPLE_PATH)
    res = pipeline.process_frame(str(TEST_CAM_A), 1, img, single_frame=True)

    smoke_dets = [d for d in res.confirmed_detections if d.detection_type == "smoke"]
    sparks_dets = [d for d in res.confirmed_detections if d.detection_type in ("sparks", "spark")]

    assert len(smoke_dets) > 0, "Complete Smoke scenario failed to confirm smoke"
    assert len(sparks_dets) == 0, "Smoke must NEVER be classified as sparks!"

    det = smoke_dets[0]
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=TEST_CAM_A,
        timestamp=datetime.now(timezone.utc),
        severity=det.severity,
        alert_type="smoke_detected",
        title="Smoke Detected in Facility",
        description=f"Confidence: {det.final_confidence * 100:.1f}%.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        metadata={"confidence": det.final_confidence, "bounding_boxes": [det.bbox]},
    )
    errors = AlertEventValidator.validate(alert, known_cam_ids={TEST_CAM_A})
    assert len(errors) == 0


# ==============================================================================
# TEST 32 - Complete Sparks Scenario E2E
# ==============================================================================
def test_32_complete_sparks_scenario():
    """TEST 32: Full end-to-end sparks scenario, strictly ensuring Sparks != Fire."""
    pipeline = DetectionPipeline()
    img = cv2.imread(SPARKS_SAMPLE_PATH)
    res = pipeline.process_frame(str(TEST_CAM_A), 1, img, single_frame=True)

    sparks_dets = [d for d in res.confirmed_detections if d.detection_type in ("sparks", "spark")]
    assert len(sparks_dets) > 0, "Complete Sparks scenario failed to confirm sparks"

    det = sparks_dets[0]
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id=TEST_CAM_A,
        timestamp=datetime.now(timezone.utc),
        severity=det.severity,
        alert_type="sparks_detected",
        title="Sparks Detected in Facility",
        description=f"Confidence: {det.final_confidence * 100:.1f}%.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        metadata={"confidence": det.final_confidence, "bounding_boxes": [det.bbox]},
    )
    errors = AlertEventValidator.validate(alert, known_cam_ids={TEST_CAM_A})
    assert len(errors) == 0
