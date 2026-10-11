import logging
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from services.audit.src.writer import write_audit_entry
from services.auth.src.rbac import Role
from .workflow import is_valid_transition, all_valid_next_states, IncidentStatus
from .timeline import append_entry, fetch_timeline

logger = logging.getLogger(__name__)

class IncidentService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def list_incidents(
        self,
        user: dict,
        status: str | None = None,
        severity: str | None = None,
        organization_id: str | None = None,
        site_id: str | None = None,
        zone_id: str | None = None,
        camera_id: str | None = None,
        assigned_to: str | None = None,
        source_type: str | None = None,
        limit: int = 50,
        offset: int = 0
    ) -> list[dict]:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        conditions = []
        params = {"limit": limit, "offset": offset}

        # RBAC organization isolation
        if user_role != Role.SUPERADMIN:
            if not user_org:
                raise HTTPException(status_code=403, detail="User has no assigned organization")
            if organization_id and str(organization_id) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
            conditions.append("i.organization_id = :org_id")
            params["org_id"] = str(user_org)
        elif organization_id:
            conditions.append("i.organization_id = :org_id")
            params["org_id"] = str(organization_id)

        if status:
            conditions.append("i.status = :status")
            params["status"] = status
        if severity:
            conditions.append("i.severity = :severity")
            params["severity"] = severity
        if site_id:
            conditions.append("i.site_id = :site_id")
            params["site_id"] = str(site_id)
        if zone_id:
            conditions.append("i.zone_id = :zone_id")
            params["zone_id"] = str(zone_id)
        if camera_id:
            conditions.append("i.camera_id = :camera_id")
            params["camera_id"] = str(camera_id)
        if assigned_to:
            conditions.append("i.assigned_to = :assigned_to")
            params["assigned_to"] = str(assigned_to)
        if source_type:
            conditions.append("i.source_type = :source_type")
            params["source_type"] = source_type

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        async with self._session_factory() as session:
            rows = await session.execute(text(f"""
                SELECT i.id, i.title, i.description, i.severity, i.status,
                       i.organization_id, o.name AS organization_name,
                       i.site_id, s.name AS site_name,
                       i.zone_id, z.name AS zone_name,
                       i.camera_id, c.name AS camera_name,
                       i.source_type, i.created_by, cb.name AS created_by_name,
                       i.assigned_to, u.name AS assigned_to_name,
                       i.created_at, i.updated_at, i.acknowledged_at, i.investigating_at, i.resolved_at, i.closed_at
                FROM incidents i
                LEFT JOIN organizations o ON i.organization_id = o.id
                LEFT JOIN sites s ON i.site_id = s.id
                LEFT JOIN zones z ON i.zone_id = z.id
                LEFT JOIN cameras c ON i.camera_id = c.id
                LEFT JOIN users u ON i.assigned_to = u.id
                LEFT JOIN users cb ON i.created_by = cb.id
                {where_clause}
                ORDER BY i.created_at DESC
                LIMIT :limit OFFSET :offset
            """), params)

            results = []
            for r in rows.fetchall():
                m = dict(r._mapping)
                m["id"] = str(m["id"])
                m["organization_id"] = str(m["organization_id"]) if m.get("organization_id") else None
                m["site_id"] = str(m["site_id"]) if m.get("site_id") else None
                m["zone_id"] = str(m["zone_id"]) if m.get("zone_id") else None
                m["camera_id"] = str(m["camera_id"]) if m.get("camera_id") else None
                m["created_by"] = str(m["created_by"]) if m.get("created_by") else None
                m["assigned_to"] = str(m["assigned_to"]) if m.get("assigned_to") else None
                m["created_at"] = m["created_at"].isoformat() if m.get("created_at") else None
                m["updated_at"] = m["updated_at"].isoformat() if m.get("updated_at") else None
                m["acknowledged_at"] = m["acknowledged_at"].isoformat() if m.get("acknowledged_at") else None
                m["investigating_at"] = m["investigating_at"].isoformat() if m.get("investigating_at") else None
                m["resolved_at"] = m["resolved_at"].isoformat() if m.get("resolved_at") else None
                m["closed_at"] = m["closed_at"].isoformat() if m.get("closed_at") else None
                results.append(m)
            return results

    async def get_incident(self, incident_id: str, user: dict) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        async with self._session_factory() as session:
            row = await session.execute(text("""
                SELECT i.id, i.title, i.description, i.severity, i.status,
                       i.organization_id, o.name AS organization_name,
                       i.site_id, s.name AS site_name,
                       i.zone_id, z.name AS zone_name,
                       i.camera_id, c.name AS camera_name,
                       i.source_type, i.created_by, cb.name AS created_by_name,
                       i.assigned_to, u.name AS assigned_to_name,
                       i.created_at, i.updated_at, i.acknowledged_at, i.investigating_at, i.resolved_at, i.closed_at
                FROM incidents i
                LEFT JOIN organizations o ON i.organization_id = o.id
                LEFT JOIN sites s ON i.site_id = s.id
                LEFT JOIN zones z ON i.zone_id = z.id
                LEFT JOIN cameras c ON i.camera_id = c.id
                LEFT JOIN users u ON i.assigned_to = u.id
                LEFT JOIN users cb ON i.created_by = cb.id
                WHERE i.id = :id
            """), {"id": incident_id})
            inc = row.fetchone()
            if not inc:
                raise HTTPException(status_code=404, detail="Incident not found")

            inc_dict = dict(inc._mapping)
            if user_role != Role.SUPERADMIN:
                if not user_org or str(user_org) != str(inc_dict["organization_id"]):
                    raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

            # Fetch linked alerts
            alerts_row = await session.execute(text("""
                SELECT ia.alert_id, ia.linked_at, a.source_uc, a.title, a.severity, a.camera_id, a.created_at AS timestamp
                FROM incident_alerts ia
                JOIN alerts a ON ia.alert_id = a.id OR ia.alert_id = a.alert_id
                WHERE ia.incident_id = :id
                ORDER BY ia.linked_at DESC
            """), {"id": incident_id})

            linked_alerts = [
                {
                    "alert_id": str(r.alert_id),
                    "source_uc": r.source_uc,
                    "title": r.title,
                    "severity": r.severity,
                    "camera_id": str(r.camera_id) if r.camera_id else None,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                    "linked_at": r.linked_at.isoformat() if r.linked_at else None,
                }
                for r in alerts_row.fetchall()
            ]

            timeline = await fetch_timeline(session, incident_id)

            inc_dict["id"] = str(inc_dict["id"])
            inc_dict["organization_id"] = str(inc_dict["organization_id"]) if inc_dict.get("organization_id") else None
            inc_dict["site_id"] = str(inc_dict["site_id"]) if inc_dict.get("site_id") else None
            inc_dict["zone_id"] = str(inc_dict["zone_id"]) if inc_dict.get("zone_id") else None
            inc_dict["camera_id"] = str(inc_dict["camera_id"]) if inc_dict.get("camera_id") else None
            inc_dict["created_by"] = str(inc_dict["created_by"]) if inc_dict.get("created_by") else None
            inc_dict["assigned_to"] = str(inc_dict["assigned_to"]) if inc_dict.get("assigned_to") else None
            inc_dict["created_at"] = inc_dict["created_at"].isoformat() if inc_dict.get("created_at") else None
            inc_dict["updated_at"] = inc_dict["updated_at"].isoformat() if inc_dict.get("updated_at") else None
            inc_dict["acknowledged_at"] = inc_dict["acknowledged_at"].isoformat() if inc_dict.get("acknowledged_at") else None
            inc_dict["investigating_at"] = inc_dict["investigating_at"].isoformat() if inc_dict.get("investigating_at") else None
            inc_dict["resolved_at"] = inc_dict["resolved_at"].isoformat() if inc_dict.get("resolved_at") else None
            inc_dict["closed_at"] = inc_dict["closed_at"].isoformat() if inc_dict.get("closed_at") else None
            inc_dict["linked_alerts"] = linked_alerts

            return {
                "incident": inc_dict,
                "linked_alerts": linked_alerts,
                "timeline": timeline,
                "valid_next_states": all_valid_next_states(inc_dict["status"]),
            }

    async def create_incident(self, data: dict, user: dict) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        target_org_id = data.get("organization_id")
        if user_role != Role.SUPERADMIN:
            if not user_org:
                raise HTTPException(status_code=403, detail="User has no assigned organization")
            target_org_id = str(user_org)
        elif not target_org_id:
            raise HTTPException(status_code=400, detail="Organization ID is required when creating an incident as SUPERADMIN")

        incident_id = str(uuid.uuid4())
        created_by_id = user.get("sub")

        site_id = str(data.get("site_id")) if data.get("site_id") else None
        zone_id = str(data.get("zone_id")) if data.get("zone_id") else None
        camera_id = str(data.get("camera_id")) if data.get("camera_id") else None
        assigned_to = str(data.get("assigned_to")) if data.get("assigned_to") else None
        alert_ids = data.get("alert_ids") or []

        async with self._session_factory() as session:
            async with session.begin():
                # Validate organization exists
                org_check = await session.execute(text("SELECT id FROM organizations WHERE id = :id"), {"id": target_org_id})
                if not org_check.fetchone():
                    raise HTTPException(status_code=404, detail=f"Organization {target_org_id} not found")

                # Validate site belongs to org if provided
                if site_id:
                    s_check = await session.execute(text("SELECT id FROM sites WHERE id = :id AND organization_id = :org_id"), {"id": site_id, "org_id": target_org_id})
                    if not s_check.fetchone():
                        raise HTTPException(status_code=400, detail="Referenced site does not belong to target organization")

                # Validate assigned_to user belongs to org if provided
                if assigned_to:
                    u_check = await session.execute(text("SELECT id FROM users WHERE id = :id AND (organization_id = :org_id OR role = 'superadmin')"), {"id": assigned_to, "org_id": target_org_id})
                    if not u_check.fetchone():
                        raise HTTPException(status_code=400, detail="Assigned user does not belong to target organization")

                # Insert incident
                await session.execute(text("""
                    INSERT INTO incidents (
                        id, organization_id, site_id, zone_id, camera_id,
                        title, description, severity, status, source_type,
                        created_by, assigned_to, created_at, updated_at
                    ) VALUES (
                        :id, :org_id, :site_id, :zone_id, :camera_id,
                        :title, :description, :severity, 'open', :source_type,
                        :created_by, :assigned_to, now(), now()
                    )
                """), {
                    "id": incident_id,
                    "org_id": target_org_id,
                    "site_id": site_id,
                    "zone_id": zone_id,
                    "camera_id": camera_id,
                    "title": data["title"],
                    "description": data.get("description"),
                    "severity": data.get("severity", "medium"),
                    "source_type": data.get("source_type", "alert"),
                    "created_by": created_by_id,
                    "assigned_to": assigned_to,
                })

                # Link alerts if provided
                for a_id in alert_ids:
                    alert_row = await session.execute(text("""
                        SELECT id FROM alerts WHERE id::text = :a_id OR alert_id::text = :a_id
                    """), {"a_id": str(a_id)})
                    found_alert = alert_row.fetchone()
                    if not found_alert:
                        raise HTTPException(status_code=404, detail=f"Alert {a_id} not found")

                    actual_alert_id = str(found_alert.id)
                    await session.execute(text("""
                        INSERT INTO incident_alerts (incident_id, alert_id, linked_at, linked_by)
                        VALUES (:inc_id, :alert_id, now(), :linked_by)
                        ON CONFLICT DO NOTHING
                    """), {"inc_id": incident_id, "alert_id": actual_alert_id, "linked_by": created_by_id})

                await append_entry(
                    session, incident_id, action="created", user_id=created_by_id,
                    note=f"Incident created with title '{data['title']}'"
                )

                await write_audit_entry(
                    self._session_factory, service="incident_management",
                    action="incident_created", entity_type="incident",
                    entity_id=incident_id, user_id=created_by_id,
                    metadata={"title": data["title"], "organization_id": target_org_id, "severity": data.get("severity", "medium")},
                    session=session
                )

        result = await self.get_incident(incident_id, user)
        if assigned_to:
            try:
                from services.notification.src.service import dispatch_incident_assigned_notification
                await dispatch_incident_assigned_notification(self._session_factory, result["incident"], assigned_to)
            except Exception as e:
                logger.warning("failed_to_dispatch_incident_created_notification err=%s", e)

        return result

    async def update_incident(self, incident_id: str, data: dict, user: dict) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        async with self._session_factory() as session:
            async with session.begin():
                inc_row = await session.execute(text("SELECT id, organization_id FROM incidents WHERE id = :id"), {"id": incident_id})
                inc = inc_row.fetchone()
                if not inc:
                    raise HTTPException(status_code=404, detail="Incident not found")

                if user_role != Role.SUPERADMIN:
                    if not user_org or str(user_org) != str(inc.organization_id):
                        raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

                updates = []
                params = {"id": incident_id}

                if "title" in data and data["title"]:
                    updates.append("title = :title")
                    params["title"] = data["title"]
                if "description" in data:
                    updates.append("description = :description")
                    params["description"] = data["description"]
                if "severity" in data and data["severity"]:
                    updates.append("severity = :severity")
                    params["severity"] = data["severity"]
                if "site_id" in data:
                    updates.append("site_id = :site_id")
                    params["site_id"] = str(data["site_id"]) if data["site_id"] else None
                if "zone_id" in data:
                    updates.append("zone_id = :zone_id")
                    params["zone_id"] = str(data["zone_id"]) if data["zone_id"] else None
                if "camera_id" in data:
                    updates.append("camera_id = :camera_id")
                    params["camera_id"] = str(data["camera_id"]) if data["camera_id"] else None
                if "assigned_to" in data:
                    updates.append("assigned_to = :assigned_to")
                    params["assigned_to"] = str(data["assigned_to"]) if data["assigned_to"] else None

                if updates:
                    updates.append("updated_at = now()")
                    await session.execute(text(f"UPDATE incidents SET {', '.join(updates)} WHERE id = :id"), params)
                    await append_entry(session, incident_id, action="updated", user_id=user.get("sub"), note="Incident details updated")
                    await write_audit_entry(
                        self._session_factory, service="incident_management",
                        action="incident_updated", entity_type="incident",
                        entity_id=incident_id, user_id=user.get("sub"),
                        metadata={"updated_fields": list(params.keys())},
                        session=session
                    )

        return await self.get_incident(incident_id, user)

    async def update_status(self, incident_id: str, new_status: str, user: dict) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        async with self._session_factory() as session:
            async with session.begin():
                inc_row = await session.execute(text("SELECT id, status, organization_id FROM incidents WHERE id = :id"), {"id": incident_id})
                inc = inc_row.fetchone()
                if not inc:
                    raise HTTPException(status_code=404, detail="Incident not found")

                if user_role != Role.SUPERADMIN:
                    if not user_org or str(user_org) != str(inc.organization_id):
                        raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

                current_status = inc.status
                # normalize 'open' vs 'active'
                current_norm = "open" if current_status == "active" else current_status
                target_norm = "open" if new_status == "active" else new_status

                if current_norm != target_norm and not is_valid_transition(current_norm, target_norm):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot transition from '{current_norm}' to '{target_norm}'. Valid next states: {all_valid_next_states(current_norm)}"
                    )

                if target_norm == "closed":
                    if user_role not in (Role.SUPERADMIN, Role.ADMIN, Role.ORG_ADMIN):
                        raise HTTPException(
                            status_code=403,
                            detail="Only organization administrators and superadmins can close incidents"
                        )

                timestamp_updates = []
                if target_norm == "acknowledged":
                    timestamp_updates.append("acknowledged_at = COALESCE(acknowledged_at, now())")
                elif target_norm == "investigating":
                    timestamp_updates.append("investigating_at = COALESCE(investigating_at, now())")
                elif target_norm == "resolved":
                    timestamp_updates.append("resolved_at = COALESCE(resolved_at, now())")
                elif target_norm == "closed":
                    timestamp_updates.append("closed_at = COALESCE(closed_at, now())")

                ts_sql = f", {', '.join(timestamp_updates)}" if timestamp_updates else ""

                await session.execute(text(f"""
                    UPDATE incidents SET status = :status, updated_at = now() {ts_sql}
                    WHERE id = :id
                """), {"status": target_norm, "id": incident_id})

                await append_entry(
                    session, incident_id, action="status_changed", user_id=user.get("sub"),
                    from_status=current_status, to_status=target_norm
                )

                await write_audit_entry(
                    self._session_factory, service="incident_management",
                    action="incident_status_changed", entity_type="incident",
                    entity_id=incident_id, user_id=user.get("sub"),
                    metadata={"from": current_status, "to": target_norm, "organization_id": str(inc.organization_id)},
                    session=session
                )

        result = await self.get_incident(incident_id, user)
        try:
            from services.notification.src.service import dispatch_incident_status_notification
            await dispatch_incident_status_notification(self._session_factory, result["incident"], current_status, target_norm)
        except Exception as e:
            logger.warning("failed_to_dispatch_incident_status_notification err=%s", e)

        return result

    async def assign_incident(self, incident_id: str, assignee_id: str | None, user: dict) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        async with self._session_factory() as session:
            async with session.begin():
                inc_row = await session.execute(text("SELECT id, organization_id FROM incidents WHERE id = :id"), {"id": incident_id})
                inc = inc_row.fetchone()
                if not inc:
                    raise HTTPException(status_code=404, detail="Incident not found")

                if user_role != Role.SUPERADMIN:
                    if not user_org or str(user_org) != str(inc.organization_id):
                        raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

                if assignee_id:
                    u_row = await session.execute(text("SELECT id, name, organization_id FROM users WHERE id = :id"), {"id": assignee_id})
                    target_u = u_row.fetchone()
                    if not target_u:
                        raise HTTPException(status_code=404, detail="Assigned user not found")
                    if user_role != Role.SUPERADMIN and str(target_u.organization_id) != str(inc.organization_id):
                        raise HTTPException(status_code=400, detail="Assigned user does not belong to the same organization")
                    assignee_name = target_u.name
                else:
                    assignee_name = "Unassigned"

                await session.execute(text("UPDATE incidents SET assigned_to = :assignee_id, updated_at = now() WHERE id = :id"), {
                    "assignee_id": assignee_id, "id": incident_id
                })

                await append_entry(
                    session, incident_id, action="assigned", user_id=user.get("sub"),
                    note=f"Assigned to {assignee_name}"
                )

                await write_audit_entry(
                    self._session_factory, service="incident_management",
                    action="incident_assigned", entity_type="incident",
                    entity_id=incident_id, user_id=user.get("sub"),
                    metadata={"assigned_to": assignee_id, "organization_id": str(inc.organization_id)},
                    session=session
                )

        result = await self.get_incident(incident_id, user)
        if assignee_id:
            try:
                from services.notification.src.service import dispatch_incident_assigned_notification
                await dispatch_incident_assigned_notification(self._session_factory, result["incident"], assignee_id)
            except Exception as e:
                logger.warning("failed_to_dispatch_incident_assigned_notification err=%s", e)

        return result

    async def link_alert(self, incident_id: str, alert_id: str, user: dict) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        async with self._session_factory() as session:
            async with session.begin():
                inc_row = await session.execute(text("SELECT id, organization_id FROM incidents WHERE id = :id"), {"id": incident_id})
                inc = inc_row.fetchone()
                if not inc:
                    raise HTTPException(status_code=404, detail="Incident not found")

                if user_role != Role.SUPERADMIN:
                    if not user_org or str(user_org) != str(inc.organization_id):
                        raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

                alert_row = await session.execute(text("""
                    SELECT id, camera_id FROM alerts WHERE id::text = :a_id OR alert_id::text = :a_id
                """), {"a_id": alert_id})
                found_alert = alert_row.fetchone()
                if not found_alert:
                    raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

                actual_alert_id = str(found_alert.id)

                await session.execute(text("""
                    INSERT INTO incident_alerts (incident_id, alert_id, linked_at, linked_by)
                    VALUES (:inc_id, :alert_id, now(), :linked_by)
                    ON CONFLICT DO NOTHING
                """), {"inc_id": incident_id, "alert_id": actual_alert_id, "linked_by": user.get("sub")})

                await append_entry(
                    session, incident_id, action="alert_linked", user_id=user.get("sub"),
                    note=f"Alert {actual_alert_id} linked to incident"
                )

                await write_audit_entry(
                    self._session_factory, service="incident_management",
                    action="incident_alert_linked", entity_type="incident",
                    entity_id=incident_id, user_id=user.get("sub"),
                    metadata={"alert_id": actual_alert_id, "organization_id": str(inc.organization_id)},
                    session=session
                )

        return await self.get_incident(incident_id, user)

    async def unlink_alert(self, incident_id: str, alert_id: str, user: dict) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        async with self._session_factory() as session:
            async with session.begin():
                inc_row = await session.execute(text("SELECT id, organization_id FROM incidents WHERE id = :id"), {"id": incident_id})
                inc = inc_row.fetchone()
                if not inc:
                    raise HTTPException(status_code=404, detail="Incident not found")

                if user_role != Role.SUPERADMIN:
                    if not user_org or str(user_org) != str(inc.organization_id):
                        raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

                await session.execute(text("""
                    DELETE FROM incident_alerts
                    WHERE incident_id = :inc_id AND (alert_id::text = :alert_id OR alert_id IN (SELECT id FROM alerts WHERE alert_id::text = :alert_id))
                """), {"inc_id": incident_id, "alert_id": alert_id})

                await append_entry(
                    session, incident_id, action="alert_unlinked", user_id=user.get("sub"),
                    note=f"Alert {alert_id} unlinked from incident"
                )

                await write_audit_entry(
                    self._session_factory, service="incident_management",
                    action="incident_alert_unlinked", entity_type="incident",
                    entity_id=incident_id, user_id=user.get("sub"),
                    metadata={"alert_id": alert_id, "organization_id": str(inc.organization_id)},
                    session=session
                )

        return await self.get_incident(incident_id, user)

    async def get_incident_summary(self, user: dict, organization_id: str | None = None) -> dict:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        conditions = []
        params = {}

        if user_role != Role.SUPERADMIN:
            conditions.append("organization_id = :org_id")
            params["org_id"] = str(user_org)
        elif organization_id:
            conditions.append("organization_id = :org_id")
            params["org_id"] = str(organization_id)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        async with self._session_factory() as session:
            row = await session.execute(text(f"""
                SELECT
                    COUNT(CASE WHEN status IN ('open', 'active') THEN 1 END) AS open_count,
                    COUNT(CASE WHEN status = 'investigating' THEN 1 END) AS investigating_count,
                    COUNT(CASE WHEN severity = 'critical' AND status NOT IN ('closed', 'resolved') THEN 1 END) AS critical_count,
                    COUNT(CASE WHEN status = 'resolved' AND resolved_at >= DATE_TRUNC('day', now()) THEN 1 END) AS resolved_today_count
                FROM incidents
                {where_clause}
            """), params)
            r = row.fetchone()
            return {
                "open_count": r.open_count or 0,
                "investigating_count": r.investigating_count or 0,
                "critical_count": r.critical_count or 0,
                "resolved_today_count": r.resolved_today_count or 0,
            }
