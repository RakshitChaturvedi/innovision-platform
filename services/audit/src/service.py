import json
import logging
import math
from datetime import datetime
from typing import Any, Optional
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.auth.src.rbac import Role
from services.audit.src.writer import write_audit_entry
from services.audit.src.schemas import (
    AuditLogItem,
    AuditLogResponse,
    OrganizationSettings,
    OrganizationUpdate,
    PlatformSettings,
    SecuritySettings,
    SettingsResponse,
    SubscriptionSummaryItem,
)

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def list_audit_logs(
        self,
        user: dict,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        organization_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> AuditLogResponse:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        # Multi-tenant RBAC Enforcement
        if user_role != Role.SUPERADMIN:
            if organization_id and str(organization_id) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization audit access forbidden")
            organization_id = user_org

        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size

        where_clauses: list[str] = []
        params: dict[str, Any] = {"limit": page_size, "offset": offset}

        if start_date:
            try:
                dt_start = datetime.fromisoformat(start_date)
                where_clauses.append("a.timestamp >= :start_date")
                params["start_date"] = dt_start
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date ISO format")

        if end_date:
            try:
                dt_end = datetime.fromisoformat(end_date)
                where_clauses.append("a.timestamp <= :end_date")
                params["end_date"] = dt_end
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date ISO format")

        if organization_id:
            where_clauses.append(
                "(u.organization_id = :org_id OR a.metadata->>'organization_id' = :org_id_str)"
            )
            params["org_id"] = organization_id
            params["org_id_str"] = str(organization_id)

        if actor_user_id:
            where_clauses.append("a.user_id = :actor_user_id")
            params["actor_user_id"] = actor_user_id

        if action:
            where_clauses.append("a.action = :action")
            params["action"] = action

        if resource_type:
            where_clauses.append("a.entity_type = :resource_type")
            params["resource_type"] = resource_type

        if resource_id:
            where_clauses.append("a.entity_id = :resource_id")
            params["resource_id"] = resource_id

        if search:
            where_clauses.append(
                "(a.action ILIKE :search OR a.entity_type ILIKE :search OR a.entity_id ILIKE :search OR "
                "a.service ILIKE :search OR u.name ILIKE :search OR u.email ILIKE :search OR "
                "a.metadata::text ILIKE :search)"
            )
            params["search"] = f"%{search}%"

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        async with self.session_factory() as session:
            count_query = text(f"""
                SELECT COUNT(*)
                FROM audit_log a
                LEFT JOIN users u ON a.user_id = u.id
                {where_sql}
            """)
            count_res = await session.execute(count_query, params)
            total = count_res.scalar() or 0

            data_query = text(f"""
                SELECT
                    a.id,
                    a.timestamp,
                    a.service,
                    a.action,
                    a.entity_type,
                    a.entity_id,
                    a.user_id,
                    u.name as user_name,
                    u.email as user_email,
                    u.role as user_role,
                    a.source_uc,
                    COALESCE(u.organization_id::text, a.metadata->>'organization_id') as organization_id,
                    a.metadata
                FROM audit_log a
                LEFT JOIN users u ON a.user_id = u.id
                {where_sql}
                ORDER BY a.timestamp DESC
                LIMIT :limit OFFSET :offset
            """)
            rows = (await session.execute(data_query, params)).fetchall()

        items = []
        for r in rows:
            if isinstance(r.metadata, dict):
                meta = r.metadata
            elif isinstance(r.metadata, str):
                try:
                    meta = json.loads(r.metadata)
                except Exception:
                    meta = {}
            else:
                meta = {}

            desc = self._generate_description(r.action, r.entity_type, r.entity_id, r.user_name, meta)
            items.append(
                AuditLogItem(
                    id=str(r.id),
                    timestamp=r.timestamp,
                    service=r.service,
                    action=r.action,
                    resource_type=r.entity_type,
                    resource_id=r.entity_id,
                    actor_user_id=str(r.user_id) if r.user_id else None,
                    user_name=r.user_name,
                    user_email=r.user_email,
                    actor_role=r.user_role,
                    source_uc=r.source_uc,
                    organization_id=r.organization_id,
                    description=desc,
                    metadata=meta,
                )
            )

        total_pages = math.ceil(total / page_size) if total > 0 else 1

        return AuditLogResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_audit_log(self, entry_id: str, user: dict) -> AuditLogItem:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        async with self.session_factory() as session:
            query = text("""
                SELECT
                    a.id,
                    a.timestamp,
                    a.service,
                    a.action,
                    a.entity_type,
                    a.entity_id,
                    a.user_id,
                    u.name as user_name,
                    u.email as user_email,
                    u.role as user_role,
                    a.source_uc,
                    COALESCE(u.organization_id::text, a.metadata->>'organization_id') as organization_id,
                    a.metadata
                FROM audit_log a
                LEFT JOIN users u ON a.user_id = u.id
                WHERE a.id = :id
            """)
            row = (await session.execute(query, {"id": entry_id})).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Audit log entry not found")

        org_id = row.organization_id
        if user_role != Role.SUPERADMIN:
            if not user_org or (org_id and str(org_id) != str(user_org)):
                raise HTTPException(status_code=403, detail="Cross-organization audit access forbidden")

        if isinstance(row.metadata, dict):
            meta = row.metadata
        elif isinstance(row.metadata, str):
            try:
                meta = json.loads(row.metadata)
            except Exception:
                meta = {}
        else:
            meta = {}

        desc = self._generate_description(row.action, row.entity_type, row.entity_id, row.user_name, meta)

        return AuditLogItem(
            id=str(row.id),
            timestamp=row.timestamp,
            service=row.service,
            action=row.action,
            resource_type=row.entity_type,
            resource_id=row.entity_id,
            actor_user_id=str(row.user_id) if row.user_id else None,
            user_name=row.user_name,
            user_email=row.user_email,
            actor_role=row.user_role,
            source_uc=row.source_uc,
            organization_id=org_id,
            description=desc,
            metadata=meta,
        )

    def _generate_description(
        self, action: str, entity_type: str, entity_id: str, actor_name: Optional[str], metadata: dict
    ) -> str:
        actor = actor_name or "System"
        readable_action = action.replace("_", " ").title()
        readable_entity = entity_type.replace("_", " ").title()

        if action == "organization_updated":
            new_name = metadata.get("name") or metadata.get("new_name")
            return f"{actor} updated organization settings for '{new_name or entity_id}'"
        elif action == "user_login":
            return f"{actor} logged in successfully"
        elif action == "user_created":
            return f"{actor} created new user ({entity_id})"
        elif action == "incident_created":
            return f"{actor} created new incident ({entity_id})"
        elif action == "incident_status_changed":
            to_s = metadata.get("to_status", "")
            return f"{actor} changed incident ({entity_id}) status to '{to_s}'"

        return f"{actor} performed {readable_action} on {readable_entity} ({entity_id})"


class SettingsService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self.session_factory = session_factory

    async def get_settings(self, user: dict, target_org_id: Optional[str] = None) -> SettingsResponse:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        if user_role != Role.SUPERADMIN:
            if target_org_id and str(target_org_id) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization settings access forbidden")
            org_id = user_org
        else:
            org_id = target_org_id or user_org

        org_settings: Optional[OrganizationSettings] = None
        subscriptions: list[SubscriptionSummaryItem] = []

        async with self.session_factory() as session:
            # Fetch Organization details
            if org_id:
                org_row = (await session.execute(
                    text("SELECT id, name, code, tier, timezone, is_active, created_at, updated_at FROM organizations WHERE id = :id"),
                    {"id": org_id}
                )).fetchone()
                if org_row:
                    org_settings = OrganizationSettings(
                        id=str(org_row.id),
                        name=org_row.name,
                        code=org_row.code,
                        tier=org_row.tier,
                        timezone=org_row.timezone,
                        is_active=org_row.is_active,
                        created_at=org_row.created_at,
                        updated_at=org_row.updated_at,
                    )
            else:
                # If SUPERADMIN with no specific org selected, grab first available org
                org_row = (await session.execute(
                    text("SELECT id, name, code, tier, timezone, is_active, created_at, updated_at FROM organizations ORDER BY created_at ASC LIMIT 1")
                )).fetchone()
                if org_row:
                    org_settings = OrganizationSettings(
                        id=str(org_row.id),
                        name=org_row.name,
                        code=org_row.code,
                        tier=org_row.tier,
                        timezone=org_row.timezone,
                        is_active=org_row.is_active,
                        created_at=org_row.created_at,
                        updated_at=org_row.updated_at,
                    )
                    org_id = str(org_row.id)

            # Fetch analytics subscriptions for this organization
            if org_id:
                sub_rows = (await session.execute(
                    text("""
                        SELECT
                            a.id as analytic_id,
                            a.display_name as name,
                            a.code,
                            a.description,
                            CASE WHEN os.is_enabled IS TRUE THEN 'active' ELSE 'disabled' END as status
                        FROM analytics_catalog a
                        LEFT JOIN organization_subscriptions os
                            ON a.id = os.analytic_id AND os.organization_id = :org_id
                        ORDER BY a.code ASC
                    """),
                    {"org_id": org_id}
                )).fetchall()

                for s in sub_rows:
                    subscriptions.append(
                        SubscriptionSummaryItem(
                            analytic_id=str(s.analytic_id),
                            name=s.name,
                            code=s.code.upper(),
                            status=str(s.status),
                            description=s.description,
                        )
                    )

        security_settings = SecuritySettings(
            auth_provider="Enterprise JWT Authentication",
            session_duration="24 Hours",
            supported_roles=["superadmin", "org_admin"],
            user_management_url="/admin/users",
        )

        platform_settings = PlatformSettings(
            platform_name="Innovision Industrial Safety & Video Intelligence",
            version="v2.4.0",
            environment="Production",
            status="healthy",
            services_count=6,
        )

        return SettingsResponse(
            organization=org_settings,
            security=security_settings,
            platform=platform_settings,
            subscriptions=subscriptions,
        )

    async def update_organization_settings(
        self, user: dict, update_data: OrganizationUpdate, target_org_id: Optional[str] = None
    ) -> OrganizationSettings:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")
        user_id = user.get("sub")

        if user_role != Role.SUPERADMIN:
            if target_org_id and str(target_org_id) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization settings update forbidden")
            org_id = user_org
        else:
            org_id = target_org_id or user_org

        if not org_id:
            raise HTTPException(status_code=400, detail="Organization ID is required")

        async with self.session_factory() as session:
            async with session.begin():
                org_row = (await session.execute(
                    text("SELECT id, name, code, tier, timezone, is_active, created_at, updated_at FROM organizations WHERE id = :id FOR UPDATE"),
                    {"id": org_id}
                )).fetchone()

                if not org_row:
                    raise HTTPException(status_code=404, detail="Organization not found")

                updates = []
                params: dict[str, Any] = {"id": org_id}
                changes: dict[str, Any] = {"organization_id": str(org_id)}

                if update_data.name is not None and update_data.name != org_row.name:
                    updates.append("name = :name")
                    params["name"] = update_data.name
                    changes["previous_name"] = org_row.name
                    changes["new_name"] = update_data.name

                if update_data.timezone is not None and update_data.timezone != org_row.timezone:
                    updates.append("timezone = :timezone")
                    params["timezone"] = update_data.timezone
                    changes["previous_timezone"] = org_row.timezone
                    changes["new_timezone"] = update_data.timezone

                if updates:
                    updates.append("updated_at = now()")
                    update_sql = f"UPDATE organizations SET {', '.join(updates)} WHERE id = :id"
                    await session.execute(text(update_sql), params)

                updated_row = (await session.execute(
                    text("SELECT id, name, code, tier, timezone, is_active, created_at, updated_at FROM organizations WHERE id = :id"),
                    {"id": org_id}
                )).fetchone()

        # Audit log write
        if updates:
            await write_audit_entry(
                session_factory=self.session_factory,
                service="settings",
                action="organization_updated",
                entity_type="organization",
                entity_id=str(org_id),
                user_id=user_id,
                metadata=changes,
            )

        return OrganizationSettings(
            id=str(updated_row.id),
            name=updated_row.name,
            code=updated_row.code,
            tier=updated_row.tier,
            timezone=updated_row.timezone,
            is_active=updated_row.is_active,
            created_at=updated_row.created_at,
            updated_at=updated_row.updated_at,
        )
