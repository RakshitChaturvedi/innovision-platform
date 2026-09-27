from fastapi import APIRouter, Depends, Header
from sqlalchemy import text
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from services.auth.src.rbac import require_role, Role, get_current_user
from services.audit.src.writer import write_audit_entry
from shared.platform_client.db import get_session_factory
from .config import settings
from .websocket import push_alert_update

router = APIRouter(prefix="/alerts", tags=["alerts"])
_session_factory = get_session_factory(settings.database_url)


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
    user: dict = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    conditions, params = [], {"limit": limit, "offset": offset}

    if user and user.get("role") not in ("superadmin", "admin"):
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

    row = (await db.execute(text("SELECT * FROM alerts WHERE alert_id = :id"),
                             {"id": alert_id})).fetchone()
    await push_alert_update(dict(row._mapping))
    return {"status": "acknowledged"}


@router.patch("/{alert_id}/resolve", dependencies=[Depends(require_role(Role.OPERATOR))])
async def resolve(
    alert_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
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

    row = (await db.execute(text("SELECT * FROM alerts WHERE alert_id = :id"),
                             {"id": alert_id})).fetchone()
    await push_alert_update(dict(row._mapping))
    return {"status": "resolved"}


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