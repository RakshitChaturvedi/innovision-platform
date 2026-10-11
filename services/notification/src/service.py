import json
import logging
import math
import uuid
from datetime import datetime
from typing import Any, Optional
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.auth.src.rbac import Role
from services.audit.src.writer import write_audit_entry
from services.notification.src.schemas import (
    NotificationItem,
    NotificationListResponse,
    NotificationPreferenceItem,
    NotificationPreferenceUpdate,
    UnreadCountResponse,
)
from services.notification.src.email import send_escalation_email

logger = logging.getLogger(__name__)

STANDARD_NOTIFICATION_TYPES = [
    {
        "notification_type": "critical_alert",
        "display_name": "Critical Safety & Perimeter Alerts",
        "description": "Immediate notifications for critical severity security & safety alert events.",
    },
    {
        "notification_type": "high_alert",
        "display_name": "High Severity Alerts",
        "description": "Notifications for high severity operational and compliance alerts.",
    },
    {
        "notification_type": "incident_assigned",
        "display_name": "Incident Assignment",
        "description": "Notifications when an operational incident is directly assigned to you.",
    },
    {
        "notification_type": "incident_status_changed",
        "display_name": "Incident Lifecycle Updates",
        "description": "Notifications when an incident status is updated or resolved.",
    },
]


class NotificationService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def list_notifications(
        self,
        user: dict,
        page: int = 1,
        page_size: int = 20,
        is_read: Optional[bool] = None,
        type_filter: Optional[str] = None,
        severity_filter: Optional[str] = None,
    ) -> NotificationListResponse:
        user_id = user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        where_clauses: list[str] = ["recipient_user_id = :user_id"]
        params: dict[str, Any] = {"user_id": user_id, "limit": page_size, "offset": offset}

        if is_read is not None:
            where_clauses.append("is_read = :is_read")
            params["is_read"] = is_read

        if type_filter:
            where_clauses.append("type = :type_filter")
            params["type_filter"] = type_filter

        if severity_filter:
            where_clauses.append("severity = :severity_filter")
            params["severity_filter"] = severity_filter

        where_sql = f"WHERE {' AND '.join(where_clauses)}"

        async with self.session_factory() as session:
            # Get Total Count matching filter
            count_res = await session.execute(text(f"SELECT COUNT(*) FROM notifications {where_sql}"), params)
            total = count_res.scalar() or 0

            # Get Unread Count overall for user
            unread_res = await session.execute(
                text("SELECT COUNT(*) FROM notifications WHERE recipient_user_id = :user_id AND is_read = false"),
                {"user_id": user_id}
            )
            unread_count = unread_res.scalar() or 0

            # Fetch rows
            rows = (await session.execute(
                text(f"""
                    SELECT id, organization_id, recipient_user_id, type, title, message, severity,
                           resource_type, resource_id, metadata, is_read, created_at, read_at
                    FROM notifications
                    {where_sql}
                    ORDER BY created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                params
            )).fetchall()

        items = []
        for r in rows:
            meta = r.metadata if isinstance(r.metadata, dict) else (json.loads(r.metadata) if r.metadata else {})
            items.append(
                NotificationItem(
                    id=str(r.id),
                    organization_id=str(r.organization_id) if r.organization_id else None,
                    recipient_user_id=str(r.recipient_user_id),
                    type=r.type,
                    title=r.title,
                    message=r.message,
                    severity=r.severity,
                    resource_type=r.resource_type,
                    resource_id=r.resource_id,
                    metadata=meta,
                    is_read=r.is_read,
                    created_at=r.created_at,
                    read_at=r.read_at,
                )
            )

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return NotificationListResponse(
            items=items,
            total=total,
            unread_count=unread_count,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_unread_count(self, user: dict) -> UnreadCountResponse:
        user_id = user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        async with self.session_factory() as session:
            res = await session.execute(
                text("SELECT COUNT(*) FROM notifications WHERE recipient_user_id = :user_id AND is_read = false"),
                {"user_id": user_id}
            )
            count = res.scalar() or 0

        return UnreadCountResponse(unread_count=count)

    async def mark_as_read(self, user: dict, notification_id: str) -> NotificationItem:
        user_id = user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        async with self.session_factory() as session:
            async with session.begin():
                row = (await session.execute(
                    text("SELECT * FROM notifications WHERE id = :id AND recipient_user_id = :user_id"),
                    {"id": notification_id, "user_id": user_id}
                )).fetchone()

                if not row:
                    raise HTTPException(status_code=404, detail="Notification not found")

                if not row.is_read:
                    await session.execute(
                        text("UPDATE notifications SET is_read = true, read_at = now() WHERE id = :id"),
                        {"id": notification_id}
                    )

                updated_row = (await session.execute(
                    text("SELECT * FROM notifications WHERE id = :id"),
                    {"id": notification_id}
                )).fetchone()

        meta = updated_row.metadata if isinstance(updated_row.metadata, dict) else (json.loads(updated_row.metadata) if updated_row.metadata else {})

        return NotificationItem(
            id=str(updated_row.id),
            organization_id=str(updated_row.organization_id) if updated_row.organization_id else None,
            recipient_user_id=str(updated_row.recipient_user_id),
            type=updated_row.type,
            title=updated_row.title,
            message=updated_row.message,
            severity=updated_row.severity,
            resource_type=updated_row.resource_type,
            resource_id=updated_row.resource_id,
            metadata=meta,
            is_read=updated_row.is_read,
            created_at=updated_row.created_at,
            read_at=updated_row.read_at,
        )

    async def mark_all_as_read(self, user: dict) -> UnreadCountResponse:
        user_id = user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        async with self.session_factory() as session:
            async with session.begin():
                await session.execute(
                    text("UPDATE notifications SET is_read = true, read_at = now() WHERE recipient_user_id = :user_id AND is_read = false"),
                    {"user_id": user_id}
                )

        return UnreadCountResponse(unread_count=0)

    async def get_user_preferences(self, user: dict) -> list[NotificationPreferenceItem]:
        user_id = user.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        async with self.session_factory() as session:
            rows = (await session.execute(
                text("SELECT notification_type, in_app_enabled, email_enabled FROM notification_preferences WHERE user_id = :user_id"),
                {"user_id": user_id}
            )).fetchall()

        pref_map = {r.notification_type: (r.in_app_enabled, r.email_enabled) for r in rows}

        results = []
        for def_t in STANDARD_NOTIFICATION_TYPES:
            t_type = def_t["notification_type"]
            in_app, email = pref_map.get(t_type, (True, True))
            results.append(
                NotificationPreferenceItem(
                    notification_type=t_type,
                    display_name=def_t["display_name"],
                    description=def_t["description"],
                    in_app_enabled=in_app,
                    email_enabled=email,
                )
            )

        return results

    async def update_user_preferences(
        self, user: dict, update_items: list[NotificationPreferenceUpdate]
    ) -> list[NotificationPreferenceItem]:
        user_id = user.get("sub")
        user_org = user.get("org_id") or user.get("organization_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        changes = []
        async with self.session_factory() as session:
            async with session.begin():
                for item in update_items:
                    # Fetch current preference
                    curr = (await session.execute(
                        text("SELECT in_app_enabled, email_enabled FROM notification_preferences WHERE user_id = :user_id AND notification_type = :ntype"),
                        {"user_id": user_id, "ntype": item.notification_type}
                    )).fetchone()

                    curr_in_app = curr.in_app_enabled if curr else True
                    curr_email = curr.email_enabled if curr else True

                    new_in_app = item.in_app_enabled if item.in_app_enabled is not None else curr_in_app
                    new_email = item.email_enabled if item.email_enabled is not None else curr_email

                    await session.execute(
                        text("""
                            INSERT INTO notification_preferences (id, user_id, organization_id, notification_type, in_app_enabled, email_enabled, created_at, updated_at)
                            VALUES (uuid_generate_v4(), :user_id, :org_id, :ntype, :in_app, :email, now(), now())
                            ON CONFLICT (user_id, notification_type)
                            DO UPDATE SET in_app_enabled = EXCLUDED.in_app_enabled, email_enabled = EXCLUDED.email_enabled, updated_at = now()
                        """),
                        {
                            "user_id": user_id,
                            "org_id": user_org,
                            "ntype": item.notification_type,
                            "in_app": new_in_app,
                            "email": new_email,
                        }
                    )
                    changes.append({"type": item.notification_type, "in_app": new_in_app, "email": new_email})

        # Record Audit Event
        await write_audit_entry(
            session_factory=self.session_factory,
            service="notification",
            action="notification_preferences_updated",
            entity_type="user_preferences",
            entity_id=user_id,
            user_id=user_id,
            metadata={"updated_preferences": changes},
        )

        return await self.get_user_preferences(user)


async def create_user_notification(
    session_factory: async_sessionmaker[AsyncSession],
    recipient_user_id: str,
    organization_id: Optional[str],
    type_str: str,
    title: str,
    message: str,
    severity: str = "medium",
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Creates an in-app notification record and delivers real-time / email notifications
    according to recipient's notification preferences.
    """
    metadata = metadata or {}

    async with session_factory() as session:
        # Check recipient preferences
        pref = (await session.execute(
            text("SELECT in_app_enabled, email_enabled FROM notification_preferences WHERE user_id = :uid AND notification_type = :ntype"),
            {"uid": recipient_user_id, "ntype": type_str}
        )).fetchone()

        in_app_enabled = pref.in_app_enabled if pref else True
        email_enabled = pref.email_enabled if pref else True

        notification_id = str(uuid.uuid4())
        created_at = datetime.utcnow()

        if in_app_enabled:
            if resource_type and resource_id:
                new_status_val = metadata.get("new_status") if type_str == "incident_status_changed" else None
                where_sql = """
                    WHERE recipient_user_id = :recipient_id
                      AND type = :type
                      AND resource_type = :res_type
                      AND resource_id = :res_id
                """
                params = {
                    "recipient_id": recipient_user_id,
                    "type": type_str,
                    "res_type": resource_type,
                    "res_id": resource_id,
                }
                if new_status_val:
                    where_sql += " AND CAST(metadata AS jsonb)->>'new_status' = :new_status"
                    params["new_status"] = str(new_status_val)

                existing = (await session.execute(
                    text(f"""
                        SELECT id, organization_id, recipient_user_id, type, title, message, severity,
                               resource_type, resource_id, metadata, is_read, created_at
                        FROM notifications
                        {where_sql}
                    """),
                    params
                )).fetchone()

                if existing:
                    logger.info(
                        "duplicate_notification_prevented recipient=%s type=%s res_type=%s res_id=%s",
                        recipient_user_id, type_str, resource_type, resource_id
                    )
                    meta_dict = existing.metadata if isinstance(existing.metadata, dict) else (json.loads(existing.metadata) if existing.metadata else {})
                    return {
                        "id": str(existing.id),
                        "organization_id": str(existing.organization_id) if existing.organization_id else None,
                        "recipient_user_id": str(existing.recipient_user_id),
                        "type": existing.type,
                        "title": existing.title,
                        "message": existing.message,
                        "severity": existing.severity,
                        "resource_type": existing.resource_type,
                        "resource_id": existing.resource_id,
                        "metadata": meta_dict,
                        "is_read": existing.is_read,
                        "created_at": existing.created_at.isoformat() if hasattr(existing.created_at, "isoformat") else str(existing.created_at),
                        "is_duplicate": True,
                    }

            await session.execute(
                text("""
                    INSERT INTO notifications
                        (id, organization_id, recipient_user_id, type, title, message, severity,
                         resource_type, resource_id, metadata, is_read, created_at)
                    VALUES
                        (:id, :org_id, :recipient_id, :type, :title, :message, :severity,
                         :res_type, :res_id, :meta, false, :created_at)
                """),
                {
                    "id": notification_id,
                    "org_id": organization_id,
                    "recipient_id": recipient_user_id,
                    "type": type_str,
                    "title": title,
                    "message": message,
                    "severity": severity,
                    "res_type": resource_type,
                    "res_id": resource_id,
                    "meta": json.dumps(metadata),
                    "created_at": created_at,
                }
            )
            await session.commit()

        # Send email if enabled and severity is critical/high or assigned
        if email_enabled:
            recipient_user = (await session.execute(
                text("SELECT email FROM users WHERE id = :id"),
                {"id": recipient_user_id}
            )).fetchone()

            if recipient_user and recipient_user.email:
                try:
                    send_escalation_email(
                        to_email=recipient_user.email,
                        alert_title=title,
                        alert_description=message,
                        camera_name=metadata.get("camera_name", "System"),
                        level=1 if severity != "critical" else 3,
                    )
                except Exception as e:
                    logger.warning("email_delivery_failed recipient=%s err=%s", recipient_user_id, e)

        return {
            "id": notification_id,
            "organization_id": organization_id,
            "recipient_user_id": recipient_user_id,
            "type": type_str,
            "title": title,
            "message": message,
            "severity": severity,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "metadata": metadata,
            "is_read": False,
            "created_at": created_at.isoformat(),
        }


async def dispatch_alert_notifications(
    session_factory: async_sessionmaker[AsyncSession],
    alert_row: dict,
) -> None:
    """Dispatches notifications to Org Admins when high or critical alerts occur."""
    severity = str(alert_row.get("severity", "medium")).lower()
    if severity not in ("critical", "high"):
        return

    notification_type = "critical_alert" if severity == "critical" else "high_alert"
    camera_id = alert_row.get("camera_id")

    async with session_factory() as session:
        org_id = None
        camera_name = "Camera"
        zone_name = ""
        site_name = ""
        if camera_id:
            res = await session.execute(
                text("""
                    SELECT COALESCE(c.organization_id, s.organization_id) AS organization_id,
                           c.name AS camera_name, z.name AS zone_name, s.name AS site_name
                    FROM cameras c
                    LEFT JOIN zones z ON c.zone_id = z.id
                    LEFT JOIN sites s ON c.site_id = s.id OR z.site_id = s.id
                    WHERE CAST(c.id AS text) = :cam_id
                """),
                {"cam_id": str(camera_id)}
            )
            row = res.fetchone()
            if row:
                org_id = str(row.organization_id) if row.organization_id else None
                camera_name = row.camera_name or "Camera"
                zone_name = row.zone_name or ""
                site_name = row.site_name or ""

        if not org_id:
            return

        recipients = await session.execute(
            text("""
                SELECT id FROM users
                WHERE (CAST(organization_id AS text) = :org_id AND CAST(role AS text) IN ('org_admin', 'admin'))
                   OR CAST(role AS text) = 'superadmin'
            """),
            {"org_id": org_id}
        )
        recipient_ids = [str(r.id) for r in recipients.fetchall()]

    title = f"{severity.upper()} Alert: {alert_row.get('title', 'Safety Event')}"
    location_parts = [p for p in [site_name, zone_name, camera_name] if p]
    location_str = ", ".join(location_parts) if location_parts else "System"
    message = f"Alert detected at {location_str}. Severity: {severity.upper()}."

    metadata = {
        "camera_id": str(camera_id) if camera_id else None,
        "camera_name": camera_name,
        "zone_name": zone_name,
        "site_name": site_name,
        "source_uc": alert_row.get("source_uc"),
    }

    for uid in recipient_ids:
        n_data = await create_user_notification(
            session_factory=session_factory,
            recipient_user_id=uid,
            organization_id=org_id,
            type_str=notification_type,
            title=title,
            message=message,
            severity=severity,
            resource_type="alert",
            resource_id=str(alert_row.get("id") or alert_row.get("alert_id")),
            metadata=metadata,
        )
        if n_data:
            try:
                from services.alert_management.src.websocket import push_user_notification
                await push_user_notification(uid, n_data)
            except Exception as e:
                logger.debug("failed_to_push_realtime_notification user_id=%s err=%s", uid, e)


async def dispatch_incident_assigned_notification(
    session_factory: async_sessionmaker[AsyncSession],
    incident_dict: dict,
    assigned_to_user_id: str,
) -> None:
    """Notifies a user when an incident is assigned to them."""
    if not assigned_to_user_id:
        return

    inc_id = incident_dict.get("id")
    org_id = incident_dict.get("organization_id")
    title = f"Incident Assigned: #{str(inc_id)[:8]}"
    message = f"You have been assigned to incident: '{incident_dict.get('title', 'Untitled')}'."

    metadata = {
        "incident_id": inc_id,
        "severity": incident_dict.get("severity"),
        "status": incident_dict.get("status"),
    }

    n_data = await create_user_notification(
        session_factory=session_factory,
        recipient_user_id=assigned_to_user_id,
        organization_id=org_id,
        type_str="incident_assigned",
        title=title,
        message=message,
        severity=incident_dict.get("severity", "medium"),
        resource_type="incident",
        resource_id=str(inc_id),
        metadata=metadata,
    )

    if n_data:
        try:
            from services.alert_management.src.websocket import push_user_notification
            await push_user_notification(assigned_to_user_id, n_data)
        except Exception as e:
            logger.debug("failed_to_push_incident_assigned_realtime user_id=%s err=%s", assigned_to_user_id, e)


async def dispatch_incident_status_notification(
    session_factory: async_sessionmaker[AsyncSession],
    incident_dict: dict,
    old_status: str,
    new_status: str,
) -> None:
    """Notifies assigned user and org admins when incident status changes."""
    inc_id = incident_dict.get("id")
    org_id = incident_dict.get("organization_id")
    assigned_to = incident_dict.get("assigned_to")

    recipients_set = set()
    if assigned_to:
        recipients_set.add(str(assigned_to))

    if org_id:
        async with session_factory() as session:
            rows = await session.execute(
                text("SELECT id FROM users WHERE (CAST(organization_id AS text) = :org_id AND CAST(role AS text) IN ('org_admin', 'admin')) OR CAST(role AS text) = 'superadmin'"),
                {"org_id": str(org_id)}
            )
            for r in rows.fetchall():
                recipients_set.add(str(r.id))

    title = f"Incident Status Updated: #{str(inc_id)[:8]}"
    message = f"Incident '{incident_dict.get('title')}' status changed from {old_status.upper()} to {new_status.upper()}."

    metadata = {
        "incident_id": inc_id,
        "old_status": old_status,
        "new_status": new_status,
    }

    for uid in recipients_set:
        n_data = await create_user_notification(
            session_factory=session_factory,
            recipient_user_id=uid,
            organization_id=org_id,
            type_str="incident_status_changed",
            title=title,
            message=message,
            severity=incident_dict.get("severity", "medium"),
            resource_type="incident",
            resource_id=str(inc_id),
            metadata=metadata,
        )
        if n_data:
            try:
                from services.alert_management.src.websocket import push_user_notification
                await push_user_notification(uid, n_data)
            except Exception as e:
                logger.debug("failed_to_push_incident_status_realtime user_id=%s err=%s", uid, e)

