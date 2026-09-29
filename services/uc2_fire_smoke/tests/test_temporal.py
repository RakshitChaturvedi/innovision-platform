"""
Tests for TemporalPersistenceTracker.
"""
import pytest

from services.uc2_fire_smoke.src.detection.temporal import TemporalPersistenceTracker


def test_temporal_persistence_promotion():
    tracker = TemporalPersistenceTracker(persistence_threshold=3, smoothing_alpha=0.5)
    cam_id = "test-cam"
    det_key = "fire:0.5:0.5"

    # Frame 1: not persistent yet
    is_p, count, score = tracker.update(cam_id, det_key, 0.8)
    assert not is_p
    assert count == 1

    # Frame 2: not persistent yet
    is_p, count, score = tracker.update(cam_id, det_key, 0.85)
    assert not is_p
    assert count == 2

    # Frame 3: threshold reached -> promoted
    is_p, count, score = tracker.update(cam_id, det_key, 0.9)
    assert is_p
    assert count == 3
    assert score > 0.8


def test_temporal_decay():
    tracker = TemporalPersistenceTracker(persistence_threshold=3)
    cam_id = "test-cam"
    det_key = "fire:0.2:0.2"

    tracker.update(cam_id, det_key, 0.8)
    # Decay when key is not active
    tracker.decay(cam_id, active_keys=[])
    tracker.decay(cam_id, active_keys=[])
    tracker.decay(cam_id, active_keys=[])

    # Should reset or decay count
    is_p, count, score = tracker.update(cam_id, det_key, 0.8)
    assert count == 1
