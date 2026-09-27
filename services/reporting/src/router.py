from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
import uuid
from datetime import datetime

from services.auth.src.rbac import require_role, Role, get_current_user
from shared.platform_client.db import get_session_factory

from .config import settings
from .tasks import generate_report_task
from .storage import presigned_download_url

router = APIRouter(prefix="/reports", tags=["reports"])
_session_factory = get_session_factory(settings.database_url)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


@router.post("/generate", dependencies=[Depends(require_role(Role.OPERATOR))])
async def generate(
    report_type: str,
    date_start: str,
    date_end: str,
    camera_ids: list[str] | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report_id = str(uuid.uuid4())

    async with db.begin():
        await db.execute(text("""
            INSERT INTO reports
                (id, generated_by, camera_ids, date_range_start, date_range_end, status)
            VALUES
                (:id, :generated_by, :camera_ids, :start, :end, 'pending')
        """), {
            "id": report_id,
            "generated_by": user["sub"],
            "camera_ids": camera_ids or [],
            "start": datetime.fromisoformat(date_start),
            "end": datetime.fromisoformat(date_end),
        })

    generate_report_task.apply_async(
        args=[report_id, report_type, date_start, date_end, camera_ids]
    )

    return {"report_id": report_id, "status": "pending"}


@router.get("/{report_id}/status")
async def status(report_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT * FROM reports WHERE id = :id"), {"id": report_id}
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    return dict(row._mapping)


@router.get("/{report_id}/download")
async def download(report_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT status, object_key FROM reports WHERE id = :id"), {"id": report_id}
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    if row.status != "complete" or not row.object_key:
        raise HTTPException(status_code=409, detail=f"Report not ready — status: {row.status}")

    url = presigned_download_url(row.object_key)
    return {"download_url": url}


@router.get("")
async def list_reports(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(text("""
        SELECT * FROM reports ORDER BY created_at DESC LIMIT 50
    """))
    return [dict(r._mapping) for r in rows.fetchall()]