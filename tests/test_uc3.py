from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest
from pydantic import ValidationError

from services.camera_registry.src.schemas import (
    ZonePPERuleItem,
    ZonePPERulesConfig,
)
from services.camera_registry.src.service import CameraRegistryService
from services.uc3.src.compliance import (
    evaluate_compliance,
    new_session_state,
    is_ppe_required,
)
from services.uc3.src.consumer import (
    format_detections_for_overlay,
    get_class_color,
    UC3ConsumerManager,
)
from services.uc3.src.ppe_config import CONF_THRESHOLD
from services.uc3.src.publisher import UC3EventPublisher
from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC


# ==============================================================================
# Helper Mock DB Session for UC3 Resolution Tests
# ==============================================================================
class MockRow:
    def __init__(self, **kwargs):
        self._data = kwargs
        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getitem__(self, idx):
        if isinstance(idx, int):
            return list(self._data.values())[idx]
        return self._data[idx]

    def __len__(self):
        return len(self._data)

    @property
    def _mapping(self):
        return self._data


class MockResult:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows if rows is not None else ([] if row is None else [row])

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class MockAsyncSession:
    def __init__(self, handler):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute(self, stmt, params=None):
        return self.handler(str(stmt), params or {})

    def begin(self):
        return self


# ==============================================================================
# 1. Baseline Color Formatting & Basic Evaluation
# ==============================================================================
def test_class_color_formatting():
    assert get_class_color("helmet", is_compliant=True) == "#FFC53D"
    assert get_class_color("vest", is_compliant=True) == "#FF8A3D"
    assert get_class_color("no-helmet", is_compliant=False) == "#FF3333"
    assert get_class_color("no-vest", is_compliant=False) == "#FF3333"
    assert get_class_color("no-vest", is_compliant=True) == "#94A3B8"
    assert get_class_color("no-helmet", is_compliant=True) == "#94A3B8"


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

    assert severity in ("medium", "high")
    assert "no-head-protection" in violations


# ==============================================================================
# 2. Camera-to-Zone Resolution Tests (Section 2)
# ==============================================================================
@pytest.mark.asyncio
async def test_camera_assigned_using_native_zone_id_column():
    org_id = uuid4()
    zone_id = uuid4()
    cam_id = uuid4()

    def query_handler(stmt, params):
        if "FROM cameras WHERE id = :id" in stmt:
            return MockResult(MockRow(
                id=cam_id,
                organization_id=org_id,
                zone_id=zone_id,
                metadata={},
            ))
        if "FROM zones z" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Fabrication Shop",
                active=True,
                organization_id=org_id,
                required_ppe=["helmet", "vest"],
                min_confidence=0.65,
            ))
        if "SELECT min_confidence FROM uc3_zones" in stmt:
            return MockResult(MockRow(min_confidence=0.65))
        if "FROM uc3_zones" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Fabrication Shop",
                organization_id=org_id,
                is_active=True,
                min_confidence=0.65,
            ))
        if "FROM uc3_zone_ppe_rules" in stmt:
            return MockResult(rows=[
                MockRow(ppe_type="helmet"),
                MockRow(ppe_type="vest"),
            ])
        return MockResult()

    publisher = UC3EventPublisher.__new__(UC3EventPublisher)
    publisher._sessionmaker = lambda: MockAsyncSession(query_handler)

    res_zone_id, required_ppe, zone_name, min_conf = await publisher.get_camera_zone_and_rules(str(cam_id))

    assert res_zone_id == zone_id
    assert zone_name == "Fabrication Shop"
    assert required_ppe == frozenset({"helmet", "vest"})
    assert min_conf == 0.65


@pytest.mark.asyncio
async def test_camera_assigned_using_legacy_metadata_fallback():
    org_id = uuid4()
    zone_id = uuid4()
    cam_id = uuid4()

    def query_handler(stmt, params):
        if "FROM cameras WHERE id = :id" in stmt:
            return MockResult(MockRow(
                id=cam_id,
                organization_id=org_id,
                zone_id=None,  # Native column unset
                metadata={"zone_id": str(zone_id)},  # Legacy fallback
            ))
        if "FROM zones z" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Legacy Zone",
                active=True,
                organization_id=org_id,
                required_ppe=["gloves"],
                min_confidence=0.50,
            ))
        if "SELECT min_confidence FROM uc3_zones" in stmt:
            return MockResult(MockRow(min_confidence=0.50))
        if "FROM uc3_zones" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Legacy Zone",
                organization_id=org_id,
                is_active=True,
                min_confidence=0.50,
            ))
        if "FROM uc3_zone_ppe_rules" in stmt:
            return MockResult(rows=[MockRow(ppe_type="gloves")])
        return MockResult()

    publisher = UC3EventPublisher.__new__(UC3EventPublisher)
    publisher._sessionmaker = lambda: MockAsyncSession(query_handler)

    res_zone_id, required_ppe, zone_name, min_conf = await publisher.get_camera_zone_and_rules(str(cam_id))

    assert res_zone_id == zone_id
    assert zone_name == "Legacy Zone"
    assert required_ppe == frozenset({"gloves"})
    assert min_conf == 0.50


@pytest.mark.asyncio
async def test_camera_genuinely_unassigned():
    org_id = uuid4()
    cam_id = uuid4()

    def query_handler(stmt, params):
        if "FROM cameras WHERE id = :id" in stmt:
            return MockResult(MockRow(
                id=cam_id,
                organization_id=org_id,
                zone_id=None,
                metadata={},
            ))
        return MockResult()

    publisher = UC3EventPublisher.__new__(UC3EventPublisher)
    publisher._sessionmaker = lambda: MockAsyncSession(query_handler)

    res_zone_id, required_ppe, zone_name, min_conf = await publisher.get_camera_zone_and_rules(str(cam_id))

    assert res_zone_id is None
    assert required_ppe is None  # Signals default policy for genuinely unassigned cameras
    assert "Unassigned" in zone_name
    assert min_conf == CONF_THRESHOLD


@pytest.mark.asyncio
async def test_camera_with_invalid_or_malformed_zone_reference():
    cam_id = uuid4()

    def query_handler(stmt, params):
        if "FROM cameras WHERE id = :id" in stmt:
            return MockResult(MockRow(
                id=cam_id,
                organization_id=uuid4(),
                zone_id=None,
                metadata={"zone_id": "not-a-valid-uuid-string-1234"},
            ))
        return MockResult()

    publisher = UC3EventPublisher.__new__(UC3EventPublisher)
    publisher._sessionmaker = lambda: MockAsyncSession(query_handler)

    res_zone_id, required_ppe, zone_name, min_conf = await publisher.get_camera_zone_and_rules(str(cam_id))

    assert res_zone_id is None
    assert required_ppe == frozenset()  # Fail-safe: empty set, not arbitrary default
    assert "Invalid" in zone_name


@pytest.mark.asyncio
async def test_camera_assigned_to_inactive_zone():
    org_id = uuid4()
    zone_id = uuid4()
    cam_id = uuid4()

    def query_handler(stmt, params):
        if "FROM cameras WHERE id = :id" in stmt:
            return MockResult(MockRow(
                id=cam_id,
                organization_id=org_id,
                zone_id=zone_id,
                metadata={},
            ))
        if "FROM zones z" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Inactive Maintenance Bay",
                active=False,  # INACTIVE!
                organization_id=org_id,
                required_ppe=["helmet"],
            ))
        if "FROM uc3_zones" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Inactive Maintenance Bay",
                organization_id=org_id,
                is_active=False,
                min_confidence=0.50,
            ))
        return MockResult()

    publisher = UC3EventPublisher.__new__(UC3EventPublisher)
    publisher._sessionmaker = lambda: MockAsyncSession(query_handler)

    res_zone_id, required_ppe, zone_name, min_conf = await publisher.get_camera_zone_and_rules(str(cam_id))

    assert res_zone_id is None
    assert required_ppe == frozenset()  # Inactive zone does not enforce arbitrary rules
    assert "Inactive" in zone_name


@pytest.mark.asyncio
async def test_camera_cross_organization_zone_rejection():
    cam_org_id = uuid4()
    foreign_org_id = uuid4()
    zone_id = uuid4()
    cam_id = uuid4()

    def query_handler(stmt, params):
        if "FROM cameras WHERE id = :id" in stmt:
            return MockResult(MockRow(
                id=cam_id,
                organization_id=cam_org_id,
                zone_id=zone_id,
                metadata={},
            ))
        if "FROM zones z" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Foreign Tenant Zone",
                active=True,
                organization_id=foreign_org_id,  # Cross-tenant mismatch!
                required_ppe=["helmet"],
            ))
        if "FROM uc3_zones" in stmt:
            return MockResult(MockRow(
                id=zone_id,
                name="Foreign Tenant Zone",
                organization_id=foreign_org_id,
                is_active=True,
                min_confidence=0.50,
            ))
        return MockResult()

    publisher = UC3EventPublisher.__new__(UC3EventPublisher)
    publisher._sessionmaker = lambda: MockAsyncSession(query_handler)

    res_zone_id, required_ppe, zone_name, min_conf = await publisher.get_camera_zone_and_rules(str(cam_id))

    assert res_zone_id is None
    assert required_ppe == frozenset()  # Cross-tenant denied
    assert "Cross-Tenant" in zone_name


# ==============================================================================
# 3. Zone min_confidence Persistence & Enforcement Tests (Section 3)
# ==============================================================================
def test_min_confidence_schema_validation():
    # Valid configurations
    c1 = ZonePPERulesConfig(ppe_rules=[], min_confidence=0.75)
    assert c1.min_confidence == 0.75

    c2 = ZonePPERulesConfig(ppe_rules=[], min_confidence=0.0)
    assert c2.min_confidence == 0.0

    c3 = ZonePPERulesConfig(ppe_rules=[], min_confidence=1.0)
    assert c3.min_confidence == 1.0

    # Invalid range: below 0.0
    with pytest.raises(ValidationError):
        ZonePPERulesConfig(ppe_rules=[], min_confidence=-0.1)

    # Invalid range: above 1.0
    with pytest.raises(ValidationError):
        ZonePPERulesConfig(ppe_rules=[], min_confidence=1.5)


@pytest.mark.asyncio
async def test_two_zones_with_different_confidence_thresholds():
    zone_a_id = str(uuid4())
    zone_b_id = str(uuid4())

    store = {
        zone_a_id: {"min_confidence": 0.80, "rules": [MockRow(ppe_type="helmet", required=True, severity="high", grace_seconds=0)]},
        zone_b_id: {"min_confidence": 0.40, "rules": [MockRow(ppe_type="helmet", required=True, severity="high", grace_seconds=0)]},
    }

    def query_handler(stmt, params):
        z_id = params.get("id")
        if "SELECT id FROM zones WHERE id = :id" in stmt:
            return MockResult(MockRow(id=z_id))
        if "SELECT min_confidence FROM uc3_zones WHERE id = :id" in stmt:
            return MockResult(MockRow(min_confidence=store[z_id]["min_confidence"]))
        if "FROM uc3_zone_ppe_rules" in stmt:
            return MockResult(rows=store[z_id]["rules"])
        return MockResult()

    class DummyRedis:
        async def publish(self, ch, msg):
            pass

    service = CameraRegistryService(lambda: MockAsyncSession(query_handler), DummyRedis())

    config_a = await service.get_zone_ppe_rules(zone_a_id)
    config_b = await service.get_zone_ppe_rules(zone_b_id)

    assert config_a["min_confidence"] == 0.80
    assert config_b["min_confidence"] == 0.40


def test_prediction_below_threshold_cannot_create_violation():
    session_state = new_session_state()

    # Zone threshold is high: 0.80
    # Negative detection has confidence 0.65 (< 0.80)
    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.65, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
            min_confidence=0.80,  # Zone threshold
        )

    # Prediction below applicable threshold cannot create violation
    assert severity == "ok"
    assert len(violations) == 0
    assert len(worker_violations) == 0


def test_prediction_meeting_threshold_creates_violation():
    session_state = new_session_state()

    # Zone threshold is 0.60
    # Negative detection meets threshold at 0.75
    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.75, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
            min_confidence=0.60,
        )

    assert severity in ("medium", "high")
    assert "no-head-protection" in violations


def test_legacy_fallback_when_threshold_unconfigured():
    session_state = new_session_state()

    # When min_confidence is None, documented fallback CONF_THRESHOLD (0.35) is used
    detections = [
        {"label": "person", "conf": 0.85, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.40, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
            min_confidence=None,  # Fallback to CONF_THRESHOLD (0.35)
        )

    assert severity in ("medium", "high")
    assert "no-head-protection" in violations


# ==============================================================================
# 4. Correct Negative PPE Class Handling Tests (Section 4)
# ==============================================================================
def test_required_helmet_with_confirmed_no_helmet_detection():
    session_state = new_session_state()

    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.85, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    all_worker_violations = []
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )
        all_worker_violations.extend(worker_violations)

    assert "no-head-protection" in violations
    assert any(wv["ppe_type"] == "helmet" for wv in all_worker_violations)


def test_required_vest_with_confirmed_no_vest_detection():
    session_state = new_session_state()

    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-vest", "conf": 0.88, "box": (0.3, 0.3, 0.7, 0.7), "_track_id": 1},
    ]

    all_worker_violations = []
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"vest"}),
        )
        all_worker_violations.extend(worker_violations)

    assert "no-safety-vest" in violations
    assert any(wv["ppe_type"] == "vest" for wv in all_worker_violations)


def test_required_gloves_with_confirmed_no_gloves_detection():
    session_state = new_session_state()

    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-gloves", "conf": 0.82, "box": (0.1, 0.5, 0.3, 0.7), "_track_id": 1},
    ]

    all_worker_violations = []
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"gloves"}),
        )
        all_worker_violations.extend(worker_violations)

    assert "no-hands-protection" in violations
    assert any(wv["ppe_type"] == "gloves" for wv in all_worker_violations)


def test_unrequired_ppe_negative_detection_ignored():
    session_state = new_session_state()

    # Zone requires ONLY vest; helmet is NOT required
    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "vest", "conf": 0.85, "box": (0.3, 0.3, 0.7, 0.7), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.95, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
        {"label": "no-gloves", "conf": 0.90, "box": (0.1, 0.5, 0.3, 0.7), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"vest"}),  # Only vest required
        )

    # An item that is not required by the zone must not create a violation
    assert severity == "ok"
    assert len(violations) == 0
    assert len(worker_violations) == 0


def test_positive_negative_conflict_reconciliation():
    session_state = new_session_state()

    # Case 1: Positive helmet conf (0.85) > Negative helmet conf (0.40) -> Positive wins (Compliant)
    detections_pos_wins = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.85, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.40, "box": (0.40, 0.10, 0.60, 0.28), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections_pos_wins,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )

    assert severity == "ok"
    assert len(violations) == 0

    # Case 2: Negative helmet conf (0.90) > Positive helmet conf (0.45) -> Negative wins (Violation)
    session_state_2 = new_session_state()
    detections_neg_wins = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 2},
        {"label": "helmet", "conf": 0.45, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 2},
        {"label": "no-helmet", "conf": 0.90, "box": (0.40, 0.10, 0.60, 0.28), "_track_id": 2},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections_neg_wins,
            worker_states=session_state_2,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )

    assert "no-head-protection" in violations


def test_negative_detections_different_tracked_workers():
    session_state = new_session_state()

    # Worker 1 has no-helmet (violating)
    # Worker 2 has valid helmet and vest (compliant)
    detections = [
        # Worker 1
        {"label": "person", "conf": 0.90, "box": (0.1, 0.1, 0.4, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.85, "box": (0.15, 0.1, 0.35, 0.3), "_track_id": 1},
        {"label": "vest", "conf": 0.85, "box": (0.15, 0.3, 0.35, 0.7), "_track_id": 1},
        # Worker 2
        {"label": "person", "conf": 0.92, "box": (0.6, 0.1, 0.9, 0.9), "_track_id": 2},
        {"label": "helmet", "conf": 0.88, "box": (0.65, 0.1, 0.85, 0.3), "_track_id": 2},
        {"label": "vest", "conf": 0.86, "box": (0.65, 0.3, 0.85, 0.7), "_track_id": 2},
    ]

    all_worker_violations = []
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet", "vest"}),
        )
        all_worker_violations.extend(worker_violations)

    # Worker 1 is flagged, Worker 2 is not
    assert len(violations) == 1
    assert "no-head-protection" in violations
    assert len(all_worker_violations) == 1
    assert all_worker_violations[0]["worker_id"] == 1


def test_temporal_hysteresis_and_recovery_to_compliant():
    session_state = new_session_state()

    # Step 1: Sustained violation over 2.5s -> violation raises
    violating_dets = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.85, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=violating_dets,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )

    assert "no-head-protection" in violations

    # Step 2: Worker puts on helmet; sustained observation over next 3 seconds -> violation clears
    compliant_dets = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.88, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
    ]
    for t in [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=compliant_dets,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )

    # Recovery confirmed!
    assert severity == "ok"
    assert len(violations) == 0


def test_prevention_of_duplicate_violation_alerts():
    session_state = new_session_state()

    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.85, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    total_new_worker_violations = 0
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]:
        _, _, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )
        total_new_worker_violations += len(worker_violations)

    # worker_violations is only appended once when state transitions from False -> True
    assert total_new_worker_violations == 1


def test_alert_contract_preservation():
    from datetime import datetime, timezone
    evt_id = uuid4()
    cam_id = uuid4()
    org_id = uuid4()
    now_dt = datetime.now(timezone.utc)
    alert = AlertEvent(
        alert_id=uuid4(),
        source_event_id=evt_id,
        source_uc=SourceUC.UC3,
        camera_id=cam_id,
        timestamp=now_dt,
        severity=AlertSeverity.HIGH,
        alert_type="uc3_ppe_violation",
        title="PPE Violation — Missing Helmet",
        description="Worker 1 detected missing required helmet.",
        status=AlertStatus.PENDING,
        metadata={"track_id": 1, "missing_ppe": ["helmet"]},
    )
    assert alert.source_event_id == evt_id
    assert alert.source_uc == SourceUC.UC3
    assert alert.metadata["track_id"] == 1
    assert alert.status == AlertStatus.PENDING


# ==============================================================================
# 5. M-1 Overlay Confidence Inconsistency Regression Tests
# ==============================================================================
def test_sub_threshold_negative_detection_not_violation_in_overlay():
    session_state = new_session_state()

    # Zone requires helmet with min_confidence = 0.70
    # The negative detection conf (0.45) is below min_confidence
    raw_detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.45, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    severity, violations, worker_violations = evaluate_compliance(
        detections=raw_detections,
        worker_states=session_state,
        now=0.0,
        required_ppe=frozenset({"helmet"}),
        min_confidence=0.70,
    )

    # Compliance engine rejected/filtered sub-threshold detection
    assert severity == "ok"
    assert len(violations) == 0
    assert len(worker_violations) == 0

    # Format detections for overlay
    overlay_detections = format_detections_for_overlay(raw_detections)
    assert len(overlay_detections) == 2

    no_helmet_overlay = next(d for d in overlay_detections if d["label"] == "No Helmet")
    assert no_helmet_overlay["compliant"] is True
    assert no_helmet_overlay["color"] != "#FF3333"
    assert no_helmet_overlay["color"] == "#94A3B8"
    assert no_helmet_overlay["confidence"] == 0.45


def test_confident_required_negative_detection_produces_confirmed_violation_in_overlay():
    session_state = new_session_state()

    # Zone requires helmet with min_confidence = 0.70
    # The negative detection conf (0.85) meets/exceeds min_confidence
    raw_detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.85, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    all_worker_violations = []
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=raw_detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
            min_confidence=0.70,
        )
        all_worker_violations.extend(worker_violations)

    assert severity in ("medium", "high")
    assert "no-head-protection" in violations
    assert len(all_worker_violations) >= 1

    # Format detections for overlay
    overlay_detections = format_detections_for_overlay(raw_detections)
    no_helmet_overlay = next(d for d in overlay_detections if d["label"] == "No Helmet")

    # Confirmed violation appears in red with compliant=False
    assert no_helmet_overlay["compliant"] is False
    assert no_helmet_overlay["color"] == "#FF3333"
    assert no_helmet_overlay["confidence"] == 0.85


def test_unrequired_ppe_negative_detection_not_violation_in_overlay():
    session_state = new_session_state()

    # Zone requires ONLY vest; helmet is NOT required
    raw_detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "vest", "conf": 0.85, "box": (0.3, 0.3, 0.7, 0.7), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.95, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]

    severity, violations, worker_violations = evaluate_compliance(
        detections=raw_detections,
        worker_states=session_state,
        now=0.0,
        required_ppe=frozenset({"vest"}),
        min_confidence=0.70,
    )

    assert severity == "ok"
    assert len(violations) == 0

    overlay_detections = format_detections_for_overlay(raw_detections)
    no_helmet_overlay = next(d for d in overlay_detections if d["label"] == "No Helmet")
    vest_overlay = next(d for d in overlay_detections if d["label"] == "Vest")

    assert no_helmet_overlay["compliant"] is True
    assert no_helmet_overlay["color"] == "#94A3B8"
    assert vest_overlay["compliant"] is True
    assert vest_overlay["color"] == "#FF8A3D"


def test_positive_negative_conflict_reconciliation_overlay():
    session_state = new_session_state()

    # Case A: Positive helmet conf (0.85) >= Negative helmet conf (0.40) -> Positive wins
    pos_wins_detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.85, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.40, "box": (0.40, 0.10, 0.60, 0.28), "_track_id": 1},
    ]

    severity, violations, _ = evaluate_compliance(
        detections=pos_wins_detections,
        worker_states=session_state,
        now=0.0,
        required_ppe=frozenset({"helmet"}),
    )

    assert severity == "ok"
    assert len(violations) == 0

    overlay_pos_wins = format_detections_for_overlay(pos_wins_detections)
    nh_pos = next(d for d in overlay_pos_wins if d["label"] == "No Helmet")
    h_pos = next(d for d in overlay_pos_wins if d["label"] == "Helmet")

    assert nh_pos["compliant"] is True
    assert nh_pos["color"] == "#94A3B8"
    assert h_pos["compliant"] is True
    assert h_pos["color"] == "#FFC53D"

    # Case B: Negative helmet conf (0.90) > Positive helmet conf (0.45) -> Negative wins
    session_state_2 = new_session_state()
    neg_wins_detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 2},
        {"label": "helmet", "conf": 0.45, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 2},
        {"label": "no-helmet", "conf": 0.90, "box": (0.40, 0.10, 0.60, 0.28), "_track_id": 2},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity_2, violations_2, _ = evaluate_compliance(
            detections=neg_wins_detections,
            worker_states=session_state_2,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )

    assert "no-head-protection" in violations_2

    overlay_neg_wins = format_detections_for_overlay(neg_wins_detections)
    nh_neg = next(d for d in overlay_neg_wins if d["label"] == "No Helmet")
    assert nh_neg["compliant"] is False
    assert nh_neg["color"] == "#FF3333"


def test_overlay_response_fields_and_contract_compatibility():
    cam_id = str(uuid4())
    zone_id = uuid4()
    raw_detections = [
        {"label": "person", "conf": 0.92, "box": (0.1, 0.1, 0.5, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.88, "box": (0.2, 0.1, 0.4, 0.3), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.35, "box": (0.22, 0.12, 0.38, 0.28), "_track_id": 1},
    ]
    session_state = new_session_state()

    severity, violations, _ = evaluate_compliance(
        detections=raw_detections,
        worker_states=session_state,
        now=0.0,
        required_ppe=frozenset({"helmet"}),
        min_confidence=0.65,
    )

    formatted = format_detections_for_overlay(raw_detections)

    latest_response = {
        "timestamp": "2026-10-11T12:00:00.000Z",
        "camera_id": cam_id,
        "detections": formatted,
        "severity": severity,
        "violations": violations,
        "zone": {
            "id": str(zone_id),
            "name": "Fabrication Zone",
            "required_ppe": ["helmet"],
            "min_confidence": 0.65,
        },
    }

    # Verify latest_detections schema contracts consumed by CameraOverlay.tsx
    assert "timestamp" in latest_response
    assert "camera_id" in latest_response
    assert "detections" in latest_response
    assert "severity" in latest_response
    assert "violations" in latest_response
    assert "zone" in latest_response

    for det in latest_response["detections"]:
        assert "track_id" in det
        assert "label" in det
        assert "bbox" in det
        assert "color" in det
        assert "compliant" in det
        assert "confidence" in det
        assert set(det["bbox"].keys()) == {"x1", "y1", "x2", "y2"}
        assert det["color"].startswith("#")
        assert isinstance(det["compliant"], bool)
        assert isinstance(det["confidence"], float)

    # Below-threshold no-helmet must be compliant and not red
    sub_no_helmet = next(d for d in latest_response["detections"] if d["label"] == "No Helmet")
    assert sub_no_helmet["compliant"] is True
    assert sub_no_helmet["color"] == "#94A3B8"


# ==============================================================================
# 6. Violation-Only Overlay & Alert Consistency Scenarios (Scenarios A through I)
# ==============================================================================

def test_scenario_a_zone_requires_helmet_gloves_worker_has_both():
    """Scenario A: Zone requires helmet and gloves; worker has both -> no visible boxes and no alert."""
    session_state = new_session_state()
    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.88, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
        {"label": "gloves", "conf": 0.85, "box": (0.2, 0.5, 0.35, 0.7), "_track_id": 1},
    ]

    severity, violations, worker_violations = evaluate_compliance(
        detections=detections,
        worker_states=session_state,
        now=0.0,
        required_ppe=frozenset({"helmet", "gloves"}),
    )

    assert severity == "ok"
    assert len(violations) == 0
    assert len(worker_violations) == 0

    visible_overlay = format_detections_for_overlay(detections, violations_only=True)
    assert len(visible_overlay) == 0


def test_scenario_b_zone_requires_helmet_gloves_worker_missing_gloves():
    """Scenario B: Zone requires helmet and gloves; worker wears helmet but is confirmed missing gloves -> only missing gloves is red, alert generated."""
    session_state = new_session_state()
    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.88, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
        {"label": "no-gloves", "conf": 0.85, "box": (0.2, 0.5, 0.35, 0.7), "_track_id": 1},
    ]

    all_worker_violations = []
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet", "gloves"}),
        )
        all_worker_violations.extend(worker_violations)

    assert severity in ("medium", "high")
    assert "no-hands-protection" in violations
    assert any(wv["ppe_type"] == "gloves" for wv in all_worker_violations)

    # User-facing overlay shows ONLY the confirmed missing-gloves violation in red
    visible_overlay = format_detections_for_overlay(detections, violations_only=True)
    assert len(visible_overlay) == 1
    assert visible_overlay[0]["label"] == "No Gloves"
    assert visible_overlay[0]["color"] == "#FF3333"
    assert visible_overlay[0]["compliant"] is False
    assert visible_overlay[0]["is_violation"] is True


def test_scenario_c_zone_requires_helmet_only_worker_missing_gloves_wears_helmet():
    """Scenario C: Zone requires helmet only; worker is missing gloves but wears helmet -> no gloves box or alert."""
    session_state = new_session_state()
    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.88, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
        {"label": "no-gloves", "conf": 0.90, "box": (0.2, 0.5, 0.35, 0.7), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),  # Gloves NOT required
        )

    assert severity == "ok"
    assert len(violations) == 0
    assert len(worker_violations) == 0

    visible_overlay = format_detections_for_overlay(detections, violations_only=True)
    assert len(visible_overlay) == 0


def test_scenario_d_zone_has_no_required_ppe():
    """Scenario D: Zone has no required PPE -> no missing-PPE violation boxes or alerts."""
    session_state = new_session_state()
    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.95, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
        {"label": "no-vest", "conf": 0.92, "box": (0.3, 0.3, 0.7, 0.7), "_track_id": 1},
        {"label": "no-gloves", "conf": 0.90, "box": (0.2, 0.5, 0.35, 0.7), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset(),  # 0 required PPE
        )

    assert severity == "ok"
    assert len(violations) == 0
    assert len(worker_violations) == 0

    visible_overlay = format_detections_for_overlay(detections, violations_only=True)
    assert len(visible_overlay) == 0


def test_scenario_e_raw_negative_prediction_fails_confirmation():
    """Scenario E: Raw no-helmet prediction fails required confidence or temporal criteria -> no violation box or alert."""
    session_state = new_session_state()

    # Case 1: Sub-threshold confidence (< 0.70)
    low_conf_detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "no-helmet", "conf": 0.40, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 1},
    ]
    severity, violations, worker_violations = evaluate_compliance(
        detections=low_conf_detections,
        worker_states=session_state,
        now=0.0,
        required_ppe=frozenset({"helmet"}),
        min_confidence=0.70,
    )
    assert severity == "ok"
    assert len(violations) == 0
    assert len(worker_violations) == 0
    assert len(format_detections_for_overlay(low_conf_detections, violations_only=True)) == 0

    # Case 2: High confidence but single-frame transient (fails temporal criteria < 2.0s and < 2 samples)
    session_state_2 = new_session_state()
    high_conf_detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 2},
        {"label": "no-helmet", "conf": 0.90, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 2},
    ]
    severity_2, violations_2, worker_violations_2 = evaluate_compliance(
        detections=high_conf_detections,
        worker_states=session_state_2,
        now=0.0,  # Only first frame
        required_ppe=frozenset({"helmet"}),
        min_confidence=0.70,
    )
    assert severity_2 == "ok"
    assert len(violations_2) == 0
    assert len(worker_violations_2) == 0
    assert len(format_detections_for_overlay(high_conf_detections, violations_only=True)) == 0


def test_scenario_f_worker_with_one_violation_and_compliant_ppe():
    """Scenario F: Worker has one confirmed violation and other compliant PPE -> only violation is red; compliant PPE and person remain invisible."""
    session_state = new_session_state()
    detections = [
        {"label": "person", "conf": 0.95, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 1},
        {"label": "helmet", "conf": 0.89, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 1},
        {"label": "vest", "conf": 0.88, "box": (0.3, 0.3, 0.7, 0.7), "_track_id": 1},
        {"label": "no-gloves", "conf": 0.84, "box": (0.2, 0.5, 0.35, 0.7), "_track_id": 1},
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]:
        severity, violations, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet", "vest", "gloves"}),
        )

    # 1. Internal evaluation confirmed violation
    assert "no-hands-protection" in violations

    # 2. In user-facing overlay: ONLY the confirmed missing-gloves is included
    visible_overlay = format_detections_for_overlay(detections, violations_only=True)
    assert len(visible_overlay) == 1
    assert visible_overlay[0]["label"] == "No Gloves"
    assert visible_overlay[0]["color"] == "#FF3333"
    assert visible_overlay[0]["compliant"] is False

    # 3. Non-violation items (person, helmet, vest) are NOT in the overlay
    overlay_labels = [d["label"] for d in visible_overlay]
    assert "Person" not in overlay_labels
    assert "Helmet" not in overlay_labels
    assert "Vest" not in overlay_labels


@pytest.mark.asyncio
async def test_scenario_g_uc3_disabled_by_effective_analytics():
    """Scenario G: UC3 is disabled by effective analytics configuration -> no violation results or alerts generated."""
    cam_id = uuid4()

    def query_handler(stmt, params):
        if "camera_effective_analytics" in stmt:
            # UC3 analytic is explicitly NOT active
            return MockResult(MockRow(is_active=False))
        if "FROM cameras WHERE id = :id" in stmt:
            return MockResult(MockRow(
                id=cam_id,
                organization_id=uuid4(),
                zone_id=uuid4(),
                use_cases=["uc1"],  # UC3 not in use_cases
                metadata={"disabled_uc": {"uc3": True}},
            ))
        return MockResult()

    publisher = UC3EventPublisher.__new__(UC3EventPublisher)
    publisher._sessionmaker = lambda: MockAsyncSession(query_handler)

    is_enabled = await publisher.is_camera_uc3_enabled(str(cam_id))
    assert is_enabled is False


def test_scenario_h_uploaded_video_session_isolation():
    """Scenario H: Uploaded-video session isolation -> boxes belong strictly to camera and session without leakage."""
    manager = UC3ConsumerManager.__new__(UC3ConsumerManager)
    manager.latest_detections = {}

    cam_id = "test-cam-001"
    session_upload_1 = "upload-session-aaa"
    session_upload_2 = "upload-session-bbb"

    # Simulate live RTSP detection
    manager.latest_detections[cam_id] = {
        "camera_id": cam_id,
        "session_id": None,
        "source_type": "live_rtsp",
        "detections": [{"label": "No Helmet", "color": "#FF3333", "compliant": False}],
    }

    # Simulate uploaded video session 1 (clean, compliant)
    manager.latest_detections[f"{cam_id}:{session_upload_1}"] = {
        "camera_id": cam_id,
        "session_id": session_upload_1,
        "source_type": "uploaded_video",
        "detections": [],
    }

    # Simulate uploaded video session 2 (missing gloves)
    manager.latest_detections[f"{cam_id}:{session_upload_2}"] = {
        "camera_id": cam_id,
        "session_id": session_upload_2,
        "source_type": "uploaded_video",
        "detections": [{"label": "No Gloves", "color": "#FF3333", "compliant": False}],
    }

    # Verify query for session 1 gets session 1, never live RTSP or session 2
    res_1 = manager.get_latest_detections(cam_id, session_upload_1)
    assert res_1["session_id"] == session_upload_1
    assert len(res_1["detections"]) == 0

    # Verify query for session 2 gets session 2
    res_2 = manager.get_latest_detections(cam_id, session_upload_2)
    assert res_2["session_id"] == session_upload_2
    assert len(res_2["detections"]) == 1
    assert res_2["detections"][0]["label"] == "No Gloves"

    # Verify query for non-existent session returns None (router returns empty, never live)
    res_unknown = manager.get_latest_detections(cam_id, "unknown-session")
    assert res_unknown is None

    # Verify live RTSP query gets live RTSP
    res_live = manager.get_latest_detections(cam_id, None)
    assert res_live["session_id"] is None
    assert len(res_live["detections"]) == 1
    assert res_live["detections"][0]["label"] == "No Helmet"


def test_scenario_i_regression_checks():
    """Scenario I: Regression checks -> tracking, deduplication, alert contract, and non-violation data models remain intact."""
    session_state = new_session_state()

    detections = [
        {"label": "person", "conf": 0.90, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 42},
        {"label": "no-helmet", "conf": 0.85, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 42},
    ]

    total_worker_alerts = 0
    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5]:
        _, _, worker_violations = evaluate_compliance(
            detections=detections,
            worker_states=session_state,
            now=t,
            required_ppe=frozenset({"helmet"}),
        )
        total_worker_alerts += len(worker_violations)

    # Deduplication check: alert only created once on state transition
    assert total_worker_alerts == 1

    # Overlay format check
    overlay = format_detections_for_overlay(detections, violations_only=True)
    assert len(overlay) == 1
    assert overlay[0]["track_id"] == 42
    assert overlay[0]["color"] == "#FF3333"
    assert overlay[0]["compliant"] is False
    assert overlay[0]["is_violation"] is True

