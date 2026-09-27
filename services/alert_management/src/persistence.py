import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from shared.contracts.alert_event import AlertEvent

logger = logging.getLogger(__name__)

async def insert_alert(session: AsyncSession, row_id: str, alert: AlertEvent) -> bool:
    metadata_json = json.dumps(alert.metadata) if alert.metadata is not None else None
    # insert row into platform alerts  table. on conflict do nothing. return true if inserted
    result = await session.execute(text("""
        INSERT INTO alerts (
            id, alert_id, camera_id, source_uc, alert_type, severity, title, description,
            source_event_id, frame_reference, frame_provider, status, metadata, created_at
        ) VALUES (
            :id, :alert_id, :camera_id, :source_uc, :alert_type, :severity, :title, 
            :description, :source_event_id, :frame_reference, :frame_provider, 'pending', 
            :metadata, :created_at
        )
        ON CONFLICT (alert_id) DO NOTHING
        RETURNING id
    """), {
        "id": row_id,
        "alert_id": str(alert.alert_id),
        "camera_id": str(alert.camera_id),
        "source_uc": alert.source_uc.value,
        "alert_type": alert.alert_type,
        "severity": alert.severity.value,
        "title": alert.title,
        "description": alert.description,
        "source_event_id": str(alert.source_event_id),
        "frame_reference": alert.frame_reference,
        "frame_provider": alert.frame_provider.value if alert.frame_provider else None,
        "metadata": metadata_json,
        "created_at": alert.timestamp,
    })

    inserted = result.fetchone() is not None
    if not inserted:
        logger.info("alert_duplicate_skipped alert_id=%s", alert.alert_id)
    return inserted

async def fetch_alert_row(session: AsyncSession, row_id: str) -> dict | None:
    row = await session.execute(text("""
        SELECT *
        FROM alerts
        WHERE id = :id
    """), {"id": row_id})
    result = row.fetchone()
    return dict(result._mapping) if result else None

async def fetch_alert_by_alert_id(session: AsyncSession, alert_id: str) -> dict | None:
    row = await session.execute(text("""
        SELECT *
        FROM alerts
        WHERE alert_id = :alert_id
    """), {"alert_id": alert_id})
    result = row.fetchone()
    return dict(result._mapping) if result else None