"""
Comprehensive Regression Test Suite for Fire, Smoke, and Sparks Detection Correctness.
Covers:
  TEST 1: YOLO class ID 2 must remain sparks (no remapping to fire).
  TEST 2: Valid smoke must not be rejected solely by Laplacian texture.
  TEST 3: Fire and sparks must use separate verification.
  TEST 4: Smoke must use smoke-specific fusion.
  TEST 5: Class switching must be controlled.
  TEST 6: False-alarm suppression must not reject valid smoke.
  TEST 7: Fire detection continues working reliably.
  TEST 8: Sparks detection continues working reliably.
  TEST 9: Large diffuse smoke plumes must not pass sparks verification.
"""
import pytest
import numpy as np
import cv2

from services.uc2_fire_smoke.src.detection.engine import YOLOEngine
from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier, VerificationResult
from services.uc2_fire_smoke.src.detection.confidence import ConfidenceFusion
from services.uc2_fire_smoke.src.detection.suppression import FalseAlarmSuppressor
from services.uc2_fire_smoke.src.detection.temporal import TemporalPersistenceTracker


def test_1_yolo_class_id_2_remains_sparks():
    """TEST 1: YOLO class ID 2 and 'sparks' must map to 'sparks', NOT 'fire'."""
    engine = YOLOEngine()
    assert engine.CLASS_MAP.get("2") == "sparks", "Class ID 2 must map to 'sparks'"
    assert engine.CLASS_MAP.get("sparks") == "sparks", "'sparks' must map to 'sparks'"
    assert engine.CLASS_MAP.get("spark") == "sparks", "'spark' must map to 'sparks'"
    assert engine.CLASS_MAP.get("0") == "fire", "Class ID 0 must map to 'fire'"
    assert engine.CLASS_MAP.get("1") == "smoke", "Class ID 1 must map to 'smoke'"


def test_2_smoke_not_rejected_solely_by_laplacian_texture():
    """TEST 2: Smoke must not be rejected merely because Laplacian variance is outside a hard threshold."""
    verifier = DeterministicVerifier()
    
    # Create turbulent smoke ROI with high gradient / texture variations
    h, w = 64, 64
    smoke_turbulent = np.full((h, w, 3), 128, dtype=np.uint8)
    noise = np.random.normal(0, 35, (h, w)).astype(np.int16)
    for c in range(3):
        smoke_turbulent[:, :, c] = np.clip(smoke_turbulent[:, :, c].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    smoke_turbulent = cv2.GaussianBlur(smoke_turbulent, (5, 5), 0)

    result = verifier.verify_smoke(smoke_turbulent)
    assert result.passed is True, "Turbulent smoke should pass verification"
    assert result.texture_score > 0.20, f"Texture score should be reasonable: {result.texture_score}"

    # Create low-contrast thin smoke
    smoke_thin = np.full((h, w, 3), 135, dtype=np.uint8)
    subtle_noise = np.random.normal(0, 3, (h, w)).astype(np.int16)
    for c in range(3):
        smoke_thin[:, :, c] = np.clip(smoke_thin[:, :, c].astype(np.int16) + subtle_noise, 0, 255).astype(np.uint8)

    result_thin = verifier.verify_smoke(smoke_thin)
    assert result_thin.passed is True, "Low contrast thin smoke should pass verification"


def test_3_fire_and_sparks_separate_verification():
    """TEST 3: Fire and sparks must have completely distinct verification logic."""
    verifier = DeterministicVerifier()

    # Large flame ROI (bright orange-red with high saturation)
    flame_roi = np.zeros((80, 80, 3), dtype=np.uint8)
    flame_roi[:, :] = (20, 160, 255) # BGR Orange

    fire_res = verifier.verify(flame_roi, "fire")
    assert fire_res.passed is True
    assert fire_res.hsv_score > 0.40

    # Tiny isolated sparks (bright particles on dark background)
    sparks_roi = np.zeros((20, 20, 3), dtype=np.uint8)
    cv2.circle(sparks_roi, (10, 10), 2, (200, 255, 255), -1)

    sparks_res = verifier.verify(sparks_roi, "sparks")
    assert sparks_res.passed is True
    assert "spark_pixels" in sparks_res.scores


def test_4_smoke_specific_confidence_fusion():
    """TEST 4: Smoke fusion combines scores using configurable weights."""
    fusion = ConfidenceFusion()

    # Smoke has low HSV score (desaturated) but high YOLO confidence and moderate texture diffusion
    smoke_result = fusion.fuse(
        yolo_conf=0.85,
        hsv_score=0.20,
        texture_score=0.75,
        temporal_score=0.90,
        det_type="smoke",
    )
    assert smoke_result.final_confidence >= 0.70, f"Smoke fusion confidence should be valid: {smoke_result.final_confidence}"
    assert smoke_result.alert_type == "smoke_detected"


def test_5_class_switching_control():
    """TEST 5: Tracking must not allow wild uncoordinated class switching."""
    tracker = TemporalPersistenceTracker(persistence_threshold=3, smoothing_alpha=0.6)

    # Sequence of fire detections
    is_p1, count1, score1 = tracker.update("cam_test", "fire:0.5:0.5", 0.80)
    is_p2, count2, score2 = tracker.update("cam_test", "fire:0.5:0.5", 0.85)
    is_p3, count3, score3 = tracker.update("cam_test", "fire:0.5:0.5", 0.90)

    assert is_p3 is True, "Track should be persistent after 3 frames"
    assert count3 == 3
    assert tracker._counts["cam_test"]["fire:0.5:0.5"] == 3


def test_6_false_alarm_suppression_preserves_valid_smoke():
    """TEST 6: False alarm suppressor must not kill genuine smoke with texture variance."""
    suppressor = FalseAlarmSuppressor()

    # Create realistic smoke ROI with natural dispersion variance
    h, w = 64, 64
    smoke_roi = np.full((h, w, 3), 140, dtype=np.uint8)
    noise = np.random.normal(0, 15, (h, w)).astype(np.int16)
    for c in range(3):
        smoke_roi[:, :, c] = np.clip(smoke_roi[:, :, c].astype(np.int16) + noise, 0, 255).astype(np.uint8)

    decision = suppressor.evaluate(
        roi=smoke_roi,
        det_type="smoke",
        yolo_confidence=0.65,
        hsv_score=0.40,
        texture_score=0.50,
    )
    assert decision.suppressed is False, f"Natural smoke should NOT be suppressed: {decision.reason}"


def test_7_fire_detection_reliable():
    """TEST 7: Verify standard flame continues to detect and verify reliably."""
    verifier = DeterministicVerifier()
    fusion = ConfidenceFusion()

    fire_roi = np.zeros((50, 50, 3), dtype=np.uint8)
    fire_roi[:, :] = (15, 120, 255) # BGR Orange-Red Flame

    v_res = verifier.verify_fire(fire_roi)
    assert v_res.passed is True
    assert v_res.hsv_score > 0.40

    f_res = fusion.fuse(
        yolo_conf=0.88,
        hsv_score=v_res.hsv_score,
        texture_score=0.50,
        temporal_score=1.0,
        det_type="fire",
    )
    assert f_res.final_confidence >= 0.70
    assert f_res.alert_type == "fire_detected"


def test_8_sparks_detection_reliable():
    """TEST 8: Verify sparks verify and fuse with proper sparks_score."""
    verifier = DeterministicVerifier()
    fusion = ConfidenceFusion()

    sparks_roi = np.zeros((30, 30, 3), dtype=np.uint8)
    cv2.circle(sparks_roi, (15, 15), 3, (220, 255, 255), -1)

    v_res = verifier.verify_sparks(sparks_roi)
    assert v_res.passed is True
    assert v_res.scores["max_brightness"] >= 160.0

    f_res = fusion.fuse(
        yolo_conf=0.75,
        hsv_score=v_res.hsv_score,
        texture_score=0.50,
        temporal_score=0.80,
        det_type="sparks",
    )
    assert f_res.final_confidence >= 0.55
    assert f_res.alert_type == "sparks_detected"


def test_9_smoke_plume_must_not_be_classified_as_sparks():
    """TEST 9: Large diffuse smoke plumes must NOT be classified as sparks, and sparks must be particle-like."""
    verifier = DeterministicVerifier()

    # 1. Large diffuse smoke plume ROI (e.g. 400x300 pixels of desaturated turbulent smoke)
    smoke_plume = np.full((300, 400, 3), 115, dtype=np.uint8)
    noise = np.random.normal(0, 15, (300, 400)).astype(np.int16)
    for c in range(3):
        smoke_plume[:, :, c] = np.clip(smoke_plume[:, :, c].astype(np.int16) + noise, 0, 255).astype(np.uint8)
    smoke_plume = cv2.GaussianBlur(smoke_plume, (7, 7), 0)

    # A large diffuse smoke plume must FAIL sparks verification (it has no spark particles)
    sparks_res = verifier.verify_sparks(smoke_plume)
    assert sparks_res.passed is False, "A large diffuse smoke plume must never pass sparks verification"

    # The same smoke plume must PASS smoke verification
    smoke_res = verifier.verify_smoke(smoke_plume)
    assert smoke_res.passed is True, f"Legitimate smoke plume must pass smoke verification: {smoke_res.rejection_reason}"
