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

    def __init__(self, bucket: str) -> None:
        self._client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = bucket
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def _upload(self, object_key: str, jpeg_bytes: bytes) -> None:
        # blocking minio upload. runs outside event loop.
        self._client.put_object(
            bucket_name=self._bucket,
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

    def upload_background(self, object_key: str, jpeg_bytes: bytes) -> None:
        # fire-and-forget upload for ingestion hot path. never awaited by caller.
        asyncio.create_task(self._upload_and_log(object_key, jpeg_bytes))

    async def _upload_and_log(self, object_key: str, jpeg_bytes: bytes) -> None:
        try:
            await asyncio.to_thread(self._upload, object_key, jpeg_bytes)
        except Exception as e:
            logger.error(f"frame_store_background_upload_failed object_key={object_key} error={e}")
            