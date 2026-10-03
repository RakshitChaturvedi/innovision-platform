from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import text
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from minio import Minio
from datetime import timedelta

from services.auth.src.rbac import require_role, Role, get_current_user
from services.audit.src.writer import write_audit_entry
from shared.platform_client.db import get_session_factory
from .config import settings
from .websocket import push_alert_update

router = APIRouter(prefix="/alerts", tags=["alerts"])
_session_factory = get_session_factory(settings.database_url)

# MinIO client — uses internal endpoint for API calls
_minio_internal = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)

from minio.error import S3Error

# MinIO client — uses public endpoint so presigned URLs are browser-reachable
_minio_public = Minio(
    settings.minio_public_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_public_secure,
    region=settings.minio_region,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session

async def get_optional_user(authorization: str | None = Header(None)) -> dict | None:
    if not authorization:
        return None
    try:
        return await get_current_user(authorization=authorization)
    except Exception:
        return None

@router.get("")
async def list_alerts(
    source_uc: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    camera_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conditions, params = [], {"limit": limit, "offset": offset}

    if user.get("role") not in ("superadmin", "admin"):
        conditions.append("camera_id = ANY(:allowed_cameras)")
        params["allowed_cameras"] = user.get("camera_ids", [])

    if source_uc:
        conditions.append("source_uc = :source_uc"); params["source_uc"] = source_uc
    if severity:
        conditions.append("severity = :severity"); params["severity"] = severity
    if status:
        conditions.append("status = :status"); params["status"] = status
    if camera_id:
        conditions.append("camera_id = :camera_id"); params["camera_id"] = camera_id

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.execute(text(f"""
        SELECT * FROM alerts {where}
        ORDER BY created_at DESC LIMIT :limit OFFSET :offset
    """), params)
    return [dict(r._mapping) for r in rows.fetchall()]


@router.patch("/{alert_id}/acknowledge", dependencies=[Depends(require_role(Role.OPERATOR))])
async def acknowledge(
    alert_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    row = (await db.execute(
        text("SELECT * FROM alerts WHERE alert_id = :id"),
        {"id": alert_id}
    )).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    if user.get("role") not in ("superadmin", "admin"):
        allowed_cameras = [str(c) for c in user.get("camera_ids", [])]
        if row.camera_id is not None and str(row.camera_id) not in allowed_cameras:
            raise HTTPException(status_code=403, detail="No access to this camera")

    async with db.begin():
        await db.execute(text("""
            UPDATE alerts SET status = 'acknowledged',
                acknowledged_at = now(), acknowledged_by = :user_id
            WHERE alert_id = :alert_id
        """), {"alert_id": alert_id, "user_id": user["sub"]})

        await write_audit_entry(
            _session_factory, service="alert_management", action="alert_acknowledged",
            entity_type="alert", entity_id=alert_id, user_id=user["sub"], session=db
        )

    updated = (await db.execute(text("SELECT * FROM alerts WHERE alert_id = :id"),
                              {"id": alert_id})).fetchone()
    if updated:
        await push_alert_update(dict(updated._mapping))
        return dict(updated._mapping)
    raise HTTPException(status_code=404, detail="Alert not found")


@router.patch("/{alert_id}/resolve", dependencies=[Depends(require_role(Role.OPERATOR))])
async def resolve(
    alert_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    row = (await db.execute(
        text("SELECT * FROM alerts WHERE alert_id = :id"),
        {"id": alert_id}
    )).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    if user.get("role") not in ("superadmin", "admin"):
        allowed_cameras = [str(c) for c in user.get("camera_ids", [])]
        if row.camera_id is not None and str(row.camera_id) not in allowed_cameras:
            raise HTTPException(status_code=403, detail="No access to this camera")

    async with db.begin():
        await db.execute(text("""
            UPDATE alerts SET status = 'resolved',
                resolved_at = now(), resolved_by = :user_id
            WHERE alert_id = :alert_id
        """), {"alert_id": alert_id, "user_id": user["sub"]})

        await write_audit_entry(
            _session_factory, service="alert_management", action="alert_resolved",
            entity_type="alert", entity_id=alert_id, user_id=user["sub"], session=db
        )

    updated = (await db.execute(text("SELECT * FROM alerts WHERE alert_id = :id"),
                              {"id": alert_id})).fetchone()
    if updated:
        await push_alert_update(dict(updated._mapping))
        return dict(updated._mapping)
    raise HTTPException(status_code=404, detail="Alert not found")


@router.get("/status-counts")
async def status_counts(
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    camera_filter = (
        "" if user.get("role") in ("superadmin", "admin")
        else "WHERE camera_id = ANY(:camera_ids)"
    )
    params = {} if user.get("role") in ("superadmin", "admin") else {"camera_ids": user.get("camera_ids", [])}

    rows = await db.execute(text(f"""
        SELECT status, count(*) AS c FROM alerts {camera_filter} GROUP BY status
    """), params)

    counts = {"pending": 0, "acknowledged": 0, "resolved": 0}
    for r in rows.fetchall():
        if r.status in counts:
            counts[r.status] = r.c
    return counts


@router.get("/unacknowledged")
async def unacknowledged(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    camera_filter = (
        "" if user["role"] in ("superadmin", "admin")
        else "AND camera_id = ANY(:camera_ids)"
    )
    params = {} if user["role"] in ("superadmin", "admin") else {"camera_ids": user["camera_ids"]}

    rows = await db.execute(text(f"""
        SELECT * FROM alerts WHERE status = 'pending' {camera_filter}
        ORDER BY created_at DESC
    """), params)
    return [dict(r._mapping) for r in rows.fetchall()]


@router.get("/count")
async def count(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    camera_filter = (
        "" if user["role"] in ("superadmin", "admin")
        else "AND camera_id = ANY(:camera_ids)"
    )
    params = {} if user["role"] in ("superadmin", "admin") else {"camera_ids": user["camera_ids"]}

    row = await db.execute(text(f"""
        SELECT count(*) AS c FROM alerts WHERE status = 'pending' {camera_filter}
    """), params)
    return {"count": row.fetchone().c}


@router.get("/{alert_id}/snapshot", dependencies=[Depends(require_role(Role.OPERATOR))])
async def get_snapshot(
    alert_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return a presigned GET URL for the alert's evidence snapshot stored in MinIO.
    The URL is built against MINIO_PUBLIC_ENDPOINT so the browser can reach it.
    Returns 404 when the alert does not exist or has no frame_reference.
    Returns 403 when the user has no access to the alert's camera.
    """
    row = (await db.execute(
        text("SELECT camera_id, frame_reference FROM alerts WHERE alert_id = :id"),
        {"id": alert_id},
    )).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")

    if user.get("role") not in ("superadmin", "admin"):
        allowed_cameras = [str(c) for c in user.get("camera_ids", [])]
        if row.camera_id is not None and str(row.camera_id) not in allowed_cameras:
            raise HTTPException(status_code=403, detail="No access to this camera")

    frame_reference: str | None = row.frame_reference
    if not frame_reference:
        raise HTTPException(status_code=404, detail="Alert has no snapshot")

    try:
        url = await asyncio.to_thread(
            _minio_public.presigned_get_object,
            settings.snapshot_bucket,
            frame_reference,
            expires=timedelta(seconds=settings.snapshot_presign_expires),
        )
    except S3Error as exc:
        code = getattr(exc, "_code", None) or getattr(exc, "code", None) or ""
        if code in ("NoSuchKey", "NoSuchBucket", "ResourceNotFound", "404") or "NoSuchKey" in str(exc) or "specified key does not exist" in str(exc):
            raise HTTPException(status_code=404, detail="Snapshot object not found")
        raise HTTPException(status_code=502, detail=f"Could not generate snapshot URL: {exc}")
    except Exception as exc:
        code = getattr(exc, "_code", None) or getattr(exc, "code", None) or ""
        if code in ("NoSuchKey", "NoSuchBucket", "ResourceNotFound", "404") or "NoSuchKey" in str(exc) or "specified key does not exist" in str(exc):
            raise HTTPException(status_code=404, detail="Snapshot object not found")
        raise HTTPException(status_code=502, detail=f"Could not generate snapshot URL: {exc}")

    return {"url": url, "expires_in": settings.snapshot_presign_expires}