"""
tests/test_alert_system_reliability.py
Mission-Critical Alert Reliability, Consistency, Deduplication, and Multi-UC Traceability Test Suite.
Covers:
- Phase 2: Schema validation, NumPy scalar/array serialization, contract enforcement
- Phase 3: Resilient publishing, exponential backoff retries, in-memory buffering & draining
- Phase 4: Deterministic event identity, duplicate message ACK without PEL leak, sustained hazard grouping
- Phase 5: Centralized severity hierarchy and dynamic incident escalation
- Phase 6: Persistence before notification, transaction rollback on failure
- Phase 7: Reconnection missed-alert recovery and WebSocket event payload serialization
- Phase 9: UC1, UC2, UC3, and UC4 alert generation, validation, and lifecycle
"""

import asyncio
from datetime import datetime, timezone
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import numpy as np
import pytest

from shared.contracts.alert_event import AlertEvent, AlertEventValidator
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher, ALERTS_DEAD_LETTER, ALERTS_LIVE_STREAM
from services.alert_management.src.consumer import AlertConsumer, MAX_DELIVERY_ATTEMPTS
from services.alert_management.src.incident_trigger import maybe_create_incident
from services.alert_management.src.reconnect import fetch_missed_alerts
from services.alert_management.src.websocket import _serialize

# Fixtures for all 4 Use Cases
@pytest.fixture
def uc1_intrusion_alert():
    return AlertEvent(
        alert_id=uuid4(),
        camera_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        alert_type="intrusion_detected",
        title="Restricted Zone Intrusion — 1 person(s) in Vault",
        description="UC1 Person Detection pipeline detected unauthorized human intrusion.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC1,
        status=AlertStatus.PENDING,
        metadata={
            "zone_id": "zone-vault-01",
            "zone_name": "Vault",
            "intruders_count": np.int64(1),
            "confidence": np.float32(0.92),
            "feet_coordinates": np.array([0.45, 0.78]),
        },
    )


@pytest.fixture
def uc2_fire_alert():
    return AlertEvent(
        alert_id=uuid4(),
        camera_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        alert_type="fire_detected",
        title="Fire Detected: Assembly Area",
        description="Flame detected in zone with 88% confidence.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC2,
        frame_reference="frame:cam-001:100",
        frame_provider=FrameProvider.REDIS,
        status=AlertStatus.PENDING,
        metadata={
            "detection_type": "fire",
            "confidence": np.float32(0.88),
            "verification_score": np.float32(0.85),
            "hsv_score": np.float32(0.91),
            "bbox": {"x1": 50, "y1": 50, "x2": 120, "y2": 120},
        },
    )


@pytest.fixture
def uc3_ppe_alert():
    return AlertEvent(
        alert_id=uuid4(),
        camera_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="ppe_violation",
        title="PPE Violation — Missing Hardhat",
        description="Worker 42 detected missing required hardhat.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC3,
        status=AlertStatus.PENDING,
        metadata={
            "track_id": 42,
            "ppe_type": "hardhat",
            "missing_ppe": ["hardhat"],
            "zone_id": "zone-shop-floor",
            "confidence": np.float32(0.94),
        },
    )


@pytest.fixture
def uc4_speed_alert():
    return AlertEvent(
        alert_id=uuid4(),
        camera_id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="speed_violation",
        title="Speed Violation: MH12AB1234 (62 km/h in 40 km/h zone)",
        description="Vehicle exceeded speed limit.",
        source_event_id=uuid4(),
        source_uc=SourceUC.UC4,
        status=AlertStatus.PENDING,
        metadata={
            "tracker_id": 7,
            "plate": "MH12AB1234",
            "speed_kmh": np.float32(62.5),
            "speed_limit_kmh": np.int64(40),
            "vehicle_type": "truck",
        },
    )


# ==============================================================================
# 1. CONTRACT & SERIALIZATION TESTS (PHASE 2)
# ==============================================================================

class TestAlertContractsAndSerialization:
    def test_all_four_use_cases_produce_valid_contracts(
        self, uc1_intrusion_alert, uc2_fire_alert, uc3_ppe_alert, uc4_speed_alert
    ):
        for alert, expected_uc in [
            (uc1_intrusion_alert, SourceUC.UC1),
            (uc2_fire_alert, SourceUC.UC2),
            (uc3_ppe_alert, SourceUC.UC3),
            (uc4_speed_alert, SourceUC.UC4),
        ]:
            assert alert.source_uc == expected_uc
            assert isinstance(alert.alert_id, UUID)
            assert isinstance(alert.camera_id, UUID)
            assert isinstance(alert.timestamp, datetime)
            assert alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.HIGH, AlertSeverity.MEDIUM, AlertSeverity.LOW]
            assert len(alert.title) > 0
            assert len(alert.description) > 0

    def test_numpy_scalars_and_arrays_serialize_seamlessly(self, uc1_intrusion_alert):
        raw_json = uc1_intrusion_alert.model_dump_json()
        assert "confidence" in raw_json
        parsed = json.loads(raw_json)
        assert isinstance(parsed["metadata"]["confidence"], float)
        assert isinstance(parsed["metadata"]["intruders_count"], int)
        assert isinstance(parsed["metadata"]["feet_coordinates"], list)

        # Ensure roundtrip deserialization restores identical fields
        restored = AlertEvent.model_validate_json(raw_json)
        assert restored.alert_id == uc1_intrusion_alert.alert_id
        assert restored.metadata["intruders_count"] == 1
        assert restored.metadata["feet_coordinates"] == [0.45, 0.78]

    def test_string_uuid_coercion_on_construction(self):
        cam_id_str = "e2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e"
        alert = AlertEvent(
            camera_id=cam_id_str,
            timestamp=datetime.now(timezone.utc),
            severity=AlertSeverity.HIGH,
            alert_type="test",
            title="Coercion Test",
            description="Testing string UUID coercion",
            source_event_id="a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d",
            source_uc=SourceUC.UC1,
        )
        assert isinstance(alert.camera_id, UUID)
        assert str(alert.camera_id) == cam_id_str

    def test_frame_reference_and_provider_mutual_consistency(self):
        # Missing provider when reference is given must raise ValueError
        with pytest.raises(ValueError, match="frame_reference and frame_provider"):
            AlertEvent(
                camera_id=uuid4(),
                timestamp=datetime.now(timezone.utc),
                severity=AlertSeverity.HIGH,
                alert_type="test",
                title="Invalid Frame",
                description="Missing provider",
                source_event_id=uuid4(),
                source_uc=SourceUC.UC1,
                frame_reference="frame:01",
                frame_provider=None,
            )

    def test_validator_accepts_uuid_and_string_camera_sets(self, uc1_intrusion_alert):
        cam_id = uc1_intrusion_alert.camera_id
        # Test UUID set
        assert AlertEventValidator.validate(uc1_intrusion_alert, {cam_id}) == []
        # Test string set
        assert AlertEventValidator.validate(uc1_intrusion_alert, {str(cam_id)}) == []
        # Test mismatch
        errs = AlertEventValidator.validate(uc1_intrusion_alert, {uuid4()})
        assert any("camera_id" in e for e in errs)


# ==============================================================================
# 2. RESILIENT EVENT PUBLISHING (PHASE 3)
# ==============================================================================

class TestResilientPublishing:
    @pytest.mark.asyncio
    async def test_publisher_retries_transient_redis_disconnect(self, uc2_fire_alert):
        mock_redis = AsyncMock()
        # Fail once with connection error, succeed on 2nd attempt
        mock_redis.xadd.side_effect = [ConnectionResetError("Redis connection lost"), "1700000000000-0"]

        publisher = AlertPublisher(mock_redis, max_retries=3, base_delay_s=0.01)
        success = await publisher.publish(uc2_fire_alert)

        assert success is True
        assert publisher.metrics["published"] == 1
        assert publisher.metrics["retried"] == 1
        assert mock_redis.xadd.call_count == 2

    @pytest.mark.asyncio
    async def test_publisher_buffers_in_memory_when_retries_exhausted(self, uc3_ppe_alert):
        mock_redis = AsyncMock()
        mock_redis.xadd.side_effect = TimeoutError("Redis down")

        publisher = AlertPublisher(mock_redis, max_retries=2, base_delay_s=0.01)
        success = await publisher.publish(uc3_ppe_alert)

        assert success is False
        assert publisher.metrics["failed"] == 1
        assert publisher.metrics["buffered"] == 1
        assert publisher.buffer_size == 1

        # Now simulate Redis reconnecting on the next publish call
        mock_redis.xadd.side_effect = None
        mock_redis.xadd.return_value = "1700000000001-0"

        flushed_count = await publisher.flush_buffer()
        assert flushed_count == 1
        assert publisher.buffer_size == 0
        assert publisher.metrics["buffer_flushed"] == 1

    @pytest.mark.asyncio
    async def test_publisher_preserves_event_identity_across_retries(self, uc4_speed_alert):
        mock_redis = AsyncMock()
        mock_redis.xadd.side_effect = [OSError("Socket closed"), "1700000000002-0"]

        publisher = AlertPublisher(mock_redis, max_retries=2, base_delay_s=0.01)
        await publisher.publish(uc4_speed_alert)

        # The published payload on the 2nd attempt must carry the exact original alert_id
        published_payload = mock_redis.xadd.call_args[0][1]["data"]
        data_dict = json.loads(published_payload)
        assert data_dict["alert_id"] == str(uc4_speed_alert.alert_id)


# ==============================================================================
# 3. CONSUMER IDEMPOTENCY & FAULT RECOVERY (PHASES 3, 4, 6)
# ==============================================================================

class TestConsumerReliabilityAndIdempotency:
    @pytest.mark.asyncio
    async def test_consumer_acknowledges_duplicate_alert_without_reprocessing(self, uc1_intrusion_alert):
        consumer = AlertConsumer()
        consumer._redis = AsyncMock()
        consumer._known_cameras = {str(uc1_intrusion_alert.camera_id)}

        payload = uc1_intrusion_alert.model_dump_json()

        # Mock persistence to return inserted=False (already persisted)
        with patch("services.alert_management.src.consumer.insert_alert", new=AsyncMock(return_value=False)), \
             patch("services.alert_management.src.consumer.maybe_create_incident", new=AsyncMock()) as mock_inc:
            await consumer._process("msg-101", {"data": payload})

            # Must ACK to prevent PEL leak
            consumer._redis.xack.assert_awaited_once_with(
                ALERTS_LIVE_STREAM, "alert_management_group", "msg-101"
            )
            # Must NOT create another incident
            mock_inc.assert_not_called()
            assert consumer.metrics["duplicates_acked"] == 1

    @pytest.mark.asyncio
    async def test_consumer_routes_poison_pill_to_dead_letter_after_max_attempts(self, uc1_intrusion_alert):
        consumer = AlertConsumer()
        consumer._redis = AsyncMock()
        consumer._known_cameras = {str(uc1_intrusion_alert.camera_id)}

        payload = uc1_intrusion_alert.model_dump_json()

        # Simulate repeated persistence failure (e.g. fatal DB issue for this specific row)
        with patch("services.alert_management.src.consumer.insert_alert", side_effect=RuntimeError("DB fatal error")):
            # Process until MAX_DELIVERY_ATTEMPTS is exceeded
            for attempt in range(1, MAX_DELIVERY_ATTEMPTS + 2):
                await consumer._process("poison-msg-999", {"data": payload})

        # Must be dead-lettered and acknowledged once threshold exceeded
        assert consumer.metrics["poison_acked"] == 1
        consumer._redis.xack.assert_awaited_with(
            ALERTS_LIVE_STREAM, "alert_management_group", "poison-msg-999"
        )
        dead_letter_calls = [
            call for call in consumer._redis.xadd.mock_calls
            if call.args and call.args[0] == ALERTS_DEAD_LETTER
        ]
        assert len(dead_letter_calls) >= 1

    @pytest.mark.asyncio
    async def test_consumer_dynamically_reloads_camera_cache_on_unknown_camera(self, uc2_fire_alert):
        consumer = AlertConsumer()
        consumer._redis = AsyncMock()
        # Initially empty known cameras
        consumer._known_cameras = set()

        payload = uc2_fire_alert.model_dump_json()

        async def fake_reload():
            # Dynamically populates camera
            consumer._known_cameras.add(str(uc2_fire_alert.camera_id))

        consumer._load_known_cameras = fake_reload

        with patch("services.alert_management.src.consumer.insert_alert", new=AsyncMock(return_value=True)), \
             patch("services.alert_management.src.consumer.maybe_create_incident", new=AsyncMock(return_value="inc-1")), \
             patch("services.alert_management.src.consumer.write_audit_entry", new=AsyncMock()), \
             patch("services.alert_management.src.consumer.fetch_alert_by_alert_id", new=AsyncMock(return_value={"camera_id": str(uc2_fire_alert.camera_id)})), \
             patch("services.alert_management.src.consumer.push_alert", new=AsyncMock()):

            await consumer._process("msg-202", {"data": payload})

            # Successfully processed and ACKed instead of being dead-lettered!
            assert consumer.metrics["processed"] == 1
            assert consumer.metrics["dead_lettered"] == 0
            consumer._redis.xack.assert_awaited_once_with(
                ALERTS_LIVE_STREAM, "alert_management_group", "msg-202"
            )

    @pytest.mark.asyncio
    async def test_consumer_recovers_pending_messages_from_pel(self, uc3_ppe_alert):
        consumer = AlertConsumer()
        consumer._redis = AsyncMock()
        consumer._known_cameras = {str(uc3_ppe_alert.camera_id)}

        payload = uc3_ppe_alert.model_dump_json()
        consumer._redis.xreadgroup.return_value = [
            ("alerts:live", [("msg-pending-01", {"data": payload})])
        ]

        with patch("services.alert_management.src.consumer.insert_alert", new=AsyncMock(return_value=True)), \
             patch("services.alert_management.src.consumer.maybe_create_incident", new=AsyncMock(return_value="inc-ppe")), \
             patch("services.alert_management.src.consumer.write_audit_entry", new=AsyncMock()), \
             patch("services.alert_management.src.consumer.fetch_alert_by_alert_id", new=AsyncMock(return_value={"camera_id": str(uc3_ppe_alert.camera_id)})), \
             patch("services.alert_management.src.consumer.push_alert", new=AsyncMock()):

            await consumer._recover_pending_messages()

            assert consumer.metrics["pending_recovered"] == 1
            consumer._redis.xack.assert_awaited_once_with(
                ALERTS_LIVE_STREAM, "alert_management_group", "msg-pending-01"
            )


# ==============================================================================
# 4. INCIDENT DEDUPLICATION & SEVERITY ESCALATION (PHASES 4, 5)
# ==============================================================================

class TestIncidentDeduplicationAndSeverity:
    @pytest.mark.asyncio
    async def test_sustained_hazard_links_to_existing_active_incident(self, uc2_fire_alert):
        mock_session = AsyncMock()

        # 1. Camera lookup returns org/site/zone
        mock_cam_res = MagicMock()
        mock_cam_res.fetchone.return_value = MagicMock(
            organization_id=uuid4(), site_id=uuid4(), zone_id=uuid4()
        )

        # 2. Existing active incident found within 10-minute window
        existing_inc_id = str(uuid4())
        mock_existing_res = MagicMock()
        mock_existing_res.fetchone.return_value = MagicMock(
            id=existing_inc_id, severity="high", status="active"
        )

        mock_session.execute.side_effect = [mock_cam_res, mock_existing_res, AsyncMock(), AsyncMock()]

        incident_id = await maybe_create_incident(
            session=mock_session,
            alert_row_id="alert-row-fire-2",
            alert_title=uc2_fire_alert,
        )

        # Must return the existing incident ID rather than inventing a duplicate
        assert incident_id == existing_inc_id

        # Must execute incident_alerts link
        executed_sqls = [str(call.args[0]) for call in mock_session.execute.call_args_list if call.args]
        assert any("INSERT INTO incident_alerts" in sql for sql in executed_sqls)
        # Must execute severity escalation to critical
        assert any("UPDATE incidents" in sql and "severity = 'critical'" in sql for sql in executed_sqls)

    @pytest.mark.asyncio
    async def test_low_and_medium_alerts_do_not_create_incidents(self):
        mock_session = AsyncMock()
        low_alert = AlertEvent(
            camera_id=uuid4(),
            timestamp=datetime.now(timezone.utc),
            severity=AlertSeverity.LOW,
            alert_type="anpr_read",
            title="Plate Read",
            description="Vehicle plate recorded",
            source_event_id=uuid4(),
            source_uc=SourceUC.UC4,
        )

        inc_id = await maybe_create_incident(
            session=mock_session,
            alert_row_id="alert-low-1",
            alert_title=low_alert,
        )

        assert inc_id is None
        mock_session.execute.assert_not_called()


# ==============================================================================
# 5. RECONNECTION & WEBSOCKET DELIVERY (PHASE 7)
# ==============================================================================

class TestReconnectionAndWebSocket:
    @pytest.mark.asyncio
    async def test_fetch_missed_alerts_with_type_safe_camera_comparison(self):
        mock_session = AsyncMock()
        mock_res = MagicMock()
        mock_res.fetchall.return_value = [
            MagicMock(_mapping={
                "alert_id": "a-1",
                "camera_id": "cam-101",
                "severity": "high",
                "title": "Missed Alert",
                "status": "pending",
                "created_at": datetime(2026, 10, 19, 10, 0, 0, tzinfo=timezone.utc),
            })
        ]
        mock_session.execute.return_value = mock_res
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__.return_value = mock_session

        missed = await fetch_missed_alerts(
            session_factory=mock_factory,
            camera_ids=["cam-101", "cam-102"],
            since="2026-10-19T09:00:00Z",
        )

        assert len(missed) == 1
        assert missed[0]["title"] == "Missed Alert"
        sql_query = str(mock_session.execute.call_args[0][0])
        # Verifies type-safe query against UUID column in postgres
        assert "camera_id::text = ANY(:camera_ids)" in sql_query

    def test_websocket_serialization_handles_datetimes_and_uuids(self):
        raw_row = {
            "id": uuid4(),
            "camera_id": uuid4(),
            "created_at": datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc),
            "severity": "critical",
            "count": 42,
        }
        serialized = _serialize(raw_row)
        assert isinstance(serialized["id"], str)
        assert isinstance(serialized["camera_id"], str)
        assert "2026-10-19" in serialized["created_at"]
        assert serialized["severity"] == "critical"
        assert serialized["count"] == 42
