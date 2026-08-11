"""
Frame Store — uploads JPEG-encoded frames to MinIO and returns the
object key that becomes ``frame_reference`` in the FrameEvent.
"""

from __future__ import annotations

import asyncio
import logging

from io import BytesIO
from minio import Minio
from services.ingestion.src.config import settings

logger = logging.getLogger(__name__)


class FrameStore:
    """
    Wraps the synchronous MinIO SDK and offloads blocking I/O to a
    thread pool via ``asyncio.to_thread``.
    """

    def __init__(self) -> None:
        self._client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def _upload(self, object_key: str, jpeg_bytes: bytes) -> None:
        # blocking minio upload. runs outside event loop.
        self._client.put_object(
            bucket_name=settings.minio_frames_bucket,
            object_name=object_key,
            data=BytesIO(jpeg_bytes),
            length=len(jpeg_bytes),
            content_type="image/jpeg"
        )

    async def upload(
        self,
        object_key: str,
        jpeg_bytes: bytes,
    ) -> None:
        """
        Upload a JPEG frame to MinIO.

        Key format: ``frames/{camera_id}/{frame_seq:08d}.jpg``

        """
        await asyncio.to_thread(self._upload, object_key, jpeg_bytes)