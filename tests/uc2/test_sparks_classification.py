"""
Comprehensive regression and validation suite for UC2 Fire, Smoke & Sparks classification:
- Primary Fire Detection: Confirms genuine flames using trained model and HSV verification.
- Primary Smoke Detection: Confirms genuine smoke (including smoke without visible flames).
- Secondary Sparks Detection: Confirms genuine flying sparks or particle showers.
- False Positive Rejection: Rejects small lights, LED indicators, light reflections, glare, and bright spots.
- Class Separation: Preserves strict distinction between fire, smoke, and sparks.
"""
from unittest.mock import patch
import cv2
import numpy as np
import pytest

from stubs.uc2_stub.cv_engine.pipeline import DetectionPipeline
from stubs.uc2_stub.cv_engine.verifier import DeterministicVerifier
from stubs.uc2_stub.cv_engine.suppression import FalseAlarmSuppressor


@pytest.fixture
def pipeline():
    return DetectionPipeline()


@pytest.fixture
def verifier():
    return DeterministicVerifier()


@pytest.fixture
def suppressor():
    return FalseAlarmSuppressor()


# ── 1. Primary Fire Detection ──────────────────────────────────────────────────

def test_primary_fire_detected_and_confirmed(pipeline):
    """Actual flames must be detected as FIRE with high confidence."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Orange-red flame core
    frame[50:120, 50:120, 2] = 255  # Red
    frame[50:120, 50:120, 1] = 120  # Green
    frame[50:120, 50:120, 0] = 10

    mock_candidates = [
        {
            "detection_type": "fire",
            "bbox": {"x1": 50, "y1": 50, "x2": 120, "y2": 120},
            "confidence": 0.88,
        }
    ]

    with patch.object(pipeline.yolo, "infer", return_value=(mock_candidates, 5.0)):
        result = pipeline.process_frame("cam-test", 1, frame, single_frame=True)

    assert result.has_detections is True
    assert len(result.confirmed_detections) == 1
    det = result.confirmed_detections[0]
    assert det.detection_type == "fire"
    assert det.final_confidence >= 0.50


# ── 2. Primary Smoke Detection (Smoke without Visible Flames) ──────────────────

def test_primary_smoke_detected_and_confirmed(pipeline):
    """Actual smoke (without visible flames) must be detected as SMOKE."""
    frame = np.full((480, 640, 3), 100, dtype=np.uint8)
    # Diffuse, desaturated smoke cloud
    np.random.seed(42)
    smoke_patch = np.full((120, 120, 3), 135, dtype=np.uint8)
    noise = np.random.normal(0, 15, (120, 120, 3)).astype(np.int16)
    frame[100:220, 100:220] = np.clip(smoke_patch + noise, 0, 255).astype(np.uint8)

    mock_candidates = [
        {
            "detection_type": "smoke",
            "bbox": {"x1": 100, "y1": 100, "x2": 220, "y2": 220},
            "confidence": 0.82,
        }
    ]

    with patch.object(pipeline.yolo, "infer", return_value=(mock_candidates, 5.0)):
        result = pipeline.process_frame("cam-test", 1, frame, single_frame=True)

    assert result.has_detections is True
    assert len(result.confirmed_detections) == 1
    det = result.confirmed_detections[0]
    assert det.detection_type == "smoke"
    assert det.final_confidence >= 0.45


# ── 3. Secondary Sparks: Confirms Genuine Flying Particles / Showers ──────────

def test_genuine_spark_shower_confirmed(verifier):
    """Genuine multi-particle spark shower on dark background passes verification."""
    roi = np.zeros((40, 40, 3), dtype=np.uint8)
    # 4 distinct tiny incandescent particles
    roi[8:10, 8:10] = [240, 250, 255]
    roi[15:17, 22:24] = [200, 230, 255]
    roi[28:30, 12:14] = [210, 240, 255]
    roi[32:34, 30:32] = [255, 255, 255]

    res = verifier.verify(roi, "sparks")
    assert res.passed is True
    assert res.hsv_score > 0.50


def test_genuine_spark_streak_confirmed(verifier):
    """High-velocity elongated flying spark streak passes verification."""
    roi = np.zeros((30, 30, 3), dtype=np.uint8)
    # Flying spark streak: 2x12 pixels (aspect ratio 6:1)
    roi[14:16, 8:20] = [220, 245, 255]

    res = verifier.verify(roi, "sparks")
    assert res.passed is True


# ── 4. False Positive Rejection: Small Lights, LEDs & Reflections ─────────────

def test_rejects_small_round_led_indicator(verifier, suppressor):
    """Round LED indicator or small light bulb must be rejected as sparks."""
    roi = np.zeros((30, 30, 3), dtype=np.uint8)
    # Round bright spot (radius 4 circle, area ~50 px)
    cv2.circle(roi, (15, 15), 4, (255, 255, 255), -1)

    # 1. Verifier rejection
    res = verifier.verify(roi, "sparks")
    assert res.passed is False
    assert "isolated_light_or_led" in res.rejection_reason or "lamp_or_light_fixture" in res.rejection_reason

    # 2. Suppressor rejection
    dec = suppressor.evaluate(roi, "sparks", yolo_confidence=0.75, hsv_score=0.8, texture_score=0.8)
    assert dec.suppressed is True
    assert dec.category in ("small_light", "led", "reflection")


def test_rejects_specular_surface_reflection(verifier, suppressor):
    """Light reflection on shiny floor or metal must be rejected as sparks."""
    roi = np.full((35, 35, 3), 130, dtype=np.uint8)
    # Desaturated bright reflection streak / pool on floor
    roi[10:25, 5:30] = [235, 235, 235]

    res = verifier.verify(roi, "sparks")
    assert res.passed is False
    assert any(term in res.rejection_reason for term in ["reflective_surface_or_box", "lamp_or_light_fixture", "spark_box_too_large"])

    dec = suppressor.evaluate(roi, "sparks", yolo_confidence=0.70, hsv_score=0.7, texture_score=0.7)
    assert dec.suppressed is True
    assert dec.category in ("specular_reflection", "reflection", "small_light")


def test_rejects_isolated_bright_pixel_noise(verifier):
    """Single noisy pixel or faint point without sufficient particles must be rejected."""
    roi = np.zeros((30, 30, 3), dtype=np.uint8)
    roi[15, 15] = [255, 255, 255]  # only 1 pixel

    res = verifier.verify(roi, "sparks")
    assert res.passed is False
    assert any(term in res.rejection_reason for term in ["insufficient_spark_pixels", "isolated_light", "reflective_surface_or_box"])


# ── 5. Blank Frame Handling ───────────────────────────────────────────────────

def test_blank_frame_produces_no_detections(pipeline):
    """Blank frame must produce zero confirmed or false detections."""
    blank = np.full((480, 640, 3), 128, dtype=np.uint8)
    result = pipeline.process_frame("cam-test", 1, blank, single_frame=True)
    assert result.has_detections is False
    assert len(result.confirmed_detections) == 0


# ── 6. Class Separation: Sparks Not Relabeled as Fire ─────────────────────────

def test_sparks_not_relabelled_as_fire(pipeline):
    """Sparks and fire must maintain their distinct detection types and attributes."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw tiny spark streak (2x12)
    frame[50:52, 50:62] = [220, 245, 255]

    mock_candidates = [
        {
            "detection_type": "sparks",
            "bbox": {"x1": 45, "y1": 45, "x2": 65, "y2": 65},
            "confidence": 0.80,
        }
    ]

    with patch.object(pipeline.yolo, "infer", return_value=(mock_candidates, 5.0)):
        result = pipeline.process_frame("cam-test", 1, frame, single_frame=True)

    assert len(result.confirmed_detections) == 1
    det = result.confirmed_detections[0]
    assert det.detection_type == "sparks"
    assert det.detection_type != "fire"
