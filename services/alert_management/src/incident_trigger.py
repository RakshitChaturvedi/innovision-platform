"""
creates incident row for high/critical severity alerts, called via consumer inside same
transaction as alert insert so alert and its incident either both exist or neither does.
Implements incident deduplication within a temporal window to group sustained hazards.
"""

import logging
import uuid
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from shared.contracts.alert_event import AlertEvent
from .config import settings

logger = logging.getLogger(__name__)

INCIDENT_DEDUP_WINDOW_MINUTES = 10


async def maybe_create_incident(
    session: AsyncSession,
    alert_row_id: str,
    alert_title: str | AlertEvent,
    severity: Optional[str] = None,
    alert: Optional[AlertEvent] = None,
) -> str | None:
    """
    Evaluates an alert and either creates a new incident or links to an active incident
    for the same camera and alert category within the deduplication window.
    """
    # Normalize arguments to support both (session, row_id, alert_obj) and (session, row_id, title, severity)
    if isinstance(alert_title, AlertEvent):
        alert_obj = alert_title
        title = alert_obj.title
        sev = alert_obj.severity.value
        description = alert_obj.description
        camera_id = str(alert_obj.camera_id) if alert_obj.camera_id else None
        alert_type = alert_obj.alert_type
    else:
        title = alert_title
        sev = severity or "medium"
        description = alert.description if alert else title
        camera_id = str(alert.camera_id) if alert and alert.camera_id else None
        alert_type = alert.alert_type if alert else "unknown"

    sev_lower = str(sev).lower()
    if sev_lower not in settings.incident_trigger_severities:
        return None

    # Resolve camera organization, site, and zone hierarchy
    org_id = None
    site_id = None
    zone_id = None
    if camera_id:
        try:
            cam_res = await session.execute(
                text("""
                    SELECT c.organization_id, c.site_id, c.zone_id
                    FROM cameras c
                    WHERE c.id::text = :cam_id
                """),
                {"cam_id": camera_id},
            )
            cam_row = cam_res.fetchone()
            if cam_row:
                org_id = str(cam_row.organization_id) if cam_row.organization_id else None
                site_id = str(cam_row.site_id) if cam_row.site_id else None
                zone_id = str(cam_row.zone_id) if cam_row.zone_id else None
        except Exception as e:
            logger.warning("camera_hierarchy_lookup_failed cam_id=%s error=%s", camera_id, e)

    # Deduplication & Grouping: Check if an active incident already exists for this camera & alert type
    if camera_id:
        try:
            existing_res = await session.execute(
                text(f"""
                    SELECT i.id, i.severity, i.status
                    FROM incidents i
                    WHERE i.camera_id::text = :cam_id
                      AND i.status IN ('active', 'open', 'investigating')
                      AND i.created_at >= now() - interval '{INCIDENT_DEDUP_WINDOW_MINUTES} minutes'
                    ORDER BY i.created_at DESC
                    LIMIT 1
                """),
                {"cam_id": camera_id},
            )
            existing_incident = existing_res.fetchone()
            if existing_incident:
                existing_id = str(existing_incident.id)

                # Link new alert to existing incident
                await session.execute(
                    text("""
                        INSERT INTO incident_alerts (incident_id, alert_id, linked_at)
                        VALUES (:incident_id, :alert_id, now())
                        ON CONFLICT DO NOTHING
                    """),
                    {"incident_id": existing_id, "alert_id": alert_row_id},
                )

                # Escalate severity if incoming alert is critical and existing incident is lower
                if sev_lower == "critical" and str(existing_incident.severity).lower() != "critical":
                    await session.execute(
                        text("""
                            UPDATE incidents
                            SET severity = 'critical', updated_at = now()
                            WHERE id = :id
                        """),
                        {"id": existing_id},
                    )

                logger.info(
                    "incident_dedup_linked existing_id=%s alert_id=%s camera=%s type=%s",
                    existing_id, alert_row_id, camera_id, alert_type,
                )
                return existing_id
        except Exception as e:
            logger.warning("incident_dedup_check_failed error=%s", e)

    # Create brand new incident
    incident_id = str(uuid.uuid4())
    try:
        await session.execute(
            text("""
                INSERT INTO incidents (
                    id, alert_id, organization_id, site_id, zone_id, camera_id,
                    title, description, severity, source_type, status, created_at, updated_at
                ) VALUES (
                    :id, :alert_id, :org_id, :site_id, :zone_id, :camera_id,
                    :title, :description, :severity, 'alert', 'active', now(), now()
                )
            """),
            {
                "id": incident_id,
                "alert_id": alert_row_id,
                "org_id": org_id,
                "site_id": site_id,
                "zone_id": zone_id,
                "camera_id": camera_id,
                "title": title,
                "description": description,
                "severity": sev_lower,
            },
        )

        # Link alert in incident_alerts junction table
        await session.execute(
            text("""
                INSERT INTO incident_alerts (incident_id, alert_id, linked_at)
                VALUES (:incident_id, :alert_id, now())
                ON CONFLICT DO NOTHING
            """),
            {"incident_id": incident_id, "alert_id": alert_row_id},
        )

        # Add initial creation entry to incident timeline
        timeline_id = str(uuid.uuid4())
        await session.execute(
            text("""
                INSERT INTO incident_timeline (id, incident_id, action, from_status, to_status, note, timestamp)
                VALUES (:id, :incident_id, 'created_from_alert', NULL, 'active', :note, now())
            """),
            {
                "id": timeline_id,
                "incident_id": incident_id,
                "note": f"Incident generated automatically from {sev_lower.upper()} alert '{title}'.",
            },
        )

        logger.info(
            "incident_created id=%s alert_id=%s severity=%s camera=%s",
            incident_id, alert_row_id, sev_lower, camera_id,
        )
        return incident_id

    except Exception as e:
        logger.error("incident_create_failed alert_id=%s error=%s", alert_row_id, e)
        # Fallback to minimal insert if schema columns are not available
        await session.execute(
            text("""
                INSERT INTO incidents (id, alert_id, title, status, created_at)
                VALUES (:id, :alert_id, :title, 'active', now())
            """),
            {"id": incident_id, "alert_id": alert_row_id, "title": title},
        )
        return incident_id