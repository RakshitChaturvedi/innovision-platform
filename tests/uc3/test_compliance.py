import pytest
import time

from stubs.uc3_stub.src import compliance
from stubs.uc3_stub.src.compliance import evaluate_compliance, new_session_state, Box


def test_empty_detections_returns_ok():
    states = new_session_state()
    now = time.monotonic()
    severity, violations, worker_violations = evaluate_compliance([], states, now=now)
    assert severity == "ok"
    assert violations == []
    assert worker_violations == []


def test_compliant_person_returns_no_violations():
    states = new_session_state()
    now = time.monotonic()
    # Person with helmet and vest
    detections = [
        {"label": "person", "conf": 0.90, "box": [0.1, 0.1, 0.8, 0.9], "_track_id": 1},
        {"label": "head", "conf": 0.85, "box": [0.3, 0.1, 0.5, 0.3], "_track_id": 1},
        {"label": "helmet", "conf": 0.88, "box": [0.3, 0.08, 0.5, 0.25], "_track_id": 1},
        {"label": "safety-vest", "conf": 0.85, "box": [0.2, 0.3, 0.7, 0.7], "_track_id": 1},
    ]

    severity, violations, worker_violations = evaluate_compliance(detections, states, now=now)
    # On first frame, evidence duration requirement is not yet met so no violation raised
    assert severity == "ok"
    assert len(worker_violations) == 0


def test_temporal_sliding_window_raise_and_clear():
    states = new_session_state()
    start_time = 100.0

    # Frame 1 at t=100.0s (missing helmet)
    det1 = [
        {"label": "person", "conf": 0.90, "box": [0.1, 0.1, 0.8, 0.9], "_track_id": 1},
        {"label": "head", "conf": 0.85, "box": [0.3, 0.1, 0.5, 0.3], "_track_id": 1},
    ]
    req_ppe = frozenset({"helmet"})
    sev1, vio1, w_vio1 = evaluate_compliance(det1, states, now=start_time, required_ppe=req_ppe)
    # Cold start guard: MIN_EVIDENCE_SECONDS (1.0s) not met yet
    assert len(w_vio1) == 0

    # Frame 2 at t=100.5s (still missing helmet)
    evaluate_compliance(det1, states, now=start_time + 0.5, required_ppe=req_ppe)

    # Frame 3 at t=101.2s (missing helmet, evidence duration > 1.0s and samples >= 2)
    sev3, vio3, w_vio3 = evaluate_compliance(det1, states, now=start_time + 1.2, required_ppe=req_ppe)
    assert len(w_vio3) == 1
    assert w_vio3[0]["ppe_type"] == "helmet"
    assert w_vio3[0]["worker_id"] == 1

    # Frame 4 at t=102.0s (now worker wears helmet)
    det_compliant = [
        {"label": "person", "conf": 0.90, "box": [0.1, 0.1, 0.8, 0.9], "_track_id": 1},
        {"label": "head", "conf": 0.85, "box": [0.3, 0.1, 0.5, 0.3], "_track_id": 1},
        {"label": "helmet", "conf": 0.88, "box": [0.3, 0.08, 0.5, 0.25], "_track_id": 1},
    ]
    evaluate_compliance(det_compliant, states, now=start_time + 2.0, required_ppe=req_ppe)
    evaluate_compliance(det_compliant, states, now=start_time + 3.0, required_ppe=req_ppe)
    evaluate_compliance(det_compliant, states, now=start_time + 4.0, required_ppe=req_ppe)
    evaluate_compliance(det_compliant, states, now=start_time + 5.0, required_ppe=req_ppe)

    # Missing fraction should drop below CLEAR threshold (30%), clearing the violation
    timeline = states[1]._timeline("head")
    assert timeline.violation_active is False


def test_zone_policy_masking():
    states = new_session_state()
    now = 100.0

    # Worker has head visible, no helmet. But required_ppe only requires "vest"
    det = [
        {"label": "person", "conf": 0.90, "box": [0.1, 0.1, 0.8, 0.9], "_track_id": 1},
        {"label": "head", "conf": 0.85, "box": [0.3, 0.1, 0.5, 0.3], "_track_id": 1},
        {"label": "safety-vest", "conf": 0.85, "box": [0.2, 0.3, 0.7, 0.7], "_track_id": 1},
    ]

    required_zone_ppe = frozenset({"vest"})
    sev, vio, w_vio = evaluate_compliance(det, states, now=now, required_ppe=required_zone_ppe)

    assert "no-head-protection" not in vio
