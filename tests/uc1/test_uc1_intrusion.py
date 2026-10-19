"""
Comprehensive test suite for UC1 (Intrusion Detection / Person Detection).

Validates:
1. Polygon geometry point-in-polygon containment (normalized and pixel coordinates).
2. Intrusion vs non-intrusion scenario classification.
3. Person detection response format and bounding box extraction.
4. AlertEvent platform contract compliance and JSON serialization.
5. Dynamic polygon zone configuration APIs.
6. Camera and video-upload session isolation.
7. Frontend CameraOverlay compatibility.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from stubs.uc1_v2.main import (
    DEFAULT_DEMO_ZONE,
    app,
    camera_zones,
    detect_people_and_intrusions,
    get_camera_zones,
    latest_camera_detections,
    latest_session_detections,
    maybe_fire_alerts,
    point_in_polygon,
    process_message,
)


# ─── 1. Polygon Geometry Containment Tests ───────────────────────

class TestPolygonContainment:
    """Tests geometric point-in-polygon testing for polygon zones."""

    def test_point_inside_normalized_polygon(self):
        polygon = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        # Point at center (0.5, 0.5)
        assert point_in_polygon(polygon, (0.5, 0.5), (1080, 1920)) is True

    def test_point_outside_normalized_polygon(self):
        polygon = [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]]
        # Point at top-left corner outside (0.1, 0.1)
        assert point_in_polygon(polygon, (0.1, 0.1), (1080, 1920)) is False

    def test_point_inside_pixel_polygon(self):
        polygon = [[200, 200], [800, 200], [800, 800], [200, 800]]
        # Point inside at (500, 500)
        assert point_in_polygon(polygon, (500, 500), (1080, 1920)) is True

    def test_point_outside_pixel_polygon(self):
        polygon = [[200, 200], [800, 200], [800, 800], [200, 800]]
        # Point outside at (100, 100)
        assert point_in_polygon(polygon, (100, 100), (1080, 1920)) is False

    def test_degenerate_polygon_returns_false(self):
        # A polygon with fewer than 3 vertices cannot enclose area
        polygon = [[0.2, 0.2], [0.8, 0.8]]
        assert point_in_polygon(polygon, (0.5, 0.5), (1080, 1920)) is False


# ─── 2. Intrusion vs Non-Intrusion Detection Tests ───────────────

class MockBox:
    def __init__(self, x1: float, y1: float, x2: float, y2: float, conf: float = 0.88):
        self.conf = np.array([conf])
        self.xyxyn = np.array([[x1, y1, x2, y2]])
        self.xyxy = np.array([[x1 * 1920, y1 * 1080, x2 * 1920, y2 * 1080]])


class MockResult:
    def __init__(self, boxes: list):
        self.boxes = boxes


class TestIntrusionScenarios:
    """Tests person detection and zone intrusion classification."""

    def setup_method(self):
        camera_zones.clear()

    def test_person_inside_restricted_zone_is_flagged_as_intruder(self):
        # Camera has restricted polygon [0.2, 0.2] to [0.8, 0.8]
        cam_id = "cam-test-intrusion-1"
        camera_zones[cam_id] = [{
            "zone_id": "zone-restricted-vault",
            "zone_name": "Secure Vault Perimeter",
            "polygon": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
            "priority": "CRITICAL",
            "is_restricted": True,
        }]

        # Person located inside: feet at ((0.4+0.6)/2 = 0.5, y2 = 0.7)
        mock_box = MockBox(0.4, 0.3, 0.6, 0.7, conf=0.92)
        mock_model = MagicMock(return_value=[MockResult([mock_box])])
        dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        people, intruders, detections, intrusions_by_zone = detect_people_and_intrusions(
            model=mock_model,
            frame=dummy_frame,
            camera_id=cam_id,
        )

        assert people == 1
        assert intruders == 1
        assert len(detections) == 1
        det = detections[0]
        assert det["is_violation"] is True
        assert det["compliant"] is False
        assert det["color"] == "#FF3333"
        assert "INTRUSION" in det["label"]
        assert "Secure Vault Perimeter" in det["label"]
        assert "zone-restricted-vault" in intrusions_by_zone

    def test_person_outside_restricted_zone_is_compliant(self):
        cam_id = "cam-test-compliant-1"
        camera_zones[cam_id] = [{
            "zone_id": "zone-restricted-vault",
            "zone_name": "Secure Vault Perimeter",
            "polygon": [[0.4, 0.4], [0.8, 0.4], [0.8, 0.8], [0.4, 0.8]],
            "priority": "CRITICAL",
            "is_restricted": True,
        }]

        # Person located outside restricted zone: feet at (0.15, 0.30)
        mock_box = MockBox(0.1, 0.1, 0.2, 0.3, conf=0.85)
        mock_model = MagicMock(return_value=[MockResult([mock_box])])
        dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        people, intruders, detections, intrusions_by_zone = detect_people_and_intrusions(
            model=mock_model,
            frame=dummy_frame,
            camera_id=cam_id,
        )

        assert people == 1
        assert intruders == 0
        assert len(detections) == 1
        det = detections[0]
        assert det["is_violation"] is False
        assert det["compliant"] is True
        assert det["color"] == "#38BDF8"
        assert "Person 85%" in det["label"]
        assert len(intrusions_by_zone) == 0

    def test_multi_person_scene_partitions_intruders_and_compliant(self):
        cam_id = "cam-test-multi-1"
        camera_zones[cam_id] = [{
            "zone_id": "zone-danger",
            "zone_name": "Hazard Area",
            "polygon": [[0.5, 0.5], [0.9, 0.5], [0.9, 0.9], [0.5, 0.9]],
            "priority": "CRITICAL",
            "is_restricted": True,
        }]

        # Person 1 (Outside): feet at (0.2, 0.4)
        box1 = MockBox(0.1, 0.1, 0.3, 0.4, conf=0.90)
        # Person 2 (Inside): feet at (0.7, 0.8)
        box2 = MockBox(0.6, 0.6, 0.8, 0.8, conf=0.95)

        mock_model = MagicMock(return_value=[MockResult([box1, box2])])
        dummy_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)

        people, intruders, detections, intrusions_by_zone = detect_people_and_intrusions(
            model=mock_model,
            frame=dummy_frame,
            camera_id=cam_id,
        )

        assert people == 2
        assert intruders == 1
        assert len(detections) == 2
        assert detections[0]["compliant"] is True
        assert detections[1]["compliant"] is False
        assert detections[1]["is_violation"] is True


# ─── 3. Alert Event Contract Compliance Tests ────────────────────

class TestAlertContractCompliance:
    """Tests alert schema validation and Redis publishing."""

    @pytest.mark.asyncio
    async def test_intrusion_alert_satisfies_platform_contract(self):
        cam_id = str(uuid.uuid4())
        mock_redis = AsyncMock()

        intrusions = {
            "zone-restricted-1": [{
                "track_id": 1,
                "bbox": {"x1": 0.2, "y1": 0.2, "x2": 0.4, "y2": 0.6},
                "label": "INTRUSION (Zone A) 95%",
                "is_violation": True,
            }]
        }

        # Clear cooldowns
        from stubs.uc1_v2.main import _last_alert_fired_at
        _last_alert_fired_at.clear()

        await maybe_fire_alerts(
            redis_client=mock_redis,
            camera_id=cam_id,
            frame_seq=42,
            people_count=1,
            intrusions_by_zone=intrusions,
            frame_reference=None,
            frame_provider=None,
            session_id=str(uuid.uuid4()),
        )

        assert mock_redis.xadd.called
        call_args = mock_redis.xadd.call_args
        stream_name = call_args[0][0]
        assert stream_name == "alerts:live"

        payload_raw = call_args[0][1]["data"]
        # Validate against official platform AlertEvent Pydantic schema
        event = AlertEvent.model_validate_json(payload_raw)
        assert event.source_uc == SourceUC.UC1
        assert event.alert_type == "intrusion_detected"
        assert event.severity == AlertSeverity.CRITICAL
        assert "Intrusion" in event.title
        assert event.metadata["intruders_count"] == 1
        assert event.metadata["total_people"] == 1

    @pytest.mark.asyncio
    async def test_fallback_headcount_breach_alert_validation(self):
        cam_id = str(uuid.uuid4())
        mock_redis = AsyncMock()

        from stubs.uc1_v2.main import _last_alert_fired_at
        _last_alert_fired_at.clear()

        # No polygon intrusions, but headcount threshold (>=3) exceeded
        await maybe_fire_alerts(
            redis_client=mock_redis,
            camera_id=cam_id,
            frame_seq=100,
            people_count=5,
            intrusions_by_zone={},
            frame_reference=None,
            frame_provider=None,
        )

        assert mock_redis.xadd.called
        payload_raw = mock_redis.xadd.call_args[0][1]["data"]
        event = AlertEvent.model_validate_json(payload_raw)
        assert event.source_uc == SourceUC.UC1
        assert event.alert_type == "headcount_breach"
        assert event.severity == AlertSeverity.HIGH

        # Now test 2x threshold (>= 6) -> CRITICAL
        _last_alert_fired_at.clear()
        await maybe_fire_alerts(
            redis_client=mock_redis,
            camera_id=cam_id,
            frame_seq=101,
            people_count=6,
            intrusions_by_zone={},
            frame_reference=None,
            frame_provider=None,
        )
        payload_raw2 = mock_redis.xadd.call_args[0][1]["data"]
        event2 = AlertEvent.model_validate_json(payload_raw2)
        assert event2.severity == AlertSeverity.CRITICAL


# ─── 4. REST API & Session Isolation Tests ───────────────────────

class TestUC1RestAPI:
    """Tests FastAPI endpoints, camera isolation, session isolation, and zone CRUD."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "healthy"
            assert data["uc"] == "uc1"
            assert data["version"] == "2.0.0"

    @pytest.mark.asyncio
    async def test_latest_detections_camera_and_session_isolation(self):
        cam_a = "cam-isolation-aaa"
        cam_b = "cam-isolation-bbb"
        session_1 = "session-upload-111"

        latest_camera_detections[cam_a] = {
            "timestamp": "2026-10-19T10:00:00Z",
            "camera_id": cam_a,
            "people_count": 2,
            "intrusion_count": 1,
            "detections": [{"label": "INTRUSION", "compliant": False, "is_violation": True}],
            "zones": [],
        }

        latest_camera_detections[f"{cam_a}:{session_1}"] = {
            "timestamp": "2026-10-19T10:00:05Z",
            "camera_id": cam_a,
            "session_id": session_1,
            "people_count": 1,
            "intrusion_count": 0,
            "detections": [{"label": "Person 90%", "compliant": True, "is_violation": False}],
            "zones": [],
        }

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Query standard camera A
            resp_cam = await client.get(f"/uc1/cameras/{cam_a}/latest-detections")
            assert resp_cam.status_code == 200
            assert resp_cam.json()["people_count"] == 2
            assert resp_cam.json()["intrusion_count"] == 1

            # Query camera A with specific upload session ID
            resp_sess = await client.get(f"/uc1/cameras/{cam_a}/latest-detections?session_id={session_1}")
            assert resp_sess.status_code == 200
            assert resp_sess.json()["people_count"] == 1
            assert resp_sess.json()["session_id"] == session_1

            # Query camera B (unpopulated) returns clean empty contract with default zones
            resp_b = await client.get(f"/uc1/cameras/{cam_b}/latest-detections")
            assert resp_b.status_code == 200
            data_b = resp_b.json()
            assert data_b["camera_id"] == cam_b
            assert data_b["people_count"] == 0
            assert data_b["detections"] == []
            assert len(data_b["zones"]) > 0

    @pytest.mark.asyncio
    async def test_zone_crud_endpoints(self):
        cam_id = "cam-zone-crud"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. GET default zones
            r_get = await client.get(f"/uc1/cameras/{cam_id}/zones")
            assert r_get.status_code == 200
            assert len(r_get.json()["zones"]) == 1

            # 2. POST update custom zones
            new_zones = {
                "zones": [
                    {
                        "zone_id": "zone-custom-1",
                        "zone_name": "Loading Dock Restricted",
                        "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
                        "priority": "HIGH",
                        "is_restricted": True,
                    }
                ]
            }
            r_post = await client.post(f"/uc1/cameras/{cam_id}/zones", json=new_zones)
            assert r_post.status_code == 200
            assert r_post.json()["status"] == "success"
            assert r_post.json()["zones"][0]["zone_id"] == "zone-custom-1"

            # Verify GET reflects update
            r_verify = await client.get(f"/uc1/cameras/{cam_id}/zones")
            assert r_verify.json()["zones"][0]["zone_name"] == "Loading Dock Restricted"

            # 3. DELETE resets back to default perimeter
            r_del = await client.delete(f"/uc1/cameras/{cam_id}/zones")
            assert r_del.status_code == 200
            assert r_del.json()["status"] == "reset_to_default"
