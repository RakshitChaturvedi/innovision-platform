from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import text
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from services.auth.src.rbac import require_role, Role, get_current_user
from services.audit.src.writer import write_audit_entry
from shared.platform_client.db import get_session_factory

from .config import settings
from .workflow import is_valid_transition, all_valid_next_states
from .timeline import append_entry, fetch_timeline

router = APIRouter(prefix="/incidents", tags=["incidents"])
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
async def list_incidents(
    status: str | None = None,
    assigned_to: str | None = None,
    user: dict = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    conditions, params = [], {}
    if status:
        conditions.append("status = :status"); params["status"] = status
    if assigned_to:
        conditions.append("assigned_to = :assigned_to"); params["assigned_to"] = assigned_to

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    rows = await db.execute(text(f"""
        SELECT * FROM incidents {where} ORDER BY created_at DESC
    """), params)
    return [dict(r._mapping) for r in rows.fetchall()]


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    row = await db.execute(text("SELECT * FROM incidents WHERE id = :id"), {"id": incident_id})
    incident = row.fetchone()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    timeline = await fetch_timeline(db, incident_id)
    return {
        "incident": dict(incident._mapping),
        "timeline": timeline,
        "valid_next_states": all_valid_next_states(incident.status),
    }


@router.patch("/{incident_id}/status", dependencies=[Depends(require_role(Role.OPERATOR))])
async def update_status(
    incident_id: str,
    new_status: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current = (await db.execute(
        text("SELECT status FROM incidents WHERE id = :id"), {"id": incident_id}
    )).fetchone()
    if not current:
        raise HTTPException(status_code=404, detail="Incident not found")

    if not is_valid_transition(current.status, new_status):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current.status}' to '{new_status}'. "
                   f"Valid next states: {all_valid_next_states(current.status)}",
        )

    async with db.begin():
        await db.execute(text("""
            UPDATE incidents SET status = :status, updated_at = now(),
                resolved_at = CASE WHEN :status = 'resolved' THEN now() ELSE resolved_at END
            WHERE id = :id
        """), {"status": new_status, "id": incident_id})

        await append_entry(
            db, incident_id, action="status_changed", user_id=user["sub"],
            from_status=current.status, to_status=new_status,
        )

        await write_audit_entry(
            _session_factory, service="incident_management",
            action="incident_status_changed", entity_type="incident",
            entity_id=incident_id, user_id=user["sub"],
            metadata={"from": current.status, "to": new_status}, session=db
        )

    return {"status": new_status}


@router.patch("/{incident_id}/assign", dependencies=[Depends(require_role(Role.OPERATOR))])
async def assign(
    incident_id: str,
    assignee_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    exists = (await db.execute(
        text("SELECT 1 FROM incidents WHERE id = :id"), {"id": incident_id}
    )).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Incident not found")

    async with db.begin():
        await db.execute(text("""
            UPDATE incidents SET assigned_to = :assignee_id WHERE id = :id
        """), {"assignee_id": assignee_id, "id": incident_id})

        await append_entry(
            db, incident_id, action="assigned", user_id=user["sub"],
            note=f"Assigned to operator {assignee_id}",
        )

    return {"status": "assigned", "assigned_to": assignee_id}


@router.post("/{incident_id}/notes", dependencies=[Depends(require_role(Role.OPERATOR))])
async def add_note(
    incident_id: str,
    note: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    async with db.begin():
        await append_entry(db, incident_id, action="note_added", user_id=user["sub"], note=note)

    return {"status": "note_added"}