"""
MinIO Client wrapper for UC3 evidence frame uploads.
"""

from __future__ import annotations

import io
import logging
from typing import Optional
from uuid import UUID

import cv2
import numpy as np

from services.uc3_ppe_detection.src import config

logger = logging.getLogger(__name__)

try:
    from minio import Minio
except ImportError:
    Minio = None


class MinIOClient:
    def __init__(self) -> None:
        self.enabled = Minio is not None
        self.client: Optional[Minio] = None
        if self.enabled:
            try:
                self.client = Minio(
                    endpoint=config.MINIO_ENDPOINT,
                    access_key=config.MINIO_ACCESS_KEY,
                    secret_key=config.MINIO_SECRET_KEY,
                    secure=config.MINIO_SECURE,
                )
                self._ensure_bucket(config.MINIO_EVIDENCE_BUCKET)
            except Exception as exc:
                logger.warning("MinIO initialization failed: %s", exc)
                self.client = None

    def _ensure_bucket(self, bucket_name: str) -> None:
        if self.client and not self.client.bucket_exists(bucket_name):
            try:
                self.client.make_bucket(bucket_name)
                logger.info("Created MinIO bucket '%s'", bucket_name)
            except Exception as exc:
                logger.warning("Failed to create MinIO bucket '%s': %s", bucket_name, exc)

    async def upload_evidence(
        self,
        camera_id: UUID,
        alert_id: str,
        image_bgr: np.ndarray,
        jpeg_quality: int = 85,
    ) -> Optional[str]:
        if not self.client:
            return None

        try:
            _, encoded = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
            data = encoded.tobytes()

            object_name = f"uc3/{camera_id}/{alert_id}.jpg"
            self.client.put_object(
                bucket_name=config.MINIO_EVIDENCE_BUCKET,
                object_name=object_name,
                data=io.BytesIO(data),
                length=len(data),
                content_type="image/jpeg",
            )
            return object_name
        except Exception as exc:
            logger.warning("Failed to upload evidence for alert %s: %s", alert_id, exc)
            return None
