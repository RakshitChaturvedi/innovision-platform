"""
Frame Store — uploads JPEG-encoded frames to MinIO and returns the
object key that becomes ``frame_reference`` in the FrameEvent.
"""

from __future__ import annotations

import asyncio
import io
import logging
from uuid import UUID

from minio import Minio

logger = logging.getLogger(__name__)


class FrameStore:
    """
    Wraps the synchronous MinIO SDK and offloads blocking I/O to a
    thread pool via ``asyncio.to_thread``.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = False,
        bucket: str = "innovision-frames",
    ) -> None:
        self._client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._bucket = bucket
        self._ensure_bucket()

    # ── internal ──────────────────────────────────────────────────────

    def _ensure_bucket(self) -> None:
        """Create the target bucket if it does not already exist."""
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)
            logger.info("minio_bucket_created bucket=%s", self._bucket)

    def _upload_sync(self, key: str, data: bytes, content_type: str) -> str:
        """Synchronous upload — called inside ``to_thread``."""
        self._client.put_object(
            bucket_name=self._bucket,
            object_name=key,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return key

    # ── public API ────────────────────────────────────────────────────

    async def upload_frame(
        self,
        camera_id: UUID,
        frame_seq: int,
        jpeg_bytes: bytes,
    ) -> str:
        """
        Upload a JPEG frame to MinIO.

        Key format: ``frames/{camera_id}/{frame_seq:08d}.jpg``

        Returns the object key (used as ``frame_reference``).
        """
        key = f"frames/{camera_id}/{frame_seq:08d}.jpg"
        await asyncio.to_thread(self._upload_sync, key, jpeg_bytes, "image/jpeg")
        return key

    async def upload_snapshot(
        self,
        key: str,
        jpeg_bytes: bytes,
        bucket: str | None = None,
    ) -> str:
        """Upload an arbitrary JPEG snapshot (e.g. alert evidence)."""
        target_bucket = bucket or self._bucket
        # Ensure the bucket exists if a custom bucket is specified
        if target_bucket != self._bucket:
            exists = await asyncio.to_thread(self._client.bucket_exists, target_bucket)
            if not exists:
                await asyncio.to_thread(self._client.make_bucket, target_bucket)
        await asyncio.to_thread(self._upload_sync, key, jpeg_bytes, "image/jpeg")
        return key
