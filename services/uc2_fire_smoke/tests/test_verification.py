"""
Tests for deterministic HSV & Texture verification algorithms.
"""
import numpy as np
import pytest

from services.uc2_fire_smoke.src.detection.verifier import DeterministicVerifier


def test_fire_hsv_verification():
    verifier = DeterministicVerifier()
    # Create synthetic red-orange fire-like ROI
    h, w = 100, 100
    fire_roi = np.zeros((h, w, 3), dtype=np.uint8)
    fire_roi[:, :, 2] = 255  # Red
    fire_roi[:, :, 1] = 120  # Green -> Orange/Yellow in BGR
    fire_roi[:, :, 0] = 0

    result = verifier.verify(fire_roi, "fire")
    assert result.hsv_score > 0.6
    assert 0.0 <= result.combined_score <= 1.0


def test_smoke_texture_verification():
    verifier = DeterministicVerifier()
    # Create smooth low-contrast gray ROI resembling smoke
    h, w = 100, 100
    smoke_roi = np.full((h, w, 3), 150, dtype=np.uint8)
    # Add subtle random texture
    noise = np.random.normal(0, 5, (h, w, 3)).astype(np.int16)
    smoke_roi = np.clip(smoke_roi + noise, 0, 255).astype(np.uint8)

    result = verifier.verify(smoke_roi, "smoke")
    assert result.hsv_score > 0.5
    assert 0.0 <= result.combined_score <= 1.0
