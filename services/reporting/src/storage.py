"""Uploads finished report PDFs to the shared reports bucket."""
from io import BytesIO
from minio import Minio
from .config import settings


def upload_report(object_key: str, pdf_bytes: bytes) -> None:
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
    )
    client.put_object(
        bucket_name=settings.reports_bucket,
        object_name=object_key,
        data=BytesIO(pdf_bytes),
        length=len(pdf_bytes),
        content_type="application/pdf",
    )


def presigned_download_url(object_key: str, expires_hours: int = 24) -> str:
    from datetime import timedelta
    client = Minio(
        endpoint=settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=False,
    )
    return client.presigned_get_object(
        settings.reports_bucket, object_key, expires=timedelta(hours=expires_hours)
    )