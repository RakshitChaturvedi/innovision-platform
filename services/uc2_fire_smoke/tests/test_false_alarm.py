"""
Tests for FalseAlarmSuppressor and ZoneEngine.
"""
import numpy as np
import pytest

from services.uc2_fire_smoke.src.detection.suppression import FalseAlarmSuppressor
from services.uc2_fire_smoke.src.detection.zone_engine import ZoneDefinition, ZoneEngine


def test_false_alarm_sunlight_suppression():
    suppressor = FalseAlarmSuppressor()
    # Pure white over-exposed ROI (sunlight flare)
    flare_roi = np.full((50, 50, 3), 255, dtype=np.uint8)

    decision = suppressor.evaluate(
        roi=flare_roi,
        det_type="fire",
        yolo_confidence=0.4,
        hsv_score=0.1,
        texture_score=0.1,
    )
    assert decision.suppressed
    assert decision.reason is not None


def test_zone_engine_containment():
    zone_engine = ZoneEngine()
    # Setup camera with a zone covering the top-left quadrant (0.0, 0.0) to (0.5, 0.5)
    zone = ZoneDefinition(
        zone_id="storage-zone-1",
        zone_name="Storage Area",
        priority="CRITICAL",
        polygon=[(0.0, 0.0), (0.5, 0.0), (0.5, 0.5), (0.0, 0.5)],
    )
    zone_engine.set_camera_zones("cam-001", [zone])

    # Test bbox in top-left
    match = zone_engine.filter_and_assign_zones(
        camera_id="cam-001",
        bbox=(50, 50, 200, 200),
        frame_shape=(1080, 1920),
        detection_class="fire",
    )
    assert match is not None
    assert match.zone_id == "storage-zone-1"
    assert match.zone_priority == "CRITICAL"
