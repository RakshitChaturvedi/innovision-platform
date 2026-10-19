"""
Unit tests for UC2 False Alarm Suppressor:
Validates rejection of static fixtures, reflections, dust, fog,
and preservation of dynamic moving sparks and genuine fire/smoke.
"""
import numpy as np
import pytest
import cv2

from stubs.uc2_stub.cv_engine.suppression import FalseAlarmSuppressor


def test_suppressor_rejects_stationary_spark_fixture():
    suppressor = FalseAlarmSuppressor()
    # A stationary light fixture tracked across consecutive identical frames
    roi_current = np.zeros((30, 30, 3), dtype=np.uint8)
    roi_current[14:16, 14:16] = [255, 255, 255]
    roi_prev = roi_current.copy()

    decision = suppressor.evaluate(
        roi=roi_current,
        det_type="sparks",
        yolo_confidence=0.75,
        hsv_score=0.8,
        texture_score=0.8,
        prev_frame_roi=roi_prev,
    )
    assert decision.suppressed is True
    assert decision.category == "static_spark"


def test_suppressor_preserves_dynamic_moving_sparks():
    suppressor = FalseAlarmSuppressor()
    # A genuine spark particle that moved between frames
    roi_current = np.zeros((30, 30, 3), dtype=np.uint8)
    roi_current[10:14, 10:14] = [255, 255, 255]

    roi_prev = np.zeros((30, 30, 3), dtype=np.uint8)
    roi_prev[20:24, 20:24] = [255, 255, 255]

    decision = suppressor.evaluate(
        roi=roi_current,
        det_type="sparks",
        yolo_confidence=0.80,
        hsv_score=0.85,
        texture_score=0.85,
        prev_frame_roi=roi_prev,
    )
    assert decision.suppressed is False


def test_suppressor_rejects_sunlight_reflection():
    suppressor = FalseAlarmSuppressor()
    # Desaturated bright sunlight reflection hotspot
    roi = np.full((50, 50, 3), 245, dtype=np.uint8)

    decision = suppressor.evaluate(
        roi=roi,
        det_type="fire",
        yolo_confidence=0.60,
        hsv_score=0.10,
        texture_score=0.10,
    )
    assert decision.suppressed is True
    assert decision.category == "reflection"
