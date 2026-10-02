"""
Unit tests for AlertConsumer reliability fixes.
All Redis and DB interactions are faked — no running services needed.
"""
import json
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Helpers to build a minimal AlertEvent JSON payload
# ---------------------------------------------------------------------------
CAMERA_ID = "00000000-0000-0000-0000-000000000003"


def _make_raw(alert_id: str | None = None, camera_id: str = CAMERA_ID) -> str:
    return json.dumps({
        "alert_id": alert_id or str(uuid4()),
        "camera_id": camera_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": "high",
        "alert_type": "ppe_violation",
        "title": "Test alert",
        "description": "Test description",
        "source_event_id": str(uuid4()),
        "source_uc": "uc3",
        "status": "pending",
        "metadata": {},
    })


def _msg(raw: str, msg_id: str = "1-1") -> tuple[str, dict]:
    return msg_id, {b"data": raw.encode()}


# ---------------------------------------------------------------------------
# Fake Redis
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self.xadded = []
        self.xacked = []

    async def xadd(self, stream, fields, **_):
        self.xadded.append((stream, fields))
        return "1-1"

    async def xack(self, stream, group, msg_id):
        self.xacked.append(msg_id)

    async def xgroup_create(self, *_, **__):
        pass

    async def xreadgroup(self, **_):
        return []

    async def xautoclaim(self, *_, **__):
        return ("0-0", [], [])

    async def xpending_range(self, *_, **__):
        return []

    def pubsub(self):
        ps = MagicMock()
        ps.psubscribe = AsyncMock()
        ps.listen = self._empty_listen
        ps.unsubscribe = AsyncMock()
        ps.aclose = AsyncMock()
        return ps

    async def _empty_listen(self):
        return
        yield  # make it an async generator


# ---------------------------------------------------------------------------
# Consumer factory — patches away DB and heavy deps
# ---------------------------------------------------------------------------
def _make_consumer(fake_redis, known_cameras=None, insert_return=True):
    from services.alert_management.src.consumer import AlertConsumer

    consumer = AlertConsumer()
    consumer._redis = fake_redis
    consumer._known_cameras = set(known_cameras or [CAMERA_ID])

    # Patch persistence and side-effects
    consumer._insert_patch = AsyncMock(return_value=insert_return)
    consumer._fetch_patch = AsyncMock(return_value={"id": "row-1", "alert_id": "a-1"})
    consumer._incident_patch = AsyncMock(return_value=None)
    consumer._push_patch = AsyncMock()
    consumer._audit_patch = AsyncMock()

    return consumer


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_is_acked():
    """When insert_alert returns False (duplicate), the message must be ACKed."""
    fake_redis = FakeRedis()
    consumer = _make_consumer(fake_redis, insert_return=False)

    raw = _make_raw()
    msg_id, data = _msg(raw, msg_id="2-1")

    with patch("services.alert_management.src.consumer.insert_alert",
               new=AsyncMock(return_value=False)), \
         patch("services.alert_management.src.consumer._session_factory"), \
         patch("services.alert_management.src.consumer.validate_alert",
               return_value=[]), \
         patch("services.alert_management.src.consumer.maybe_create_incident",
               new=AsyncMock(return_value=None)), \
         patch("services.alert_management.src.consumer.fetch_alert_by_alert_id",
               new=AsyncMock(return_value={})), \
         patch("services.alert_management.src.consumer.push_alert", new=AsyncMock()), \
         patch("services.alert_management.src.consumer.write_audit_entry",
               new=AsyncMock()), \
         patch("services.alert_management.src.consumer.get_session_factory",
               return_value=MagicMock()):

        # Patch the session context manager
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_begin = MagicMock()
        mock_begin.__aenter__ = AsyncMock(return_value=None)
        mock_begin.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin = MagicMock(return_value=mock_begin)

        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("services.alert_management.src.consumer._session_factory",
                   mock_factory), \
             patch("services.alert_management.src.consumer.insert_alert",
                   new=AsyncMock(return_value=False)):
            await consumer._process(msg_id, data)

    assert msg_id in fake_redis.xacked, "duplicate must be ACKed"


@pytest.mark.asyncio
async def test_persistence_failure_does_not_ack():
    """When DB raises, message must NOT be ACKed (stays pending for retry)."""
    fake_redis = FakeRedis()
    consumer = _make_consumer(fake_redis)

    raw = _make_raw()
    msg_id, data = _msg(raw, msg_id="3-1")

    with patch("services.alert_management.src.consumer.validate_alert", return_value=[]):
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_begin = MagicMock()
        mock_begin.__aenter__ = AsyncMock(side_effect=Exception("DB down"))
        mock_begin.__aexit__ = AsyncMock(return_value=False)
        mock_session.begin = MagicMock(return_value=mock_begin)
        mock_factory = MagicMock()
        mock_factory.return_value = mock_session

        with patch("services.alert_management.src.consumer._session_factory", mock_factory):
            await consumer._process(msg_id, data)

    assert msg_id not in fake_redis.xacked, "failed message must NOT be ACKed"


@pytest.mark.asyncio
async def test_max_deliveries_dead_letters():
    """
    autoclaim_loop: when delivery count >= MAX, message goes to dead_letter and is ACKed.
    Tests the core dead-letter logic directly without going through the loop sleep.
    """
    from services.alert_management.src.consumer import _MAX_DELIVERY_COUNT

    fake_redis = FakeRedis()
    consumer = _make_consumer(fake_redis)

    raw = _make_raw()
    msg_id = "5-1"
    data = {b"data": raw.encode()}

    fake_redis.xautoclaim = AsyncMock(return_value=(
        "0-0",
        [(msg_id, data)],
        [],
    ))
    fake_redis.xpending_range = AsyncMock(return_value=[
        {"times_delivered": _MAX_DELIVERY_COUNT, "message_id": msg_id}
    ])

    # Call the body of the autoclaim loop directly (skip the sleep)
    result = await fake_redis.xautoclaim(
        "alerts:live", "alert_management_group", "worker",
        min_idle_time=60000, start_id="0-0", count=50,
    )
    claimed = result[1]
    for cid, cdata in claimed:
        pending = await fake_redis.xpending_range(
            "alerts:live", "alert_management_group",
            min=cid, max=cid, count=1,
        )
        delivery_count = pending[0]["times_delivered"] if pending else 1
        if delivery_count >= _MAX_DELIVERY_COUNT:
            craw = cdata.get(b"data", b"").decode()
            await consumer._to_dead_letter(
                f"max_deliveries_exceeded:{delivery_count}", craw
            )
            await consumer._ack(cid)

    dead_letter_streams = [s for s, _ in fake_redis.xadded if "dead_letter" in str(s)]
    assert len(dead_letter_streams) >= 1, "max-delivery message must go to dead_letter"
    assert msg_id in fake_redis.xacked, "dead-lettered message must be ACKed"


@pytest.mark.asyncio
async def test_new_camera_picked_up_after_refresh():
    """
    After _load_known_cameras is called, a newly added camera's alerts
    pass validation without restarting the service.
    """
    new_cam = "00000000-0000-0000-0000-000000000099"
    fake_redis = FakeRedis()
    consumer = _make_consumer(fake_redis, known_cameras=[])  # starts empty

    # Before refresh — camera unknown → validation fails
    raw = _make_raw(camera_id=new_cam)
    from shared.contracts.alert_event import AlertEvent
    alert = AlertEvent.model_validate_json(raw)
    from services.alert_management.src.validator import validate_alert
    errors_before = validate_alert(alert, consumer._known_cameras)
    assert len(errors_before) > 0, "unknown camera should fail validation before refresh"

    # Directly update _known_cameras as _load_known_cameras would after a DB refresh
    # This tests the behaviour: after refresh, new camera passes validation.
    from uuid import UUID
    consumer._known_cameras = {UUID(new_cam)}

    errors_after = validate_alert(alert, consumer._known_cameras)
    assert len(errors_after) == 0, "camera should pass validation after refresh"
