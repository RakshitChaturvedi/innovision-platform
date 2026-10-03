import pytest


def is_overlay_enabled_for_camera(camera_use_cases: list[str], enabled_config: str = "uc3") -> bool:
    if not camera_use_cases:
        return False
    allowed = [s.strip().lower() for s in enabled_config.split(",") if s.strip()]
    return any(uc.lower() in allowed for uc in camera_use_cases)


def get_active_overlay_use_case(camera_use_cases: list[str], enabled_config: str = "uc3") -> str | None:
    if not camera_use_cases:
        return None
    allowed = [s.strip().lower() for s in enabled_config.split(",") if s.strip()]
    for uc in camera_use_cases:
        if uc.lower() in allowed:
            return uc.lower()
    return None


def build_detections_url(camera_id: str, use_case: str = "uc3") -> str:
    return f"/{use_case.lower()}/cameras/{camera_id}/latest-detections"


def should_stop_polling_on_status(status_code: int) -> bool:
    return status_code == 404


def is_timestamp_stale(last_observed_change_ms: float, current_time_ms: float, threshold_ms: float = 5000.0) -> bool:
    return (current_time_ms - last_observed_change_ms) > threshold_ms


def test_overlay_disabled_when_not_in_config():
    """Overlay must be disabled if camera use cases do not match enabled list."""
    # Config is "uc3" by default
    assert not is_overlay_enabled_for_camera(["uc1"], "uc3")
    assert not is_overlay_enabled_for_camera(["uc2"], "uc3")
    assert is_overlay_enabled_for_camera(["uc3"], "uc3")

    # Config is "uc1,uc3"
    assert is_overlay_enabled_for_camera(["uc1"], "uc1,uc3")
    assert not is_overlay_enabled_for_camera(["uc4"], "uc1,uc3")


def test_active_overlay_use_case_returns_correct_matched_case():
    assert get_active_overlay_use_case(["uc1", "uc3"], "uc3") == "uc3"
    assert get_active_overlay_use_case(["uc1"], "uc3") is None
    assert build_detections_url("cam-42", "uc1") == "/uc1/cameras/cam-42/latest-detections"


def test_polling_stops_on_404():
    """HTTP 404 status code must trigger poll cancellation."""
    assert should_stop_polling_on_status(404)
    assert not should_stop_polling_on_status(200)
    assert not should_stop_polling_on_status(500)


def test_boxes_cleared_when_stale():
    """Timestamp un-changed for > 5000ms of local time must be flagged stale."""
    t0 = 1000000.0
    # 4 seconds elapsed -> not stale
    assert not is_timestamp_stale(t0, t0 + 4000.0, 5000.0)
    # 5.1 seconds elapsed -> stale
    assert is_timestamp_stale(t0, t0 + 5100.0, 5000.0)
