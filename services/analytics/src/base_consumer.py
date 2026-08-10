"""
Base Consumer — abstract base class for all UC analytics workers.

Handles:
- Fetching assigned camera IDs from the ``cameras`` table.
- Creating Redis Consumer Groups on per-camera ``frames:{camera_id}`` streams.
- The XREADGROUP → deserialise → fetch frame → process → XACK loop.
- Alert emission via ``AlertPublisher`` with snapshot upload to MinIO.
"""

from __future__ import annotations

import abc
import asyncio
import io
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import numpy as np
import redis.asyncio as aioredis
from minio import Minio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import FrameProvider, SourceUC
from shared.contracts.frame_event import FrameEvent
from shared.platform_client.alert_publisher import AlertPublisher

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────

MINIO_FRAMES_BUCKET = "innovision-frames"
MINIO_SNAPSHOTS_BUCKET = "innovision-snapshots"


class BaseConsumer(abc.ABC):
    """
    Abstract consumer that each UC worker extends.

    Subclasses must implement:
        - ``source_uc``      (class-level SourceUC enum)
        - ``process_frame()`` (inference / detection logic)
    """

    source_uc: SourceUC  # set by subclass

    def __init__(self) -> None:
        # ── Config from environment ───────────────────────────────────
        self._redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        self._database_url = os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform",
        )
        self._minio_endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
        self._minio_access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
        self._minio_secret_key = os.environ.get("MINIO_SECRET_KEY", "changeme")
        self._minio_secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"

        self._group_name = f"{self.source_uc.value}_analytics_group"
        self._consumer_name = f"{self.source_uc.value}_worker_1"

        # Initialised in ``start()``
        self._redis: Optional[aioredis.Redis] = None
        self._minio: Optional[Minio] = None
        self._db_engine = None
        self._publisher: Optional[AlertPublisher] = None
        self._camera_ids: list[UUID] = []

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Initialise connections and begin consuming."""
        self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
        self._db_engine = create_async_engine(self._database_url, pool_size=3)
        self._minio = Minio(
            endpoint=self._minio_endpoint,
            access_key=self._minio_access_key,
            secret_key=self._minio_secret_key,
            secure=self._minio_secure,
        )
        self._publisher = AlertPublisher(self._redis)

        # Fetch assigned cameras
        self._camera_ids = await self._fetch_camera_ids()
        logger.info(
            "%s_consumer_started cameras=%s group=%s",
            self.source_uc.value,
            [str(c) for c in self._camera_ids],
            self._group_name,
        )

        # Create consumer groups
        for cam_id in self._camera_ids:
            stream = f"frames:{cam_id}"
            try:
                await self._redis.xgroup_create(
                    stream, self._group_name, id="0", mkstream=True
                )
            except Exception:
                # BUSYGROUP — group already exists
                pass

        # Spawn a consumer task per camera
        tasks = [
            asyncio.create_task(
                self._consume_loop(cam_id), name=f"{self.source_uc.value}-{cam_id}"
            )
            for cam_id in self._camera_ids
        ]
        await asyncio.gather(*tasks)

    async def _fetch_camera_ids(self) -> list[UUID]:
        """Query cameras table for cameras assigned to this UC."""
        session_factory = async_sessionmaker(self._db_engine, expire_on_commit=False)
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "SELECT id FROM cameras "
                    "WHERE :uc = ANY(use_cases) AND status != 'disabled'"
                ),
                {"uc": self.source_uc.value},
            )
            return [
                row.id if isinstance(row.id, UUID) else UUID(str(row.id))
                for row in result.fetchall()
            ]

    # ── Consumer loop ─────────────────────────────────────────────────

    async def _consume_loop(self, camera_id: UUID) -> None:
        """XREADGROUP loop for a single camera stream."""
        stream = f"frames:{camera_id}"
        logger.info(
            "%s_consumer_loop_started stream=%s", self.source_uc.value, stream
        )

        while True:
            try:
                messages = await self._redis.xreadgroup(
                    groupname=self._group_name,
                    consumername=self._consumer_name,
                    streams={stream: ">"},
                    count=5,
                    block=2000,
                )

                if not messages:
                    continue

                for _stream_name, entries in messages:
                    for msg_id, data in entries:
                        await self._process_message(camera_id, stream, msg_id, data)

            except asyncio.CancelledError:
                logger.info("%s_consumer_cancelled stream=%s", self.source_uc.value, stream)
                return
            except Exception as exc:
                logger.error(
                    "%s_consumer_error stream=%s error=%s",
                    self.source_uc.value,
                    stream,
                    exc,
                )
                await asyncio.sleep(1)

    async def _process_message(
        self, camera_id: UUID, stream: str, msg_id, data: dict
    ) -> None:
        """Deserialise event, fetch frame, run inference, then ACK."""
        raw = data.get(b"data") or data.get("data")
        if isinstance(raw, bytes):
            raw = raw.decode()

        try:
            event = FrameEvent.model_validate_json(raw)
        except Exception as exc:
            logger.error(
                "%s_frame_event_invalid msg_id=%s error=%s",
                self.source_uc.value,
                msg_id,
                exc,
            )
            await self._redis.xack(stream, self._group_name, msg_id)
            return

        # Fetch frame bytes from MinIO (primary) or Redis (fallback)
        frame_bytes = await self._fetch_frame(event)
        if frame_bytes is None:
            logger.warning(
                "%s_frame_fetch_failed ref=%s",
                self.source_uc.value,
                event.frame_reference,
            )
            await self._redis.xack(stream, self._group_name, msg_id)
            return

        # Decode JPEG → numpy array
        frame = np.frombuffer(frame_bytes, dtype=np.uint8)
        import cv2
        frame = cv2.imdecode(frame, cv2.IMREAD_COLOR)

        # Run UC-specific inference
        try:
            await self.process_frame(event, frame)
        except Exception as exc:
            logger.exception(
                "%s_process_frame_error camera_id=%s seq=%d",
                self.source_uc.value,
                camera_id,
                event.frame_seq,
            )

        # ACK only after processing is complete
        await self._redis.xack(stream, self._group_name, msg_id)

    async def _fetch_frame(self, event: FrameEvent) -> Optional[bytes]:
        """Fetch frame bytes from MinIO or fall back to Redis cache."""
        if event.frame_provider == FrameProvider.MINIO:
            try:
                response = await asyncio.to_thread(
                    self._minio.get_object,
                    MINIO_FRAMES_BUCKET,
                    event.frame_reference,
                )
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except Exception as exc:
                logger.warning(
                    "minio_fetch_failed ref=%s error=%s — trying redis cache",
                    event.frame_reference,
                    exc,
                )

        # Fallback: Redis cache
        if event.frame_provider == FrameProvider.REDIS or True:
            cached = await self._redis.get(f"frame_cache:{event.frame_reference}")
            if cached:
                return cached

        return None

    # ── Alert helpers ─────────────────────────────────────────────────

    async def emit_alert(
        self,
        alert: AlertEvent,
        snapshot_bytes: Optional[bytes] = None,
    ) -> bool:
        """
        Publish an alert via the shared ``AlertPublisher``.

        If *snapshot_bytes* is provided, uploads the snapshot to the
        ``innovision-snapshots`` bucket and populates the frame fields.
        """
        if snapshot_bytes is not None:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            snap_key = (
                f"{self.source_uc.value}/alerts/{date_str}/{alert.alert_id}.jpg"
            )
            try:
                await asyncio.to_thread(
                    self._minio.put_object,
                    MINIO_SNAPSHOTS_BUCKET,
                    snap_key,
                    io.BytesIO(snapshot_bytes),
                    len(snapshot_bytes),
                    "image/jpeg",
                )
                # Reconstruct alert with frame reference (frozen model)
                alert = AlertEvent(
                    alert_id=alert.alert_id,
                    camera_id=alert.camera_id,
                    timestamp=alert.timestamp,
                    severity=alert.severity,
                    alert_type=alert.alert_type,
                    title=alert.title,
                    description=alert.description,
                    source_event_id=alert.source_event_id,
                    source_uc=alert.source_uc,
                    frame_reference=snap_key,
                    frame_provider=FrameProvider.MINIO,
                    status=alert.status,
                    metadata=alert.metadata,
                )
            except Exception as exc:
                logger.error("snapshot_upload_failed: %s", exc)

        return await self._publisher.publish(alert)

    # ── Abstract method ───────────────────────────────────────────────

    @abc.abstractmethod
    async def process_frame(self, event: FrameEvent, frame: np.ndarray) -> None:
        """
        Run UC-specific inference / detection on the decoded frame.

        Called once per sampled frame. Use ``self.emit_alert()`` when
        alert criteria are met.
        """
        ...
