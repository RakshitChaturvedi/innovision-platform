"""
Helper for appending rows to incident_timeline.
Every status change, assignment, and note flows through here so the
insert shape stays consistent no matter which router endpoint calls it.
"""
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def append_entry(
    session: AsyncSession,
    incident_id: str,
    action: str,
    user_id: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    note: str | None = None,
) -> None:
    await session.execute(text("""
        INSERT INTO incident_timeline
            (id, incident_id, user_id, action, from_status, to_status, note, timestamp)
        VALUES
            (:id, :incident_id, :user_id, :action, :from_status, :to_status, :note, now())
    """), {
        "id": str(uuid.uuid4()),
        "incident_id": incident_id,
        "user_id": user_id,
        "action": action,
        "from_status": from_status,
        "to_status": to_status,
        "note": note,
    })


async def fetch_timeline(session: AsyncSession, incident_id: str) -> list[dict]:
    rows = await session.execute(text("""
        SELECT * FROM incident_timeline
        WHERE incident_id = :incident_id
        ORDER BY timestamp ASC
    """), {"incident_id": incident_id})
    return [dict(r._mapping) for r in rows.fetchall()]