"""
Unit tests for UC2 DeterministicVerifier:
Verifies fire, smoke, and sparks detection and confirms strict rejection
of false-positive sources such as ceiling lamps, computer screens/monitors,
reflective surfaces, and oversized bounding boxes.
"""
import numpy as np
import pytest
import cv2

from stubs.uc2_stub.cv_engine.verifier import DeterministicVerifier, VerificationResult


def test_fire_hsv_verification():
    verifier = DeterministicVerifier()
    # Synthetic orange-red flame
    h, w = 100, 100
    fire_roi = np.zeros((h, w, 3), dtype=np.uint8)
    fire_roi[:, :, 2] = 255  # Red
    fire_roi[:, :, 1] = 120  # Green
    fire_roi[:, :, 0] = 0

    res = verifier.verify(fire_roi, "fire")
    assert res.passed is True
    assert res.hsv_score > 0.4


def test_smoke_texture_verification():
    verifier = DeterministicVerifier()
    # Synthetic smoke: desaturated grey with subtle texture noise
    h, w = 100, 100
    smoke_roi = np.full((h, w, 3), 140, dtype=np.uint8)
    noise = np.random.normal(0, 5, (h, w, 3)).astype(np.int16)
    smoke_roi = np.clip(smoke_roi + noise, 0, 255).astype(np.uint8)

    res = verifier.verify(smoke_roi, "smoke")
    assert res.passed is True
    assert res.texture_score > 0.2


def test_sparks_genuine_particles():
    verifier = DeterministicVerifier()
    # Dark industrial background with tiny bright spark particles
    sparks_roi = np.zeros((30, 30, 3), dtype=np.uint8)
    # 2 tiny spark particles
    sparks_roi[10:12, 10:12] = [255, 255, 255]
    sparks_roi[20:22, 18:20] = [200, 240, 255]

    res = verifier.verify(sparks_roi, "sparks")
    assert res.passed is True
    assert res.scores["spark_pixels"] >= 4


def test_sparks_rejects_ceiling_lamp_fixture():
    verifier = DeterministicVerifier()
    # Simulated ceiling fluorescent / LED high-bay fixture:
    # 50x50 box containing a large bright white glowing lamp core (area > 90px)
    lamp_roi = np.zeros((50, 50, 3), dtype=np.uint8)
    # Bright desaturated white/light gray fixture
    lamp_roi[15:35, 10:40] = (240, 240, 240)

    res = verifier.verify(lamp_roi, "sparks")
    assert res.passed is False
    assert "lamp_or_light_fixture" in res.rejection_reason or "spark_box_too_large" in res.rejection_reason


def test_sparks_rejects_illuminated_screen():
    verifier = DeterministicVerifier()
    # Simulated bright computer monitor / operator display
    # 80x80 box, broad glowing area with screen content variations
    np.random.seed(42)
    screen_roi = np.full((80, 80, 3), 220, dtype=np.uint8)
    noise = np.random.normal(0, 22, (80, 80, 3)).astype(np.int16)
    screen_roi = np.clip(screen_roi + noise, 0, 255).astype(np.uint8)

    res = verifier.verify(screen_roi, "sparks")
    assert res.passed is False
    assert any(
        term in res.rejection_reason
        for term in [
            "spark_box_too_large",
            "broad_light_field",
            "illuminated_screen_or_monitor",
            "lamp_or_light_fixture",
            "uniform_daylight_or_sky",
        ]
    )


def test_sparks_rejects_oversized_box():
    verifier = DeterministicVerifier()
    # Bounding box exceeding single spark particle limits (e.g. 70x70)
    oversized_roi = np.zeros((70, 70, 3), dtype=np.uint8)
    oversized_roi[30:35, 30:35] = [255, 255, 255]

    res = verifier.verify(oversized_roi, "sparks")
    assert res.passed is False
    assert "spark_box_too_large" in res.rejection_reason


def test_sparks_rejects_reflective_surface():
    verifier = DeterministicVerifier()
    # Bounding box with reflective white box surface (area > 500, desaturated, avg_val > 120)
    np.random.seed(42)
    box_roi = np.full((30, 30, 3), 160, dtype=np.uint8)
    noise = np.random.normal(0, 20, (30, 30, 3)).astype(np.int16)
    box_roi = np.clip(box_roi + noise, 0, 255).astype(np.uint8)

    res = verifier.verify(box_roi, "sparks")
    assert res.passed is False
    assert any(
        term in res.rejection_reason
        for term in [
            "reflective_surface_or_box",
            "spark_box_too_large",
            "uniform_daylight_or_sky",
            "low_spark_intensity",
        ]
    )
