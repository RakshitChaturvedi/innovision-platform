"""
Shared query helpers reused by multiple report generators.
Kept separate from any one generator so common filtering logic
(date range + camera_ids) doesn't get copy-pasted four times.
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def alerts_in_range(
    session: AsyncSession,
    date_start: datetime,
    date_end: datetime,
    camera_ids: list[str] | None = None,
) -> list[dict]:
    camera_filter = "AND camera_id = ANY(:camera_ids)" if camera_ids else ""
    params = {"start": date_start, "end": date_end}
    if camera_ids:
        params["camera_ids"] = camera_ids

    rows = await session.execute(text(f"""
        SELECT a.*, c.name AS camera_name
        FROM alerts a
        JOIN cameras c ON c.id = a.camera_id
        WHERE a.created_at BETWEEN :start AND :end
        {camera_filter}
        ORDER BY a.created_at DESC
    """), params)
    return [dict(r._mapping) for r in rows.fetchall()]


async def incidents_in_range(
    session: AsyncSession, date_start: datetime, date_end: datetime,
) -> list[dict]:
    rows = await session.execute(text("""
        SELECT i.*, a.source_uc, a.alert_type, a.severity, a.created_at AS alert_created_at
        FROM incidents i
        JOIN alerts a ON a.id = i.alert_id
        WHERE a.created_at BETWEEN :start AND :end
        ORDER BY a.created_at DESC
    """), {"start": date_start, "end": date_end})
    return [dict(r._mapping) for r in rows.fetchall()]