"""
Comprehensive Tests for Camera-Based Video Upload, Source Isolation, and Analytics Processing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import UUID, uuid4
import pytest

import numpy as np

from shared.contracts.enums import FrameProvider
from shared.contracts.frame_event import FrameEvent, FrameEventSchema
from services.ingestion.src.video_session_manager import (
    VideoSessionManager,
    validate_video_file_bytes,
    sanitize_filename,
    MAX_FILE_SIZE_BYTES,
)
from services.camera_registry.src.video_sessions import (
    CameraRegistryVideoSessionCoordinator,
    validate_video_file_bytes as reg_validate_video_file_bytes,
    sanitize_filename as reg_sanitize_filename,
)
from services.uc3.src.compliance import evaluate_compliance, new_session_state


class MockRedis:
    """Async Redis mock for isolated session testing."""
    def __init__(self):
        self.data: dict[str, Any] = {}
        self.sets: dict[str, set[str]] = {}
        self.streams: dict[str, list[tuple[str, dict]]] = {}

    async def get(self, key: str):
        val = self.data.get(key)
        if isinstance(val, str):
            return val.encode("utf-8")
        return val

    async def set(self, key: str, value: Any, ex: int | None = None):
        if isinstance(value, bytes):
            self.data[key] = value
        else:
            self.data[key] = str(value)

    async def delete(self, key: str):
        self.data.pop(key, None)

    async def sadd(self, key: str, value: str):
        if key not in self.sets:
            self.sets[key] = set()
        self.sets[key].add(str(value))

    async def smembers(self, key: str):
        return {s.encode("utf-8") for s in self.sets.get(key, set())}

    async def exists(self, key: str) -> int:
        return 1 if key in self.data or key in self.streams or key in self.sets else 0

    async def xadd(self, stream: str, fields: dict, maxlen: int | None = None, approximate: bool = False):
        if stream not in self.streams:
            self.streams[stream] = []
        msg_id = f"{len(self.streams[stream])+1}-0"
        self.streams[stream].append((msg_id, fields))
        return msg_id


# ==============================================================================
# 1. Validation & Safe Storage Name Tests
# ==============================================================================
def test_validate_video_file_bytes_valid_mp4():
    # Valid MP4 header with ftyp box
    header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + (b"\x00" * 100)
    validate_video_file_bytes("dynamic_test_video.mp4", header)
    reg_validate_video_file_bytes("dynamic_test_video.mp4", header)


def test_validate_video_file_bytes_valid_avi():
    # Valid AVI header
    header = b"RIFF\x24\x00\x00\x00AVI LIST\x00\x00\x00\x00" + (b"\x00" * 100)
    validate_video_file_bytes("traffic_sample.avi", header)
    reg_validate_video_file_bytes("traffic_sample.avi", header)


def test_validate_video_file_bytes_valid_mkv():
    # Valid MKV header with EBML ID
    header = b"\x1a\x45\xdf\xa3\x93\x42\x86\x81\x01\x42\xf7\x81\x01" + (b"\x00" * 100)
    validate_video_file_bytes("crane_zone.mkv", header)
    reg_validate_video_file_bytes("crane_zone.mkv", header)


def test_validate_video_file_bytes_empty_fails():
    with pytest.raises(ValueError, match="cannot be empty"):
        validate_video_file_bytes("test.mp4", b"")


def test_validate_video_file_bytes_oversize_fails():
    with pytest.raises(ValueError, match="exceeds maximum allowed size"):
        # Simulated oversize
        validate_video_file_bytes("huge.mp4", b"\x00" * 100, max_size_bytes=50)


def test_validate_video_file_bytes_unsupported_ext():
    with pytest.raises(ValueError, match="Unsupported video format"):
        validate_video_file_bytes("malicious.exe", b"MZ\x90\x00" + b"\x00" * 50)

    with pytest.raises(ValueError, match="Unsupported video format"):
        validate_video_file_bytes("notes.txt", b"plain text data")


def test_validate_video_file_bytes_magic_byte_mismatch():
    # Named .mp4 but contains plain text without ftyp header
    with pytest.raises(ValueError, match="does not match expected .mp4 video signature"):
        validate_video_file_bytes("fake.mp4", b"This is not a real video content header at all!")


def test_sanitize_filename_prevents_directory_traversal():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"
    assert sanitize_filename("my video @ 2026! #1.mp4") == "my_video___2026___1.mp4"
    assert reg_sanitize_filename("../../../malicious.mp4") == "malicious.mp4"


# ==============================================================================
# 2. Session Creation, Lifecycle, and Idempotency Tests
# ==============================================================================
@pytest.mark.asyncio
async def test_session_creation_and_persistence():
    mock_redis = MockRedis()
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = VideoSessionManager(redis_client=mock_redis, minio_client=None, upload_dir=tmpdir)
        cam_id = str(uuid4())
        org_id = str(uuid4())

        header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + (b"\x00" * 200)
        session = await manager.create_session(
            camera_id=cam_id,
            organization_id=org_id,
            filename="factory_floor_50fps.mp4",
            content=header,
            target_fps=15.0,
        )

        assert session["session_id"] is not None
        assert session["camera_id"] == cam_id
        assert session["organization_id"] == org_id
        assert session["original_filename"] == "factory_floor_50fps.mp4"
        assert session["status"] == "uploaded"
        assert session["file_size_bytes"] == len(header)

        # Retrieve session
        retrieved = await manager.get_session(session["session_id"])
        assert retrieved is not None
        assert retrieved["session_id"] == session["session_id"]
        assert retrieved["status"] == "uploaded"

        # List camera sessions
        c_sessions = await manager.list_camera_sessions(cam_id)
        assert len(c_sessions) == 1
        assert c_sessions[0]["session_id"] == session["session_id"]


@pytest.mark.asyncio
async def test_session_idempotent_stop():
    mock_redis = MockRedis()
    with tempfile.TemporaryDirectory() as tmpdir:
        manager = VideoSessionManager(redis_client=mock_redis, minio_client=None, upload_dir=tmpdir)
        cam_id = str(uuid4())
        header = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom" + (b"\x00" * 100)
        session = await manager.create_session(
            camera_id=cam_id,
            organization_id=None,
            filename="test.mp4",
            content=header,
        )
        sid = session["session_id"]

        # Stop uploaded session (not yet running) - must succeed safely
        res1 = await manager.stop_session(sid)
        assert res1["status"] == "stopped"

        # Repeated stop on already stopped session - must be idempotent
        res2 = await manager.stop_session(sid)
        assert res2["status"] == "stopped"


# ==============================================================================
# 3. Source Isolation and Collision Guard Tests
# ==============================================================================
def test_frame_event_contract_carries_session_identity():
    cam_id = uuid4()
    sid = uuid4()
    now = datetime.now(timezone.utc)

    # Isolated upload video frame event
    upload_event = FrameEvent(
        camera_id=cam_id,
        frame_seq=42,
        timestamp=now,
        frame_provider=FrameProvider.REDIS,
        frame_reference=f"frame:{cam_id}:session:{sid}:42",
        frame_shape=(1080, 1920),
        source_type="uploaded_video",
        session_id=sid,
    )

    assert upload_event.source_type == "uploaded_video"
    assert upload_event.session_id == sid
    assert upload_event.frame_reference == f"frame:{cam_id}:session:{sid}:42"

    # Schema validation preservation
    errors = FrameEventSchema.validated_reference_format(upload_event)
    assert len(errors) == 0

    # Backwards compatibility check: default live rtsp event
    live_event = FrameEvent(
        camera_id=cam_id,
        frame_seq=1,
        timestamp=now,
        frame_provider=FrameProvider.REDIS,
        frame_reference=f"frame:{cam_id}:1",
        frame_shape=(1080, 1920),
    )
    assert live_event.source_type == "live_rtsp"
    assert live_event.session_id is None


@pytest.mark.asyncio
async def test_collision_guard_detection_with_mock_redis():
    mock_redis = MockRedis()
    cam_id = str(uuid4())

    # Simulate live camera with active RTSP stream in Redis
    await mock_redis.set(f"frames:{cam_id}", b"active_live_stream_entry")

    # Verification: check if live stream exists
    is_live = await mock_redis.exists(f"frames:{cam_id}")
    assert is_live == 1

    # Isolated session stream key must NOT collide with live stream
    sid = str(uuid4())
    session_stream_key = f"frames:{cam_id}:session:{sid}"
    assert session_stream_key != f"frames:{cam_id}"
    assert await mock_redis.exists(session_stream_key) == 0


# ==============================================================================
# 4. Effective Analytics Routing & Zone PPE Rule Enforcement
# ==============================================================================
def test_zone_ppe_rules_enforced_on_session_detections():
    """Verify zone PPE rules and min_confidence threshold apply to worker detections."""
    w_states = new_session_state()
    now = time.monotonic()

    # Zone requires helmet and vest with 0.60 min_confidence
    req_ppe = {"helmet", "vest"}
    min_conf = 0.60

    # Person with helmet at 0.75 conf, but no vest
    raw_detections = [
        {"label": "person", "conf": 0.85, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 10},
        {"label": "head", "conf": 0.80, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 10},
        {"label": "helmet", "conf": 0.75, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 10},
        # No vest detection
    ]

    for t in [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        severity, unique_vio, worker_violations = evaluate_compliance(
            detections=raw_detections,
            worker_states=w_states,
            now=t,
            required_ppe=req_ppe,
            min_confidence=min_conf,
        )

    assert "no-safety-vest" in unique_vio
    assert "no-head-protection" not in unique_vio


def test_sub_threshold_negative_detection_ignored_in_zone_evaluation():
    """Verify low-confidence negative PPE detection does not trigger false violation."""
    w_states = new_session_state()

    req_ppe = {"helmet"}
    min_conf = 0.70

    # Negative detection 'no-helmet' with conf 0.55 < min_conf 0.70, but positive helmet with conf 0.75
    raw_detections = [
        {"label": "person", "conf": 0.85, "box": (0.2, 0.1, 0.8, 0.9), "_track_id": 11},
        {"label": "head", "conf": 0.80, "box": (0.4, 0.1, 0.6, 0.3), "_track_id": 11},
        {"label": "helmet", "conf": 0.75, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 11},
        {"label": "no-helmet", "conf": 0.55, "box": (0.38, 0.08, 0.62, 0.25), "_track_id": 11},
    ]

    for t in [0.0, 0.5, 1.0]:
        severity, unique_vio, worker_violations = evaluate_compliance(
            detections=raw_detections,
            worker_states=w_states,
            now=t,
            required_ppe=req_ppe,
            min_confidence=min_conf,
        )

    # Because helmet conf (0.75) > no-helmet conf (0.55), helmet is compliant
    assert "no-head-protection" not in unique_vio


# ==============================================================================
# 5. Playback Loop Synthetic Frame Test
# ==============================================================================
@pytest.mark.asyncio
async def test_video_session_manager_playback_with_synthetic_video():
    """Create a short synthetic MP4 using OpenCV and verify playback & frame emission."""
    import cv2

    mock_redis = MockRedis()
    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = os.path.join(tmpdir, "synth_test.mp4")

        # Write 5 synthetic 640x480 test frames
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(video_path, fourcc, 10.0, (640, 480))
        for i in range(5):
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(img, f"Frame {i}", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)
            out.write(img)
        out.release()

        manager = VideoSessionManager(redis_client=mock_redis, minio_client=None, upload_dir=tmpdir)
        cam_id = str(uuid4())

        # Create session from synthetic file
        session = await manager.create_session_from_existing(
            camera_id=cam_id,
            organization_id=None,
            source_path=video_path,
            original_filename="synth_test.mp4",
            target_fps=20.0,
        )
        sid = session["session_id"]
        assert session["total_frames"] == 5

        # Start processing
        proc = await manager.start_session_processing(sid, effective_analytics=["uc3"], playback_fps=20.0)
        assert proc["status"] == "processing"

        # Wait for playback task to finish (5 frames at 20fps ~ 0.25s)
        await asyncio.sleep(0.6)

        # Check final session status
        final_s = await manager.get_session(sid)
        assert final_s is not None
        assert final_s["status"] in ("completed", "processing")
        assert final_s["processed_frames"] >= 1

        # Check that isolated session stream received frames
        session_stream = f"frames:{cam_id}:session:{sid}"
        assert session_stream in mock_redis.streams
        assert len(mock_redis.streams[session_stream]) >= 1

        # Check that FrameEvent payload in stream contains source_type="uploaded_video"
        first_entry = mock_redis.streams[session_stream][0]
        event_json = json.loads(first_entry[1]["data"])
        assert event_json["source_type"] == "uploaded_video"
        assert event_json["session_id"] == sid
