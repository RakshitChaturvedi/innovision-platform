"""
creates incident row for high/critical severity alerts, called via consumer inside same
transaction as alert insert so alert and its incident either both exist or neither does.
"""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from .config import settings

logger = logging.getLogger(__name__)

async def maybe_create_incident(session: AsyncSession, alert_row_id: str, alert_title: str, severity:str) -> str | None:
    # return new incident id or none if this severity doesnt warrant an incident
    if severity not in settings.incident_trigger_severities:
        return None
    incident_id = str(uuid.uuid4())

    await session.execute(text("""
        INSERT INTO incidents (id, alert_id, title, status, created_at) 
        VALUES (:id, :alert_id, :title, 'active', now())
    """), {"id": incident_id, "alert_id": alert_row_id, "title": alert_title})

    logger.info("incident_created id=%s alert_id=%s severity=%s", incident_id, alert_row_id, severity)
    return incident_id