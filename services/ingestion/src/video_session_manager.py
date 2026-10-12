"""
Video Session Manager — Handles video upload validation, secure storage,
lifecycle transitions, source-isolated frame streaming, and playback.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import os
from pathlib import Path
import re
import time
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

import cv2
import numpy as np
import redis.asyncio as aioredis
from minio import Minio

from shared.contracts.enums import FrameProvider
from shared.contracts.frame_event import FrameEvent
from services.ingestion.src.config import settings

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB


def validate_video_file_bytes(filename: str, content: bytes, max_size_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
    """Validate video extension, non-empty size, maximum size, and header magic bytes."""
    if not content or len(content) == 0:
        raise ValueError("Video file cannot be empty")

    if len(content) > max_size_bytes:
        raise ValueError(f"Video file exceeds maximum allowed size ({max_size_bytes // (1024 * 1024)} MB)")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported video format: '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}")

    # Magic bytes check
    is_valid_magic = False
    header = content[:32]

    if ext in {".mp4", ".mov"}:
        if len(header) >= 8 and (header[4:8] in (b"ftyp", b"moov", b"wide", b"free") or header[:3] == b"\x00\x00\x00"):
            is_valid_magic = True
    elif ext == ".avi":
        if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"AVI ":
            is_valid_magic = True
    elif ext == ".mkv":
        if header.startswith(b"\x1a\x45\xdf\xa3"):
            is_valid_magic = True

    if not is_valid_magic:
        raise ValueError(f"File '{filename}' content header does not match expected {ext} video signature")


def sanitize_filename(filename: str) -> str:
    """Generate safe alphanumeric filename without path traversal."""
    base = Path(filename).name
    # Keep only alphanumeric, dots, underscores, hyphens
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    if not clean or clean.startswith("."):
        clean = f"video_{uuid.uuid4().hex[:8]}.mp4"
    return clean


class VideoSessionManager:
    def __init__(
        self,
        redis_client: aioredis.Redis,
        minio_client: Optional[Minio] = None,
        upload_dir: Optional[str] = None,
    ) -> None:
        self._redis = redis_client

        self._minio = minio_client
        if self._minio is None and os.environ.get("ENABLE_MINIO_STORAGE", "false").lower() in ("true", "1", "yes"):
            endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
            access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
            secret_key = os.environ.get("MINIO_SECRET_KEY", "InnovisionMinIO_2026")
            secure = os.environ.get("MINIO_SECURE", "false").lower() in ("true", "1", "yes")
            try:
                self._minio = Minio(
                    endpoint=endpoint,
                    access_key=access_key,
                    secret_key=secret_key,
                    secure=secure,
                )
            except Exception as e:
                logger.warning("minio_init_warning error=%s", e)
                self._minio = None

        self._bucket = os.environ.get("MINIO_UPLOADS_BUCKET", "innovision-uploads")
        if self._minio is not None:
            self._ensure_bucket()

        # Local fallback directory for container / host execution
        self._upload_dir = Path(upload_dir or (
            "/tmp/innovision_uploads" if os.name != "nt" else os.path.join(os.environ.get("TEMP", "C:\\temp"), "innovision_uploads")
        ))
        self._upload_dir.mkdir(parents=True, exist_ok=True)

        # Active playback tasks: session_id -> asyncio.Task
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._stop_events: Dict[str, asyncio.Event] = {}

    def _ensure_bucket(self) -> None:
        if self._minio:
            try:
                if not self._minio.bucket_exists(self._bucket):
                    self._minio.make_bucket(self._bucket)
                    logger.info("minio_bucket_created bucket=%s", self._bucket)
            except Exception as e:
                logger.warning("minio_bucket_check_failed error=%s", e)

    async def create_session(
        self,
        camera_id: str,
        organization_id: Optional[str],
        filename: str,
        content: bytes,
        target_fps: float = 10.0,
    ) -> Dict[str, Any]:
        """Validate, store, and persist a new video upload session."""
        validate_video_file_bytes(filename, content)
        clean_name = sanitize_filename(filename)
        session_id = str(uuid.uuid4())

        # 1. Save to local upload dir
        local_filename = f"session_{session_id}_{clean_name}"
        local_path = self._upload_dir / local_filename
        with open(local_path, "wb") as f:
            f.write(content)

        # 2. Upload to MinIO object store if available
        storage_ref = str(local_path)
        if self._minio:
            try:
                object_name = f"uploads/{camera_id}/{session_id}_{clean_name}"
                await asyncio.to_thread(
                    self._minio.put_object,
                    self._bucket,
                    object_name,
                    io.BytesIO(content),
                    len(content),
                    content_type="video/mp4",
                )
                storage_ref = f"minio://{self._bucket}/{object_name}"
                logger.info("session_video_stored_minio object=%s size=%d", object_name, len(content))
            except Exception as e:
                logger.warning("minio_upload_fallback_to_local error=%s", e)

        # 3. Inspect video properties via cv2
        total_frames = 0
        video_fps = target_fps
        try:
            cap = cv2.VideoCapture(str(local_path))
            if cap.isOpened():
                total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                native_fps = cap.get(cv2.CAP_PROP_FPS)
                if native_fps and native_fps > 0:
                    video_fps = min(native_fps, target_fps)
            cap.release()
        except Exception as e:
            logger.warning("cv2_metadata_probe_failed error=%s", e)

        now_str = datetime.now(timezone.utc).isoformat()
        session_data: Dict[str, Any] = {
            "session_id": session_id,
            "camera_id": camera_id,
            "organization_id": organization_id,
            "original_filename": filename,
            "storage_path": str(local_path),
            "storage_ref": storage_ref,
            "file_size_bytes": len(content),
            "status": "uploaded",
            "fps": float(video_fps),
            "total_frames": total_frames,
            "processed_frames": 0,
            "error_message": None,
            "effective_analytics": [],
            "created_at": now_str,
            "updated_at": now_str,
        }

        # Persist session state in Redis
        await self._save_session_state(session_id, session_data)
        await self._redis.sadd(f"camera_video_sessions:{camera_id}", session_id)

        logger.info("video_session_created session_id=%s camera_id=%s file=%s", session_id, camera_id, filename)
        return session_data

    async def create_session_from_existing(
        self,
        camera_id: str,
        organization_id: Optional[str],
        source_path: str,
        original_filename: Optional[str] = None,
        target_fps: float = 10.0,
    ) -> Dict[str, Any]:
        """Create session from pre-existing test video on disk."""
        p = Path(source_path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Video file not found at: {source_path}")

        with open(p, "rb") as f:
            content = f.read()

        fname = original_filename or p.name
        return await self.create_session(
            camera_id=camera_id,
            organization_id=organization_id,
            filename=fname,
            content=content,
            target_fps=target_fps,
        )

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        raw = await self._redis.get(f"video_session:{session_id}")
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)

    async def list_camera_sessions(self, camera_id: str) -> List[Dict[str, Any]]:
        session_ids = await self._redis.smembers(f"camera_video_sessions:{camera_id}")
        sessions: List[Dict[str, Any]] = []
        for sid in session_ids:
            sid_str = sid.decode("utf-8") if isinstance(sid, bytes) else str(sid)
            s = await self.get_session(sid_str)
            if s:
                sessions.append(s)
        sessions.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return sessions

    async def _save_session_state(self, session_id: str, data: Dict[str, Any]) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(f"video_session:{session_id}", json.dumps(data))

    async def start_session_processing(
        self,
        session_id: str,
        effective_analytics: Optional[List[str]] = None,
        playback_fps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Start isolated asynchronous video playback and frame publication."""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Video session '{session_id}' not found")

        # Idempotent start: return existing processing state
        if session.get("status") == "processing" and session_id in self._active_tasks:
            task = self._active_tasks[session_id]
            if not task.done():
                return session

        # Verify source file exists
        local_path = session.get("storage_path")
        if not local_path or not os.path.exists(local_path):
            # Check mounted test_data/videos directory
            orig_fname = session.get("original_filename")
            for c_dir in [Path("/app/test_data/videos"), Path("test_data/videos")]:
                if orig_fname and (c_dir / orig_fname).exists():
                    local_path = str(c_dir / orig_fname)
                    session["storage_path"] = local_path
                    break
            else:
                # Attempt to pull from MinIO if missing on local disk
                if self._minio and session.get("storage_ref", "").startswith("minio://"):
                    ref = session["storage_ref"].replace(f"minio://{self._bucket}/", "")
                    dest = self._upload_dir / f"session_{session_id}.mp4"
                    await asyncio.to_thread(self._minio.fget_object, self._bucket, ref, str(dest))
                    local_path = str(dest)
                    session["storage_path"] = local_path
                else:
                    raise FileNotFoundError(f"Video file '{local_path}' not available for playback")

        fps = playback_fps or float(session.get("fps", 10.0))
        eff_analytics = effective_analytics or session.get("effective_analytics", [])

        session["status"] = "processing"
        session["effective_analytics"] = eff_analytics
        session["fps"] = fps
        session["error_message"] = None
        await self._save_session_state(session_id, session)

        stop_event = asyncio.Event()
        self._stop_events[session_id] = stop_event

        task = asyncio.create_task(
            self._playback_loop(session_id, session["camera_id"], local_path, fps, stop_event),
            name=f"video_session_playback_{session_id}",
        )
        self._active_tasks[session_id] = task

        logger.info("video_session_started session_id=%s camera_id=%s fps=%.1f", session_id, session["camera_id"], fps)
        return session

    async def stop_session(self, session_id: str) -> Dict[str, Any]:
        """Idempotently cancel and stop playback of the specified session."""
        session = await self.get_session(session_id)
        if not session:
            raise ValueError(f"Video session '{session_id}' not found")

        # Signal stop event
        if session_id in self._stop_events:
            self._stop_events[session_id].set()

        # Cancel active task if running
        if session_id in self._active_tasks:
            task = self._active_tasks[session_id]
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._active_tasks.pop(session_id, None)

        self._stop_events.pop(session_id, None)

        session["status"] = "stopped"
        await self._save_session_state(session_id, session)
        logger.info("video_session_stopped session_id=%s", session_id)
        return session

    async def _playback_loop(
        self,
        session_id: str,
        camera_id: str,
        video_path: str,
        fps: float,
        stop_event: asyncio.Event,
    ) -> None:
        """Asynchronous frame decoding, rate-limiting, and dual-routing publication."""
        target_fps = max(1.0, min(30.0, fps))
        frame_interval = 1.0 / target_fps
        frame_seq = 0

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.error("cv2_open_failed path=%s", video_path)
            s = await self.get_session(session_id)
            if s:
                s["status"] = "failed"
                s["error_message"] = "Failed to open video file for decoding"
                await self._save_session_state(session_id, s)
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        session_stream_key = f"frames:{camera_id}:session:{session_id}"
        live_mirror_stream_key = f"frames:{camera_id}"

        try:
            while not stop_event.is_set():
                start_time = time.monotonic() if hasattr(time, "monotonic") else 0.0

                ret, frame = cap.read()
                if not ret or frame is None:
                    # Video reached end of file
                    logger.info("video_session_eof session_id=%s total_frames=%d", session_id, frame_seq)
                    break

                frame_seq += 1
                h, w = frame.shape[:2]

                # 1. Encode JPEG
                _, jpeg_bytes = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                raw_bytes = jpeg_bytes.tobytes()

                # 2. Cache in Redis with isolated session key
                cache_key = f"frame:{camera_id}:session:{session_id}:{frame_seq}"
                await self._redis.set(cache_key, raw_bytes, ex=300)

                # 3. Construct source-isolated FrameEvent
                event = FrameEvent(
                    camera_id=UUID(camera_id),
                    frame_seq=frame_seq,
                    timestamp=datetime.now(timezone.utc),
                    frame_provider=FrameProvider.REDIS,
                    frame_reference=cache_key,
                    frame_shape=(h, w),
                    source_type="uploaded_video",
                    session_id=UUID(session_id),
                )
                payload = event.model_dump_json()

                # 4. Route to dedicated session stream
                await self._redis.xadd(
                    session_stream_key,
                    {"data": payload},
                    maxlen=1000,
                    approximate=True,
                )

                # 5. Mirror to camera stream for entitlement-evaluated analytics consumption
                await self._redis.xadd(
                    live_mirror_stream_key,
                    {"data": payload},
                    maxlen=1000,
                    approximate=True,
                )

                # 6. Periodic progress update
                if frame_seq % 10 == 0 or frame_seq == 1:
                    s = await self.get_session(session_id)
                    if s:
                        s["processed_frames"] = frame_seq
                        if total_frames > 0:
                            s["total_frames"] = total_frames
                        await self._save_session_state(session_id, s)

                # 7. Apply rate-limiting & backpressure
                elapsed = (time.monotonic() - start_time) if hasattr(time, "monotonic") else 0.0
                delay = max(0.001, frame_interval - elapsed)
                await asyncio.sleep(delay)

            # Mark completion
            s = await self.get_session(session_id)
            if s:
                s["processed_frames"] = frame_seq
                if total_frames > 0:
                    s["total_frames"] = total_frames
                if not stop_event.is_set():
                    s["status"] = "completed"
                else:
                    s["status"] = "stopped"
                await self._save_session_state(session_id, s)

        except asyncio.CancelledError:
            s = await self.get_session(session_id)
            if s:
                s["status"] = "stopped"
                await self._save_session_state(session_id, s)
            raise

        except Exception as e:
            logger.exception("video_session_playback_error session_id=%s", session_id)
            s = await self.get_session(session_id)
            if s:
                s["status"] = "failed"
                s["error_message"] = str(e)
                await self._save_session_state(session_id, s)

        finally:
            cap.release()
            self._active_tasks.pop(session_id, None)
            self._stop_events.pop(session_id, None)
            logger.info("video_session_playback_finished session_id=%s frames=%d", session_id, frame_seq)
