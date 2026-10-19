from fastapi import APIRouter, Depends, Header, HTTPException
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
    user_role = user.get("role")
    user_org = user.get("org_id") or user.get("organization_id")

    conditions, params = [], {"limit": limit, "offset": offset}
    join_cameras = False

    if user_role != Role.SUPERADMIN:
        if not user_org:
            raise HTTPException(status_code=403, detail="User has no assigned organization")
        join_cameras = True
        conditions.append("(c.organization_id = :org_id OR a.camera_id IS NULL)")
        params["org_id"] = str(user_org)

        if user_role not in (Role.ADMIN, Role.ORG_ADMIN):
            camera_ids = user.get("camera_ids", [])
            if camera_ids:
                conditions.append("a.camera_id::text = ANY(:allowed_cameras)")
                params["allowed_cameras"] = [str(c) for c in camera_ids]

    if source_uc:
        conditions.append("a.source_uc = :source_uc"); params["source_uc"] = source_uc
    if severity:
        conditions.append("a.severity = :severity"); params["severity"] = severity
    if status:
        conditions.append("a.status = :status"); params["status"] = status
    if camera_id:
        conditions.append("a.camera_id::text = :camera_id"); params["camera_id"] = str(camera_id)

    join_clause = "LEFT JOIN cameras c ON a.camera_id = c.id" if join_cameras else ""
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.execute(text(f"""
        SELECT a.* FROM alerts a {join_clause} {where}
        ORDER BY a.created_at DESC LIMIT :limit OFFSET :offset
    """), params)
    return [dict(r._mapping) for r in rows.fetchall()]


@router.patch("/{alert_id}/acknowledge", dependencies=[Depends(require_role(Role.OPERATOR))])
async def acknowledge(
    alert_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    user_role = user.get("role")
    user_org = user.get("org_id") or user.get("organization_id")

    # Verify existence and tenant ownership
    check_row = await db.execute(text("""
        SELECT a.id, a.alert_id, c.organization_id
        FROM alerts a
        LEFT JOIN cameras c ON a.camera_id = c.id
        WHERE a.alert_id::text = :alert_id OR a.id::text = :alert_id
    """), {"alert_id": alert_id})
    alt = check_row.fetchone()
    if not alt:
        raise HTTPException(status_code=404, detail="Alert not found")

    if user_role != Role.SUPERADMIN:
        if not user_org or (alt.organization_id and str(alt.organization_id) != str(user_org)):
            raise HTTPException(status_code=403, detail="Cross-organization alert triage forbidden")

    actual_alert_id = str(alt.alert_id)
    async with db.begin():
        await db.execute(text("""
            UPDATE alerts SET status = 'acknowledged',
                acknowledged_at = now(), acknowledged_by = :user_id
            WHERE alert_id::text = :alert_id OR id::text = :alert_id
        """), {"alert_id": alert_id, "user_id": user["sub"]})

        await write_audit_entry(
            _session_factory, service="alert_management", action="alert_acknowledged",
            entity_type="alert", entity_id=actual_alert_id, user_id=user["sub"], session=db
        )

    row = (await db.execute(text("SELECT * FROM alerts WHERE alert_id::text = :id OR id::text = :id"),
                             {"id": alert_id})).fetchone()
    await push_alert_update(dict(row._mapping))
    return {"status": "acknowledged"}


@router.patch("/{alert_id}/resolve", dependencies=[Depends(require_role(Role.OPERATOR))])
async def resolve(
    alert_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    user_role = user.get("role")
    user_org = user.get("org_id") or user.get("organization_id")

    # Verify existence and tenant ownership
    check_row = await db.execute(text("""
        SELECT a.id, a.alert_id, c.organization_id
        FROM alerts a
        LEFT JOIN cameras c ON a.camera_id = c.id
        WHERE a.alert_id::text = :alert_id OR a.id::text = :alert_id
    """), {"alert_id": alert_id})
    alt = check_row.fetchone()
    if not alt:
        raise HTTPException(status_code=404, detail="Alert not found")

    if user_role != Role.SUPERADMIN:
        if not user_org or (alt.organization_id and str(alt.organization_id) != str(user_org)):
            raise HTTPException(status_code=403, detail="Cross-organization alert triage forbidden")

    actual_alert_id = str(alt.alert_id)
    async with db.begin():
        await db.execute(text("""
            UPDATE alerts SET status = 'resolved',
                resolved_at = now(), resolved_by = :user_id
            WHERE alert_id::text = :alert_id OR id::text = :alert_id
        """), {"alert_id": alert_id, "user_id": user["sub"]})

        await write_audit_entry(
            _session_factory, service="alert_management", action="alert_resolved",
            entity_type="alert", entity_id=actual_alert_id, user_id=user["sub"], session=db
        )

    row = (await db.execute(text("SELECT * FROM alerts WHERE alert_id::text = :id OR id::text = :id"),
                             {"id": alert_id})).fetchone()
    await push_alert_update(dict(row._mapping))
    return {"status": "resolved"}


@router.get("/unacknowledged")
async def unacknowledged(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_role = user.get("role")
    user_org = user.get("org_id") or user.get("organization_id")

    conditions = ["a.status = 'pending'"]
    params = {}
    join_cameras = False

    if user_role != Role.SUPERADMIN:
        if not user_org:
            raise HTTPException(status_code=403, detail="User has no assigned organization")
        join_cameras = True
        conditions.append("(c.organization_id = :org_id OR a.camera_id IS NULL)")
        params["org_id"] = str(user_org)

        if user_role not in (Role.ADMIN, Role.ORG_ADMIN):
            camera_ids = user.get("camera_ids", [])
            if camera_ids:
                conditions.append("a.camera_id::text = ANY(:camera_ids)")
                params["camera_ids"] = [str(c) for c in camera_ids]

    join_clause = "LEFT JOIN cameras c ON a.camera_id = c.id" if join_cameras else ""
    where = f"WHERE {' AND '.join(conditions)}"
    rows = await db.execute(text(f"""
        SELECT a.* FROM alerts a {join_clause} {where}
        ORDER BY a.created_at DESC
    """), params)
    return [dict(r._mapping) for r in rows.fetchall()]


@router.get("/count")
async def count(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user_role = user.get("role")
    user_org = user.get("org_id") or user.get("organization_id")

    conditions = ["a.status = 'pending'"]
    params = {}
    join_cameras = False

    if user_role != Role.SUPERADMIN:
        if not user_org:
            raise HTTPException(status_code=403, detail="User has no assigned organization")
        join_cameras = True
        conditions.append("(c.organization_id = :org_id OR a.camera_id IS NULL)")
        params["org_id"] = str(user_org)

        if user_role not in (Role.ADMIN, Role.ORG_ADMIN):
            camera_ids = user.get("camera_ids", [])
            if camera_ids:
                conditions.append("a.camera_id::text = ANY(:camera_ids)")
                params["camera_ids"] = [str(c) for c in camera_ids]

    join_clause = "LEFT JOIN cameras c ON a.camera_id = c.id" if join_cameras else ""
    where = f"WHERE {' AND '.join(conditions)}"
    row = await db.execute(text(f"""
        SELECT count(*) AS c FROM alerts a {join_clause} {where}
    """), params)
    return {"count": row.fetchone().c}