"""
Camera Registry Video Sessions Integration — Coordinates upload validation,
tenant ownership, session state queries, and delegates playback to ingestion.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import re
import urllib.request
import urllib.error
import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}
MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024  # 200 MB
INGESTION_SERVICE_URL = os.environ.get("INGESTION_SERVICE_URL", "http://ingestion:8020")


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
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
    if not clean or clean.startswith("."):
        clean = f"video_{uuid.uuid4().hex[:8]}.mp4"
    return clean


class CameraRegistryVideoSessionCoordinator:
    def __init__(self, redis_client: aioredis.Redis, upload_dir: Optional[str] = None) -> None:
        self._redis = redis_client
        self._upload_dir = Path(upload_dir or (
            "/tmp/innovision_uploads" if os.name != "nt" else os.path.join(os.environ.get("TEMP", "C:\\temp"), "innovision_uploads")
        ))
        self._upload_dir.mkdir(parents=True, exist_ok=True)

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

    async def save_session(self, session_id: str, data: Dict[str, Any]) -> None:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(f"video_session:{session_id}", json.dumps(data))

    async def create_session_from_bytes(
        self,
        camera_id: str,
        organization_id: Optional[str],
        filename: str,
        content: bytes,
        target_fps: float = 10.0,
    ) -> Dict[str, Any]:
        """Validate, store locally and persist video session in Redis."""
        validate_video_file_bytes(filename, content)
        clean_name = sanitize_filename(filename)
        session_id = str(uuid.uuid4())

        local_filename = f"session_{session_id}_{clean_name}"
        local_path = self._upload_dir / local_filename
        with open(local_path, "wb") as f:
            f.write(content)

        now_str = datetime.now(timezone.utc).isoformat()
        session_data: Dict[str, Any] = {
            "session_id": str(session_id),
            "camera_id": str(camera_id),
            "organization_id": str(organization_id) if organization_id else None,
            "original_filename": filename,
            "storage_path": str(local_path),
            "storage_ref": str(local_path),
            "file_size_bytes": len(content),
            "status": "uploaded",
            "fps": float(target_fps),
            "total_frames": 0,
            "processed_frames": 0,
            "error_message": None,
            "effective_analytics": [],
            "created_at": now_str,
            "updated_at": now_str,
        }

        await self.save_session(session_id, session_data)
        await self._redis.sadd(f"camera_video_sessions:{camera_id}", session_id)
        logger.info("registry_session_created session_id=%s camera_id=%s", session_id, camera_id)
        return session_data

    async def create_session_from_existing_test_video(
        self,
        camera_id: str,
        organization_id: Optional[str],
        video_filename: str,
        target_fps: float = 10.0,
    ) -> Dict[str, Any]:
        """Find video in known test directories and create a session."""
        candidate_dirs = [
            Path("test_data/videos"),
            Path("/app/test_data/videos"),
            Path("../test_data/videos"),
        ]
        found_path: Optional[Path] = None
        clean_name = Path(video_filename).name

        for d in candidate_dirs:
            p = d / clean_name
            if p.exists() and p.is_file():
                found_path = p
                break

        if not found_path:
            raise FileNotFoundError(f"Test video '{clean_name}' not found in test_data/videos")

        with open(found_path, "rb") as f:
            content = f.read()

        return await self.create_session_from_bytes(
            camera_id=camera_id,
            organization_id=organization_id,
            filename=clean_name,
            content=content,
            target_fps=target_fps,
        )

    async def call_ingestion_start(
        self,
        session_id: str,
        effective_analytics: List[str],
        fps: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Call Ingestion service to start playback."""
        url = f"{INGESTION_SERVICE_URL}/sessions/start"
        payload = json.dumps({
            "session_id": session_id,
            "effective_analytics": effective_analytics,
            "fps": fps,
        }).encode("utf-8")

        def _do_request():
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            return await asyncio.to_thread(_do_request)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            logger.warning("ingestion_start_http_error code=%d body=%s", e.code, err_body)
            # Try to parse detail
            try:
                msg = json.loads(err_body).get("detail", err_body)
            except Exception:
                msg = err_body
            raise RuntimeError(f"Ingestion service start failed ({e.code}): {msg}")
        except Exception as e:
            logger.warning("ingestion_start_request_failed error=%s", e)
            # Fallback update in Redis
            s = await self.get_session(session_id)
            if s:
                s["status"] = "processing"
                s["effective_analytics"] = effective_analytics
                if fps:
                    s["fps"] = fps
                await self.save_session(session_id, s)
                return s
            raise RuntimeError(f"Could not connect to ingestion service: {e}")

    async def call_ingestion_stop(self, session_id: str) -> Dict[str, Any]:
        """Call Ingestion service to stop playback."""
        url = f"{INGESTION_SERVICE_URL}/sessions/{session_id}/stop"

        def _do_request():
            req = urllib.request.Request(
                url,
                data=b"{}",
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            return await asyncio.to_thread(_do_request)
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            logger.warning("ingestion_stop_http_error code=%d body=%s", e.code, err_body)
            s = await self.get_session(session_id)
            if s:
                s["status"] = "stopped"
                await self.save_session(session_id, s)
                return s
            raise RuntimeError(f"Ingestion stop failed: {err_body}")
        except Exception as e:
            logger.warning("ingestion_stop_request_failed error=%s", e)
            s = await self.get_session(session_id)
            if s:
                s["status"] = "stopped"
                await self.save_session(session_id, s)
                return s
            raise
