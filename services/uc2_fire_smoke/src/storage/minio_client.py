"""
MinIO Storage Client — Uploads evidence snapshots and fetches frame fallbacks.
Bucket: `innovision-evidence`, Key: `evidence/{camera_id}/{alert_id}.jpg`.
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Optional

import cv2
import numpy as np
from minio import Minio
from minio.error import S3Error

from services.uc2_fire_smoke.src.config import settings

logger = logging.getLogger("innovision.uc2.storage.minio")


class MinIOClient:
    """
    Async-friendly wrapper for MinIO S3 object storage operations.
    """

    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: Optional[bool] = None,
        evidence_bucket: Optional[str] = None,
        frames_bucket: Optional[str] = None,
    ) -> None:
        self.endpoint = endpoint or settings.minio_endpoint
        self.access_key = access_key or settings.minio_access_key
        self.secret_key = secret_key or settings.minio_secret_key
        self.secure = secure if secure is not None else settings.minio_secure
        self.evidence_bucket = evidence_bucket or settings.minio_evidence_bucket
        self.frames_bucket = frames_bucket or settings.minio_frames_bucket

        self._client: Optional[Minio] = None
        self._init_client()

    def _init_client(self) -> None:
        try:
            self._client = Minio(
                endpoint=self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
            logger.info(f"MinIO client initialized for endpoint {self.endpoint}")
        except Exception as exc:
            logger.error(f"Failed to initialize MinIO client: {exc}")
            self._client = None

    def _ensure_bucket(self, bucket_name: str) -> None:
        if not self._client:
            return
        try:
            if not self._client.bucket_exists(bucket_name):
                self._client.make_bucket(bucket_name)
                logger.info(f"Created bucket {bucket_name}")
        except Exception as exc:
            logger.warning(f"Bucket check/create error for {bucket_name}: {exc}")

    async def upload_evidence(
        self,
        camera_id: str,
        alert_id: str,
        image_bgr: np.ndarray,
        jpeg_quality: int = 85,
    ) -> Optional[str]:
        """
        Encodes image as JPEG and uploads to MinIO bucket `innovision-evidence`.
        Returns the object key path: `evidence/{camera_id}/{alert_id}.jpg`.
        """
        if not self._client:
            return None

        def _sync_upload() -> Optional[str]:
            try:
                self._ensure_bucket(self.evidence_bucket)
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality]
                success, encoded_img = cv2.imencode(".jpg", image_bgr, encode_param)
                if not success:
                    logger.error("Failed to JPEG-encode evidence image")
                    return None

                img_bytes = encoded_img.tobytes()
                object_key = f"evidence/{camera_id}/{alert_id}.jpg"

                self._client.put_object(
                    bucket_name=self.evidence_bucket,
                    object_name=object_key,
                    data=io.BytesIO(img_bytes),
                    length=len(img_bytes),
                    content_type="image/jpeg",
                )
                logger.info(f"Uploaded evidence snapshot to {self.evidence_bucket}/{object_key}")
                return object_key
            except Exception as exc:
                logger.error(f"MinIO evidence upload failed for {alert_id}: {exc}")
                return None

        return await asyncio.to_thread(_sync_upload)

    async def get_frame(self, object_key: str) -> Optional[np.ndarray]:
        """
        Fetch frame bytes from MinIO frames bucket and decode into BGR ndarray.
        """
        if not self._client:
            return None

        def _sync_get() -> Optional[np.ndarray]:
            try:
                response = self._client.get_object(self.frames_bucket, object_key)
                img_bytes = response.read()
                response.close()
                response.release_conn()

                np_arr = np.frombuffer(img_bytes, np.uint8)
                frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                return frame
            except Exception as exc:
                logger.error(f"MinIO get_frame failed for {object_key}: {exc}")
                return None

        return await asyncio.to_thread(_sync_get)

    async def check_health(self) -> bool:
        """Check MinIO connectivity by probing bucket list."""
        if not self._client:
            return False

        def _sync_check() -> bool:
            try:
                self._client.list_buckets()
                return True
            except Exception as exc:
                logger.warning(f"MinIO health check probe failed: {exc}")
                return False

        return await asyncio.to_thread(_sync_check)

