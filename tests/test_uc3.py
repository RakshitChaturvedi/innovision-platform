import time
from uuid import uuid4
import pytest
from services.uc3.src.compliance import evaluate_compliance, new_session_state
from services.uc3.src.consumer import get_class_color

def test_class_color_formatting():
    assert get_class_color("helmet", is_compliant=True) == "#FFC53D"
    assert get_class_color("vest", is_compliant=True) == "#FF8A3D"
    assert get_class_color("no-helmet", is_compliant=False) == "#FF3333"

def test_uc3_compliance_evaluation_compliant():
    session_state = new_session_state()
    now = time.monotonic()

    # Person with helmet, vest, gloves, shoes
    detections = [
        {"label": "person", "conf": 0.85, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "head", "conf": 0.80, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
        {"label": "helmet", "conf": 0.82, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
        {"label": "vest", "conf": 0.78, "box": (0.3, 0.3, 0.7, 0.7), "_track_id": 1},
    ]

    severity, violations, worker_violations = evaluate_compliance(
        detections=detections,
        worker_states=session_state,
        now=now,
        required_ppe=None,
    )

    assert severity == "ok"
    assert len(violations) == 0

def test_uc3_compliance_evaluation_missing_ppe():
    session_state = new_session_state()

    # Continuous observation over 3 seconds showing missing helmet
    detections = [
        {"label": "person", "conf": 0.85, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "head", "conf": 0.80, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=None,
        )

    # After sustained missing helmet beyond VIOLATION_WINDOW_SECONDS, violation is raised
    assert severity in ("medium", "high")
    assert "no-head-protection" in violations
