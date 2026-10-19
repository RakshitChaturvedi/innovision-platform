# handles queries that were missed while disconnected. used by websockets join handler

import logging
from sqlalchemy import text
from datetime import datetime

logger = logging.getLogger(__name__)

def parse_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))

async def fetch_missed_alerts(session_factory, camera_ids: list[str], since: str) -> list[dict]:
    # returns all still pending alerts for given cams created after since
    if not camera_ids:
        return []

    since = parse_timestamp(since)
    cam_str_list = [str(c) for c in camera_ids if c]

    async with session_factory() as session:
        rows = await session.execute(text("""
            SELECT alert_id, camera_id, source_uc, alert_type, severity, title, description,
                   frame_reference, frame_provider, status, metadata, created_at
            FROM alerts
            WHERE camera_id::text = ANY(:camera_ids) AND created_at > :since AND status = 'pending'
            ORDER BY created_at ASC
        """), {"camera_ids": cam_str_list, "since": since})
        return [dict(r._mapping) for r in rows.fetchall()]