import os
import logging
import uuid
import json
from datetime import datetime, timezone
import redis.asyncio as aioredis

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from services.camera_registry.src.schemas import (
    CameraCreate, CameraConfigUpdate,
    OrganizationCreate, OrganizationUpdate, OrganizationStatusUpdate,
    SiteCreate, SiteUpdate,
    ZoneCreate, ZoneUpdate,
    OrganizationSubscriptionCreate, OrganizationSubscriptionUpdate,
    ZonePPERuleItem
)

logger = logging.getLogger(__name__)

class CameraRegistryService:
    def __init__(self, session_factory, redis_client: aioredis.Redis):
        self._session_factory = session_factory
        self._redis = redis_client

    # --- Organizations ---
    async def create_organization(self, data: OrganizationCreate) -> dict:
        org_id = str(uuid.uuid4())
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    INSERT INTO organizations (id, name, code, tier, is_active)
                    VALUES (:id, :name, :code, :tier, :is_active)
                """), {
                    "id": org_id,
                    "name": data.name,
                    "code": data.code,
                    "tier": data.tier,
                    "is_active": data.is_active
                })
                row = await session.execute(text("SELECT id, name, code, tier, is_active, created_at, updated_at FROM organizations WHERE id = :id"), {"id": org_id})
                return dict(row.fetchone()._mapping)

    async def list_organizations(self) -> list[dict]:
        async with self._session_factory() as session:
            rows = await session.execute(text("SELECT id, name, code, tier, is_active, created_at, updated_at FROM organizations ORDER BY created_at DESC"))
            return [dict(r._mapping) for r in rows.fetchall()]

    async def get_organization(self, org_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.execute(text("SELECT id, name, code, tier, is_active, created_at, updated_at FROM organizations WHERE id = :id"), {"id": org_id})
            res = row.fetchone()
            return dict(res._mapping) if res else None

    async def update_organization(self, org_id: str, data: OrganizationUpdate) -> dict | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.execute(text("SELECT id FROM organizations WHERE id = :id"), {"id": org_id})
                if not row.fetchone():
                    return None
                updates = []
                params = {"id": org_id}
                if data.name is not None:
                    updates.append("name = :name")
                    params["name"] = data.name
                if data.tier is not None:
                    updates.append("tier = :tier")
                    params["tier"] = data.tier
                if updates:
                    updates.append("updated_at = now()")
                    await session.execute(text(f"UPDATE organizations SET {', '.join(updates)} WHERE id = :id"), params)
                r = await session.execute(text("SELECT id, name, code, tier, is_active, created_at, updated_at FROM organizations WHERE id = :id"), {"id": org_id})
                return dict(r.fetchone()._mapping)

    async def update_organization_status(self, org_id: str, is_active: bool) -> dict | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.execute(text("SELECT id FROM organizations WHERE id = :id"), {"id": org_id})
                if not row.fetchone():
                    return None
                await session.execute(text("UPDATE organizations SET is_active = :is_active, updated_at = now() WHERE id = :id"), {"id": org_id, "is_active": is_active})
                r = await session.execute(text("SELECT id, name, code, tier, is_active, created_at, updated_at FROM organizations WHERE id = :id"), {"id": org_id})
                return dict(r.fetchone()._mapping)

    # --- Sites ---
    async def create_site(self, data: SiteCreate) -> dict:
        site_id = str(uuid.uuid4())
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    INSERT INTO sites (id, organization_id, name, code, address, timezone)
                    VALUES (:id, :organization_id, :name, :code, :address, :timezone)
                """), {
                    "id": site_id,
                    "organization_id": str(data.organization_id),
                    "name": data.name,
                    "code": data.code,
                    "address": data.address,
                    "timezone": data.timezone
                })
                row = await session.execute(text("SELECT id, organization_id, name, code, address, timezone, created_at, updated_at FROM sites WHERE id = :id"), {"id": site_id})
                return dict(row.fetchone()._mapping)

    async def list_sites(self, organization_id: str | None = None) -> list[dict]:
        async with self._session_factory() as session:
            if organization_id:
                rows = await session.execute(text("SELECT id, organization_id, name, code, address, timezone, created_at, updated_at FROM sites WHERE organization_id = :org_id ORDER BY created_at DESC"), {"org_id": organization_id})
            else:
                rows = await session.execute(text("SELECT id, organization_id, name, code, address, timezone, created_at, updated_at FROM sites ORDER BY created_at DESC"))
            return [dict(r._mapping) for r in rows.fetchall()]

    async def get_site(self, site_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.execute(text("SELECT id, organization_id, name, code, address, timezone, created_at, updated_at FROM sites WHERE id = :id"), {"id": site_id})
            res = row.fetchone()
            return dict(res._mapping) if res else None

    async def update_site(self, site_id: str, data: SiteUpdate) -> dict | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.execute(text("SELECT id FROM sites WHERE id = :id"), {"id": site_id})
                if not row.fetchone():
                    return None
                updates = []
                params = {"id": site_id}
                if data.name is not None:
                    updates.append("name = :name")
                    params["name"] = data.name
                if data.code is not None:
                    updates.append("code = :code")
                    params["code"] = data.code
                if data.address is not None:
                    updates.append("address = :address")
                    params["address"] = data.address
                if data.timezone is not None:
                    updates.append("timezone = :timezone")
                    params["timezone"] = data.timezone
                if updates:
                    updates.append("updated_at = now()")
                    await session.execute(text(f"UPDATE sites SET {', '.join(updates)} WHERE id = :id"), params)
                r = await session.execute(text("SELECT id, organization_id, name, code, address, timezone, created_at, updated_at FROM sites WHERE id = :id"), {"id": site_id})
                return dict(r.fetchone()._mapping)

    async def delete_site(self, site_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                # 1. Dependency check: child zones
                z_count = await session.execute(text("SELECT count(*) FROM zones WHERE site_id = :id"), {"id": site_id})
                if z_count.scalar() > 0:
                    raise ValueError("Cannot delete site: child zones are associated with this site. Remove or reassign zones first.")

                # 2. Dependency check: any cameras referencing this site (including decommissioned)
                c_count = await session.execute(
                    text("SELECT count(*) FROM cameras WHERE site_id = :id"),
                    {"id": site_id}
                )
                if c_count.scalar() > 0:
                    raise ValueError("Cannot delete site: cameras (including decommissioned cameras) reference this site. Reassign cameras to another site before deleting.")

                # 3. Dependency check: historical incidents
                try:
                    i_count = await session.execute(
                        text("SELECT count(*) FROM incidents WHERE site_id = :id"),
                        {"id": site_id}
                    )
                    if i_count.scalar() > 0:
                        raise ValueError("Cannot delete site: historical incidents reference this site. Reassign incidents or retain site for compliance history.")
                except ValueError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to verify historical incidents dependency for site {site_id}: {e}")
                    raise RuntimeError(f"Database error during site historical dependency check: {e}. Site deletion aborted.")

                await session.execute(text("DELETE FROM sites WHERE id = :id"), {"id": site_id})

    # --- Zones ---
    async def create_zone(self, data: ZoneCreate) -> dict:
        zone_id = str(uuid.uuid4())
        slug = data.slug or f"{data.name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    INSERT INTO zones (id, site_id, name, slug, description, zone_type, risk_level, active)
                    VALUES (:id, :site_id, :name, :slug, :description, :zone_type, :risk_level, :active)
                """), {
                    "id": zone_id,
                    "site_id": str(data.site_id) if data.site_id else None,
                    "name": data.name,
                    "slug": slug,
                    "description": data.description,
                    "zone_type": data.zone_type,
                    "risk_level": data.risk_level,
                    "active": data.is_active
                })
                row = await session.execute(text("""
                    SELECT z.id, z.site_id, z.name, z.slug, z.description, z.zone_type, z.risk_level, z.active AS is_active, z.created_at, z.updated_at, s.organization_id
                    FROM zones z
                    LEFT JOIN sites s ON z.site_id = s.id
                    WHERE z.id = :id
                """), {"id": zone_id})
                return dict(row.fetchone()._mapping)

    async def list_zones(self, site_id: str | None = None) -> list[dict]:
        async with self._session_factory() as session:
            if site_id:
                rows = await session.execute(text("""
                    SELECT z.id, z.site_id, z.name, z.slug, z.description, z.zone_type, z.risk_level, z.active AS is_active, z.created_at, z.updated_at, s.organization_id
                    FROM zones z
                    LEFT JOIN sites s ON z.site_id = s.id
                    WHERE z.site_id = :site_id
                    ORDER BY z.created_at DESC
                """), {"site_id": site_id})
            else:
                rows = await session.execute(text("""
                    SELECT z.id, z.site_id, z.name, z.slug, z.description, z.zone_type, z.risk_level, z.active AS is_active, z.created_at, z.updated_at, s.organization_id
                    FROM zones z
                    LEFT JOIN sites s ON z.site_id = s.id
                    ORDER BY z.created_at DESC
                """))
            return [dict(r._mapping) for r in rows.fetchall()]

    async def get_zone(self, zone_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.execute(text("""
                SELECT z.id, z.site_id, z.name, z.slug, z.description, z.zone_type, z.risk_level, z.active AS is_active, z.created_at, z.updated_at, s.organization_id
                FROM zones z
                LEFT JOIN sites s ON z.site_id = s.id
                WHERE z.id = :id
            """), {"id": zone_id})
            res = row.fetchone()
            return dict(res._mapping) if res else None

    async def update_zone(self, zone_id: str, data: ZoneUpdate) -> dict | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.execute(text("SELECT id FROM zones WHERE id = :id"), {"id": zone_id})
                if not row.fetchone():
                    return None
                updates = []
                params = {"id": zone_id}
                if data.name is not None:
                    updates.append("name = :name")
                    params["name"] = data.name
                if data.description is not None:
                    updates.append("description = :description")
                    params["description"] = data.description
                if data.zone_type is not None:
                    updates.append("zone_type = :zone_type")
                    params["zone_type"] = data.zone_type
                if data.risk_level is not None:
                    updates.append("risk_level = :risk_level")
                    params["risk_level"] = data.risk_level
                if data.is_active is not None:
                    updates.append("active = :active")
                    params["active"] = data.is_active
                if updates:
                    updates.append("updated_at = now()")
                    await session.execute(text(f"UPDATE zones SET {', '.join(updates)} WHERE id = :id"), params)
                r = await session.execute(text("""
                    SELECT z.id, z.site_id, z.name, z.slug, z.description, z.zone_type, z.risk_level, z.active AS is_active, z.created_at, z.updated_at, s.organization_id
                    FROM zones z
                    LEFT JOIN sites s ON z.site_id = s.id
                    WHERE z.id = :id
                """), {"id": zone_id})
                return dict(r.fetchone()._mapping)

    async def delete_zone(self, zone_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                # 1. Dependency check: any cameras referencing this zone (active or decommissioned)
                c_count = await session.execute(
                    text("SELECT count(*) FROM cameras WHERE zone_id = :id"),
                    {"id": zone_id}
                )
                if c_count.scalar() > 0:
                    raise ValueError("Cannot delete zone: active cameras are assigned to this zone (or decommissioned cameras still reference it). Reassign cameras to another zone or unassign them first.")

                # 2. Dependency check: historical compliance and safety event records
                try:
                    # 2a. Historical compliance events
                    ce_count = await session.execute(
                        text("SELECT count(*) FROM compliance_events WHERE zone_id = :id"),
                        {"id": zone_id}
                    )
                    if ce_count.scalar() > 0:
                        raise ValueError("Cannot delete zone: historical compliance event records reference this zone. Deactivate the zone instead to preserve compliance history.")

                    # 2b. Historical daily person compliance records
                    pdc_count = await session.execute(
                        text("SELECT count(*) FROM person_daily_compliance WHERE zone_id = :id"),
                        {"id": zone_id}
                    )
                    if pdc_count.scalar() > 0:
                        raise ValueError("Cannot delete zone: daily person compliance records reference this zone. Deactivate the zone instead to preserve compliance history.")

                    # 2c. Historical incidents
                    inc_count = await session.execute(
                        text("SELECT count(*) FROM incidents WHERE zone_id = :id"),
                        {"id": zone_id}
                    )
                    if inc_count.scalar() > 0:
                        raise ValueError("Cannot delete zone: historical incident records reference this zone. Deactivate the zone instead to preserve compliance history.")

                    # 2d. UC3 safety events (with documented schema-compatibility policy)
                    reg_check = await session.execute(text("SELECT to_regclass('public.uc3_events')"))
                    if reg_check.scalar() is not None:
                        uc3_count = await session.execute(
                            text("SELECT count(*) FROM uc3_events WHERE zone_id = :id"),
                            {"id": zone_id}
                        )
                        if uc3_count.scalar() > 0:
                            raise ValueError("Cannot delete zone: historical safety event records (uc3_events) reference this zone. Deactivate the zone instead to preserve compliance history.")
                    else:
                        # Documented schema-compatibility policy:
                        # In full deployments, uc3_events is required. Only decoupled environments
                        # with INNOVISION_ALLOW_OPTIONAL_UC3_TABLES=1 may bypass a missing uc3_events table.
                        allow_optional = os.getenv("INNOVISION_ALLOW_OPTIONAL_UC3_TABLES", "0").lower() in ("1", "true", "yes")
                        if not allow_optional:
                            raise RuntimeError(
                                "Required safety table 'uc3_events' is missing from the database. "
                                "Zone deletion aborted to prevent undetected data loss. "
                                "Set INNOVISION_ALLOW_OPTIONAL_UC3_TABLES=1 only in verified decoupled environments."
                            )
                        logger.warning(
                            "Optional table 'uc3_events' is not present in database; skipping check per documented compatibility policy."
                        )
                except ValueError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to verify historical dependencies for zone {zone_id}: {e}")
                    raise RuntimeError(f"Database error during safety dependency check: {e}. Zone deletion aborted.")

                # Safe cleanup of related policies and rules
                await session.execute(text("DELETE FROM zone_analytics_policies WHERE zone_id = :id"), {"id": zone_id})
                await session.execute(text("DELETE FROM zones WHERE id = :id"), {"id": zone_id})

    # --- Cameras ---
    async def create_camera(self, data: CameraCreate) -> dict:
        camera_id = str(uuid.uuid4())

        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    INSERT INTO cameras
                        (id, name, location, rtsp_url, status, use_cases, fps, organization_id, site_id, zone_id, lifecycle_state, source_type, source_url, is_simulation)
                    VALUES
                        (:id, :name, :location, :rtsp_url, 'offline', :use_cases, :fps, :org_id, :site_id, :zone_id, :lifecycle_state, :source_type, :source_url, :is_simulation)
                """), {
                    "id": camera_id,
                    "name": data.name,
                    "location": data.location,
                    "rtsp_url": data.rtsp_url,
                    "use_cases": data.use_cases,
                    "fps": data.fps,
                    "org_id": str(data.organization_id) if data.organization_id else None,
                    "site_id": str(data.site_id) if data.site_id else None,
                    "zone_id": str(data.zone_id) if data.zone_id else None,
                    "lifecycle_state": data.lifecycle_state or "unassigned",
                    "source_type": data.source_type or "rtsp",
                    "source_url": data.source_url,
                    "is_simulation": data.is_simulation or False,
                })
        await self._redis.publish(f"camera:added:{camera_id}", camera_id)
        await self.recalculate_effective_analytics([camera_id])
        logger.info("camera_created id=%s name=%s use_cases=%s", camera_id, data.name, data.use_cases)
        return {"id": camera_id, **data.model_dump()}

    async def assign_camera_zone(self, camera_id: str, site_id: str | None = None, zone_id: str | None = None, lifecycle_state: str | None = None) -> dict | None:
        target_site_id = site_id
        target_org_id = None

        async with self._session_factory() as session:
            async with session.begin():
                if zone_id:
                    z_row = await session.execute(text("SELECT site_id FROM zones WHERE id = :id"), {"id": zone_id})
                    z = z_row.fetchone()
                    if z and z.site_id:
                        target_site_id = str(z.site_id)

                if target_site_id:
                    s_row = await session.execute(text("SELECT organization_id FROM sites WHERE id = :id"), {"id": target_site_id})
                    s = s_row.fetchone()
                    if s and s.organization_id:
                        target_org_id = str(s.organization_id)

                new_lifecycle = lifecycle_state
                if new_lifecycle is None:
                    if zone_id:
                        new_lifecycle = 'active'
                    else:
                        new_lifecycle = 'unassigned'

                await session.execute(text("""
                    UPDATE cameras
                    SET organization_id = COALESCE(:org_id, organization_id),
                        site_id = :site_id,
                        zone_id = :zone_id,
                        lifecycle_state = :lifecycle_state,
                        updated_at = now()
                    WHERE id = :id
                """), {
                    "org_id": target_org_id,
                    "site_id": target_site_id,
                    "zone_id": zone_id,
                    "lifecycle_state": new_lifecycle,
                    "id": camera_id
                })

        await self.recalculate_effective_analytics([camera_id])
        return await self.get_camera_hierarchy(camera_id)

    async def get_camera_hierarchy(self, camera_id: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.execute(text("""
                SELECT c.id, c.name, c.location, c.rtsp_url, c.status, c.fps, c.use_cases,
                       c.organization_id, c.site_id, c.zone_id, c.lifecycle_state, c.source_type, c.source_url, c.is_simulation, c.created_at,
                       o.id AS org_id, o.name AS org_name, o.code AS org_code,
                       s.id AS s_id, s.name AS s_name, s.code AS s_code,
                       z.id AS z_id, z.name AS z_name, z.zone_type AS z_type, z.risk_level AS z_risk
                FROM cameras c
                LEFT JOIN organizations o ON c.organization_id = o.id
                LEFT JOIN sites s ON c.site_id = s.id
                LEFT JOIN zones z ON c.zone_id = z.id
                WHERE c.id = :id
            """), {"id": camera_id})
            res = row.fetchone()
            if not res:
                return None
            m = dict(res._mapping)
            camera_dict = {
                "id": str(m["id"]),
                "name": m["name"],
                "location": m["location"],
                "rtsp_url": m["rtsp_url"],
                "status": m["status"],
                "fps": m["fps"],
                "use_cases": m["use_cases"],
                "organization_id": str(m["organization_id"]) if m["organization_id"] else None,
                "site_id": str(m["site_id"]) if m["site_id"] else None,
                "zone_id": str(m["zone_id"]) if m["zone_id"] else None,
                "lifecycle_state": m["lifecycle_state"],
                "source_type": m["source_type"],
                "source_url": m["source_url"],
                "is_simulation": m["is_simulation"],
                "created_at": m["created_at"],
                "organization": {
                    "id": str(m["org_id"]),
                    "name": m["org_name"],
                    "code": m["org_code"]
                } if m["org_id"] else None,
                "site": {
                    "id": str(m["s_id"]),
                    "name": m["s_name"],
                    "code": m["s_code"]
                } if m["s_id"] else None,
                "zone": {
                    "id": str(m["z_id"]),
                    "name": m["z_name"],
                    "zone_type": m["z_type"],
                    "risk_level": m["z_risk"]
                } if m["z_id"] else None
            }
            return camera_dict

    async def update_config(self, camera_id: str, data: CameraConfigUpdate) -> None:
        updates = {k: str(v) if isinstance(v, uuid.UUID) else v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return

        set_clause = ", ".join(f"{k} = :{k}" for k in updates)
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(
                    text(f"UPDATE cameras SET {set_clause}, updated_at = now() "
                         f"WHERE id = :camera_id"), {**updates, "camera_id": camera_id},
                )
        await self.recalculate_effective_analytics([camera_id])
        await self._redis.publish(f"camera:updated:{camera_id}", camera_id)
        logger.info("camera_updated id=%s field=%s", camera_id, list(updates.keys()))

    async def decommission_camera(self, camera_id: str) -> dict | None:
        async with self._session_factory() as session:
            async with session.begin():
                row = await session.execute(
                    text("SELECT id, name, organization_id, site_id, zone_id, lifecycle_state, status FROM cameras WHERE id = :id"),
                    {"id": camera_id}
                )
                cam = row.fetchone()
                if not cam:
                    return None
                await session.execute(
                    text("UPDATE cameras SET status = 'disabled', lifecycle_state = 'disabled', updated_at = now() WHERE id = :id"),
                    {"id": camera_id},
                )
        await self.recalculate_effective_analytics([camera_id])
        await self._redis.publish(f"camera:removed:{camera_id}", camera_id)
        logger.info("camera_decommissioned id=%s", camera_id)
        return await self.get_camera(camera_id, include_disabled=True)

    async def delete_camera(self, camera_id: str) -> dict | None:
        return await self.decommission_camera(camera_id)

    async def get_cameras_for_uc(self, uc_id: str) -> list[str]:
        async with self._session_factory() as session:
            rows = await session.execute(
                text("""
                    SELECT DISTINCT e.camera_id
                    FROM camera_effective_analytics e
                    JOIN analytics_catalog a ON e.analytic_id = a.id
                    JOIN cameras c ON e.camera_id = c.id
                    WHERE (a.code = :uc_id OR a.internal_code = :uc_id OR :uc_id = ANY(c.use_cases))
                      AND e.is_active = true
                      AND c.status != 'disabled'
                """),
                {"uc_id": uc_id}
            )
            return [str(r.camera_id) for r in rows.fetchall()]

    async def get_active_cameras(self) -> list[dict]:
        # used by ingestion service on startup to know what to connect to
        async with self._session_factory() as session:
            rows = await session.execute(
                text("""
                    SELECT id, name, location, rtsp_url, status, fps, use_cases,
                           organization_id, site_id, zone_id, lifecycle_state, source_type, source_url, is_simulation
                    FROM cameras
                    WHERE status != 'disabled'
                """))
            return [dict(r._mapping) for r in rows.fetchall()]

    async def update_status(self, camera_id: str, status: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                await session.execute(text("""
                    UPDATE cameras SET status = :status, updated_at = now() WHERE id = :id
                """), {"status": status, "id": camera_id})
        await self.recalculate_effective_analytics([camera_id])

    async def get_camera(self, camera_id: str, include_disabled: bool = False) -> dict | None:
        async with self._session_factory() as session:
            sql = """
                SELECT id, name, location, rtsp_url, status, fps, use_cases,
                       organization_id, site_id, zone_id, lifecycle_state, source_type, source_url, is_simulation
                FROM cameras
                WHERE id = :id
            """
            if not include_disabled:
                sql += " AND status != 'disabled'"
            row = await session.execute(text(sql), {"id": camera_id})
            camera = row.fetchone()
            if not camera:
                return None
            return dict(camera._mapping)

    # --- Analytics Catalog (Phase 2) ---
    async def list_analytics_catalog(self) -> list[dict]:
        async with self._session_factory() as session:
            rows = await session.execute(text("""
                SELECT id, code, internal_code, display_name, description, category, icon_key, is_active, created_at
                FROM analytics_catalog
                WHERE is_active = true
                ORDER BY internal_code ASC
            """))
            return [dict(r._mapping) for r in rows.fetchall()]

    async def get_analytic(self, analytic_id_or_code: str) -> dict | None:
        async with self._session_factory() as session:
            row = await session.execute(text("""
                SELECT id, code, internal_code, display_name, description, category, icon_key, is_active, created_at
                FROM analytics_catalog
                WHERE id::text = :val OR code = :val OR internal_code = :val
            """), {"val": analytic_id_or_code})
            res = row.fetchone()
            return dict(res._mapping) if res else None

    # --- Organization Subscriptions (Phase 2) ---
    async def create_organization_subscription(self, organization_id: str, data: OrganizationSubscriptionCreate) -> dict:
        sub_id = str(uuid.uuid4())
        async with self._session_factory() as session:
            async with session.begin():
                # Check organization exists
                org_check = await session.execute(text("SELECT id FROM organizations WHERE id = :id"), {"id": organization_id})
                if not org_check.fetchone():
                    raise ValueError(f"Organization {organization_id} not found")

                # Check analytic exists
                analytic_check = await session.execute(text("SELECT id FROM analytics_catalog WHERE id = :id"), {"id": str(data.analytic_id)})
                if not analytic_check.fetchone():
                    raise ValueError(f"Analytic {data.analytic_id} not found in catalog")

                # Check duplicate
                dup_check = await session.execute(text("""
                    SELECT id FROM organization_subscriptions WHERE organization_id = :org_id AND analytic_id = :analytic_id
                """), {"org_id": organization_id, "analytic_id": str(data.analytic_id)})
                if dup_check.fetchone():
                    raise KeyError(f"Subscription for analytic {data.analytic_id} already exists for organization {organization_id}")

                await session.execute(text("""
                    INSERT INTO organization_subscriptions (id, organization_id, analytic_id, is_enabled, max_cameras_allowed, valid_until)
                    VALUES (:id, :org_id, :analytic_id, :is_enabled, :max_cameras, :valid_until)
                """), {
                    "id": sub_id,
                    "org_id": organization_id,
                    "analytic_id": str(data.analytic_id),
                    "is_enabled": data.is_enabled,
                    "max_cameras": data.max_cameras_allowed,
                    "valid_until": data.valid_until
                })

        res = await self.get_organization_subscription(organization_id, str(data.analytic_id))
        if not res:
            raise RuntimeError("Failed to fetch newly created subscription")
        return res

    async def list_organization_subscriptions(self, organization_id: str) -> list[dict]:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            org_check = await session.execute(text("SELECT id FROM organizations WHERE id = :id"), {"id": organization_id})
            if not org_check.fetchone():
                raise ValueError(f"Organization {organization_id} not found")

            rows = await session.execute(text("""
                SELECT s.id, s.organization_id, s.analytic_id, s.is_enabled, s.max_cameras_allowed, s.valid_until, s.created_at,
                       a.code AS analytic_code, a.internal_code AS analytic_internal_code, a.display_name AS analytic_display_name
                FROM organization_subscriptions s
                JOIN analytics_catalog a ON s.analytic_id = a.id
                WHERE s.organization_id = :org_id
                ORDER BY a.internal_code ASC
            """), {"org_id": organization_id})

            results = []
            for r in rows.fetchall():
                m = dict(r._mapping)
                m["id"] = str(m["id"])
                m["organization_id"] = str(m["organization_id"])
                m["analytic_id"] = str(m["analytic_id"])
                is_enabled = m["is_enabled"]
                valid_until = m["valid_until"]
                if not is_enabled:
                    status = "disabled"
                elif valid_until and valid_until.astimezone(timezone.utc) < now:
                    status = "expired"
                else:
                    status = "enabled"

                m["status"] = status
                results.append(m)

            return results

    async def get_organization_subscription(self, organization_id: str, analytic_id: str) -> dict | None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        async with self._session_factory() as session:
            row = await session.execute(text("""
                SELECT s.id, s.organization_id, s.analytic_id, s.is_enabled, s.max_cameras_allowed, s.valid_until, s.created_at,
                       a.code AS analytic_code, a.internal_code AS analytic_internal_code, a.display_name AS analytic_display_name
                FROM organization_subscriptions s
                JOIN analytics_catalog a ON s.analytic_id = a.id
                WHERE s.organization_id = :org_id AND (s.analytic_id::text = :analytic_id OR a.code = :analytic_id OR a.internal_code = :analytic_id)
            """), {"org_id": organization_id, "analytic_id": analytic_id})

            res = row.fetchone()
            if not res:
                return None
            m = dict(res._mapping)
            m["id"] = str(m["id"])
            m["organization_id"] = str(m["organization_id"])
            m["analytic_id"] = str(m["analytic_id"])
            is_enabled = m["is_enabled"]
            valid_until = m["valid_until"]
            if not is_enabled:
                status = "disabled"
            elif valid_until and valid_until.astimezone(timezone.utc) < now:
                status = "expired"
            else:
                status = "enabled"
            m["status"] = status
            return m

    async def update_organization_subscription(self, organization_id: str, analytic_id: str, data: OrganizationSubscriptionUpdate) -> dict | None:
        updates = {k: v for k, v in data.model_dump().items() if v is not None}
        if not updates:
            return await self.get_organization_subscription(organization_id, analytic_id)

        set_clauses = []
        params = {"org_id": organization_id, "analytic_id": analytic_id}
        if "is_enabled" in updates:
            set_clauses.append("is_enabled = :is_enabled")
            params["is_enabled"] = updates["is_enabled"]
        if "max_cameras_allowed" in updates:
            set_clauses.append("max_cameras_allowed = :max_cameras_allowed")
            params["max_cameras_allowed"] = updates["max_cameras_allowed"]
        if "valid_until" in updates:
            set_clauses.append("valid_until = :valid_until")
            params["valid_until"] = updates["valid_until"]

        set_str = ", ".join(set_clauses)
        async with self._session_factory() as session:
            async with session.begin():
                sub_row = await session.execute(text("""
                    SELECT s.id FROM organization_subscriptions s
                    JOIN analytics_catalog a ON s.analytic_id = a.id
                    WHERE s.organization_id = :org_id AND (s.analytic_id::text = :analytic_id OR a.code = :analytic_id OR a.internal_code = :analytic_id)
                """), {"org_id": organization_id, "analytic_id": analytic_id})
                res = sub_row.fetchone()
                if not res:
                    raise ValueError(f"Subscription for analytic {analytic_id} not found")

                await session.execute(text(f"""
                    UPDATE organization_subscriptions
                    SET {set_str}
                    WHERE id = '{res.id}'
                """), params)

        await self._recalculate_org_cameras(organization_id)
        return await self.get_organization_subscription(organization_id, analytic_id)

    async def delete_organization_subscription(self, organization_id: str, analytic_id: str) -> None:
        async with self._session_factory() as session:
            async with session.begin():
                sub_row = await session.execute(text("""
                    SELECT s.id FROM organization_subscriptions s
                    JOIN analytics_catalog a ON s.analytic_id = a.id
                    WHERE s.organization_id = :org_id AND (s.analytic_id::text = :analytic_id OR a.code = :analytic_id OR a.internal_code = :analytic_id)
                """), {"org_id": organization_id, "analytic_id": analytic_id})
                res = sub_row.fetchone()
                if not res:
                    raise ValueError(f"Subscription for analytic {analytic_id} not found")

                await session.execute(text("""
                    DELETE FROM organization_subscriptions
                    WHERE id = :id
                """), {"id": str(res.id)})

        await self._recalculate_org_cameras(organization_id)

    async def _recalculate_org_cameras(self, org_id: str) -> None:
        async with self._session_factory() as session:
            c_rows = await session.execute(text("""
                SELECT DISTINCT c.id FROM cameras c
                LEFT JOIN sites s ON c.site_id = s.id
                WHERE c.organization_id = :org_id OR s.organization_id = :org_id
            """), {"org_id": org_id})
            cam_ids = [str(r.id) for r in c_rows.fetchall()]
        if cam_ids:
            await self.recalculate_effective_analytics(cam_ids)

    # --- Zone Analytics Policies (Phase 3) ---
    async def list_zone_analytics_policies(self, zone_id: str) -> list[dict]:
        async with self._session_factory() as session:
            z_row = await session.execute(text("SELECT id FROM zones WHERE id = :id"), {"id": zone_id})
            if not z_row.fetchone():
                raise ValueError(f"Zone {zone_id} not found")

            rows = await session.execute(text("""
                SELECT a.id AS analytic_id, a.internal_code, a.code, a.display_name, a.category,
                       COALESCE(p.is_enabled, false) AS is_enabled
                FROM analytics_catalog a
                LEFT JOIN zone_analytics_policies p ON a.id = p.analytic_id AND p.zone_id = :zone_id
                WHERE a.is_active = true
                ORDER BY a.internal_code ASC
            """), {"zone_id": zone_id})

            results = []
            for r in rows.fetchall():
                m = dict(r._mapping)
                m["analytic_id"] = str(m["analytic_id"])
                results.append(m)
            return results

    async def update_zone_analytics_policy(
        self,
        zone_id: str,
        analytic_id: str,
        is_enabled: bool,
        current_user: dict | None = None,
        user_org_id: str | None = None
    ) -> dict:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        eff_user_org_id = user_org_id or (current_user.get("org_id") if isinstance(current_user, dict) else None)

        async with self._session_factory() as session:
            async with session.begin():
                z_row = await session.execute(text("""
                    SELECT z.id, s.organization_id
                    FROM zones z
                    LEFT JOIN sites s ON z.site_id = s.id
                    WHERE z.id = :id
                """), {"id": zone_id})
                z = z_row.fetchone()
                if not z:
                    raise ValueError(f"Zone {zone_id} not found")

                zone_org_id = str(z.organization_id) if z.organization_id else None

                if eff_user_org_id and zone_org_id and str(eff_user_org_id) != zone_org_id:
                    raise PermissionError(f"User organization {eff_user_org_id} does not match zone organization {zone_org_id}")

                a_row = await session.execute(text("""
                    SELECT id FROM analytics_catalog
                    WHERE id::text = :id OR code = :id OR internal_code = :id
                """), {"id": analytic_id})
                a = a_row.fetchone()
                if not a:
                    raise ValueError(f"Analytic {analytic_id} not found in catalog")

                actual_analytic_id = str(a.id)

                if is_enabled:
                    if not zone_org_id:
                        raise KeyError("Zone must belong to an organization with an active subscription to enable analytics")

                    sub_row = await session.execute(text("""
                        SELECT is_enabled, valid_until, max_cameras_allowed
                        FROM organization_subscriptions
                        WHERE organization_id = :org_id AND analytic_id = :analytic_id
                    """), {"org_id": zone_org_id, "analytic_id": actual_analytic_id})
                    sub = sub_row.fetchone()

                    if not sub:
                        raise KeyError(f"Organization has no subscription for analytic {actual_analytic_id}")
                    if not sub.is_enabled:
                        raise KeyError(f"Organization subscription for analytic {actual_analytic_id} is disabled")
                    if sub.valid_until and sub.valid_until.astimezone(timezone.utc) < now:
                        raise KeyError(f"Organization subscription for analytic {actual_analytic_id} has expired")

                    # Check camera subscription limit
                    if sub.max_cameras_allowed is not None:
                        cnt_row = await session.execute(text("""
                            SELECT COUNT(DISTINCT e.camera_id) AS cnt
                            FROM camera_effective_analytics e
                            JOIN cameras c ON e.camera_id = c.id
                            LEFT JOIN sites s ON c.site_id = s.id
                            WHERE (c.organization_id = :org_id OR s.organization_id = :org_id)
                              AND e.analytic_id = :analytic_id
                              AND e.is_active = true
                        """), {"org_id": zone_org_id, "analytic_id": actual_analytic_id})
                        current_usage = cnt_row.fetchone().cnt

                        new_cams_row = await session.execute(text("""
                            SELECT COUNT(c.id) AS cnt
                            FROM cameras c
                            LEFT JOIN camera_effective_analytics e ON c.id = e.camera_id AND e.analytic_id = :analytic_id
                            WHERE c.zone_id = :zone_id AND c.status != 'disabled' AND (e.is_active IS NULL OR e.is_active = false)
                        """), {"zone_id": zone_id, "analytic_id": actual_analytic_id})
                        new_cams = new_cams_row.fetchone().cnt

                        if current_usage + new_cams > sub.max_cameras_allowed:
                            raise KeyError(f"ANALYTIC_CAMERA_LIMIT_EXCEEDED: Enabling analytic on zone would exceed camera limit ({sub.max_cameras_allowed}) for org {zone_org_id}")

                policy_id = str(uuid.uuid4())
                await session.execute(text("""
                    INSERT INTO zone_analytics_policies (id, zone_id, analytic_id, is_enabled, updated_at)
                    VALUES (:id, :zone_id, :analytic_id, :is_enabled, now())
                    ON CONFLICT (zone_id, analytic_id)
                    DO UPDATE SET is_enabled = EXCLUDED.is_enabled, updated_at = now()
                """), {
                    "id": policy_id,
                    "zone_id": zone_id,
                    "analytic_id": actual_analytic_id,
                    "is_enabled": is_enabled
                })

        async with self._session_factory() as session:
            c_rows = await session.execute(text("SELECT id FROM cameras WHERE zone_id = :zone_id"), {"zone_id": zone_id})
            cam_ids = [str(r.id) for r in c_rows.fetchall()]
        if cam_ids:
            await self.recalculate_effective_analytics(cam_ids)

        policies = await self.list_zone_analytics_policies(zone_id)
        single = next((p for p in policies if str(p["analytic_id"]) == actual_analytic_id), None)
        return single or {}

    async def bulk_update_zone_analytics_policies(
        self,
        zone_id: str,
        policies: list[dict],
        current_user: dict | None = None,
        user_org_id: str | None = None
    ) -> list[dict]:
        eff_user_org_id = user_org_id or (current_user.get("org_id") if isinstance(current_user, dict) else None)
        for item in policies:
            analytic_id = str(item.get("analytic_id"))
            is_enabled = bool(item.get("is_enabled"))
            await self.update_zone_analytics_policy(
                zone_id, analytic_id, is_enabled, current_user=current_user, user_org_id=eff_user_org_id
            )
        return await self.list_zone_analytics_policies(zone_id)

    # --- UC3 Zone PPE Rules (Phase 3) ---
    async def get_zone_ppe_rules(self, zone_id: str, min_confidence: float = 0.50) -> dict:
        STANDARD_PPE_TYPES = [
            "helmet", "safety-vest", "gloves", "shoes",
            "glasses", "mask", "face-guard", "medical-suit"
        ]
        async with self._session_factory() as session:
            z_row = await session.execute(text("SELECT id FROM zones WHERE id = :id"), {"id": zone_id})
            if not z_row.fetchone():
                raise ValueError(f"Zone {zone_id} not found")

            # Resolve stored min_confidence from uc3_zones or zones
            eff_min_conf = min_confidence
            async def _fetch_conf():
                nonlocal eff_min_conf
                uz_conf = await session.execute(
                    text("SELECT min_confidence FROM uc3_zones WHERE id = :id"),
                    {"id": zone_id}
                )
                uz_r = uz_conf.fetchone()
                if uz_r and uz_r[0] is not None:
                    eff_min_conf = float(uz_r[0])
                else:
                    z_conf = await session.execute(
                        text("SELECT min_confidence FROM zones WHERE id = :id"),
                        {"id": zone_id}
                    )
                    zr = z_conf.fetchone()
                    if zr and zr[0] is not None:
                        eff_min_conf = float(zr[0])

            try:
                if hasattr(session, "begin_nested"):
                    async with session.begin_nested():
                        await _fetch_conf()
                else:
                    await _fetch_conf()
            except Exception:
                pass

            rules_rows = await session.execute(text("""
                SELECT id, zone_id, ppe_type, required, severity, grace_seconds
                FROM uc3_zone_ppe_rules
                WHERE zone_id = :id
            """), {"id": zone_id})
            rows = rules_rows.fetchall()

            if rows:
                rule_items = [
                    {
                        "ppe_type": r.ppe_type,
                        "required": bool(r.required),
                        "severity": r.severity or "high",
                        "grace_seconds": r.grace_seconds or 0
                    }
                    for r in rows
                ]
                return {
                    "zone_id": zone_id,
                    "ppe_rules": rule_items,
                    "min_confidence": eff_min_conf
                }

            z_ppe = await session.execute(text("SELECT required_ppe FROM zones WHERE id = :id"), {"id": zone_id})
            z_res = z_ppe.fetchone()
            req_set = set(z_res.required_ppe) if z_res and z_res.required_ppe else set()

            rule_items = [
                {
                    "ppe_type": ppe,
                    "required": (ppe in req_set),
                    "severity": "high",
                    "grace_seconds": 0
                }
                for ppe in STANDARD_PPE_TYPES
            ]

            return {
                "zone_id": zone_id,
                "ppe_rules": rule_items,
                "min_confidence": eff_min_conf
            }

    async def update_zone_ppe_rules(
        self,
        zone_id: str,
        rules: list,
        min_confidence: float = 0.50,
        current_user: dict | None = None,
        user_org_id: str | None = None
    ) -> dict:
        if min_confidence < 0.0 or min_confidence > 1.0:
            raise ValueError(f"min_confidence must be between 0.0 and 1.0, got {min_confidence}")

        eff_user_org_id = user_org_id or (current_user.get("org_id") if isinstance(current_user, dict) else None)
        cam_ids: list[str] = []

        async with self._session_factory() as session:
            async with session.begin():
                z_row = await session.execute(text("""
                    SELECT z.id, s.organization_id
                    FROM zones z
                    LEFT JOIN sites s ON z.site_id = s.id
                    WHERE z.id = :id
                """), {"id": zone_id})
                z = z_row.fetchone()
                if not z:
                    raise ValueError(f"Zone {zone_id} not found")

                zone_org_id = str(z.organization_id) if z.organization_id else None
                if eff_user_org_id and zone_org_id and str(eff_user_org_id) != zone_org_id:
                    raise PermissionError(f"User organization {eff_user_org_id} does not match zone organization {zone_org_id}")

                uc3_z = await session.execute(text("SELECT id FROM uc3_zones WHERE id = :id"), {"id": zone_id})
                if not uc3_z.fetchone():
                    z_info = await session.execute(text("SELECT name, description, risk_level FROM zones WHERE id = :id"), {"id": zone_id})
                    zi = z_info.fetchone()
                    try:
                        async with session.begin_nested():
                            await session.execute(text("""
                                INSERT INTO uc3_zones (id, organization_id, name, description, risk_level, is_active, min_confidence)
                                VALUES (:id, :org_id, :name, :description, :risk_level, true, :min_conf)
                                ON CONFLICT (id) DO UPDATE SET min_confidence = EXCLUDED.min_confidence;
                            """), {
                                "id": zone_id,
                                "org_id": zone_org_id,
                                "name": zi.name if zi else "Zone",
                                "description": zi.description if zi else None,
                                "risk_level": zi.risk_level if zi else "medium",
                                "min_conf": min_confidence
                            })
                    except Exception:
                        await session.execute(text("""
                            INSERT INTO uc3_zones (id, organization_id, name, description, risk_level, is_active)
                            VALUES (:id, :org_id, :name, :description, :risk_level, true)
                            ON CONFLICT (id) DO NOTHING;
                        """), {
                            "id": zone_id,
                            "org_id": zone_org_id,
                            "name": zi.name if zi else "Zone",
                            "description": zi.description if zi else None,
                            "risk_level": zi.risk_level if zi else "medium"
                        })
                else:
                    try:
                        async with session.begin_nested():
                            await session.execute(text("""
                                UPDATE uc3_zones SET min_confidence = :min_conf WHERE id = :id
                            """), {"id": zone_id, "min_conf": min_confidence})
                    except Exception:
                        pass

                await session.execute(text("DELETE FROM uc3_zone_ppe_rules WHERE zone_id = :id"), {"id": zone_id})

                required_ppe_list = []
                for rule in rules:
                    ppe_type = getattr(rule, "ppe_type", None) or (rule.get("ppe_type") if isinstance(rule, dict) else None)
                    required = getattr(rule, "required", None)
                    if required is None and isinstance(rule, dict):
                        required = rule.get("required", True)
                    severity = getattr(rule, "severity", None) or (rule.get("severity") if isinstance(rule, dict) else "high")
                    grace_seconds = getattr(rule, "grace_seconds", None)
                    if grace_seconds is None and isinstance(rule, dict):
                        grace_seconds = rule.get("grace_seconds", 0)

                    if required:
                        required_ppe_list.append(ppe_type)

                    rule_id = str(uuid.uuid4())
                    await session.execute(text("""
                        INSERT INTO uc3_zone_ppe_rules (id, zone_id, ppe_type, required, severity, grace_seconds)
                        VALUES (:id, :zone_id, :ppe_type, :required, :severity, :grace_seconds)
                    """), {
                        "id": rule_id,
                        "zone_id": zone_id,
                        "ppe_type": ppe_type,
                        "required": bool(required),
                        "severity": severity,
                        "grace_seconds": grace_seconds or 0
                    })

                PPE_ENUM_MAP = {
                    "helmet": "helmet",
                    "safety-vest": "vest",
                    "vest": "vest",
                    "gloves": "gloves",
                    "shoes": "safety_shoes",
                    "safety-shoes": "safety_shoes",
                    "safety_shoes": "safety_shoes",
                    "mask": "mask",
                    "glasses": "eye_prot",
                    "goggles": "eye_prot",
                    "eye_prot": "eye_prot",
                    "face-guard": "mask",
                    "medical-suit": "vest",
                }

                pg_enum_ppe_list = list({
                    PPE_ENUM_MAP[item]
                    for item in required_ppe_list
                    if item in PPE_ENUM_MAP
                })

                # Sync to zones table required_ppe and min_confidence columns
                try:
                    async with session.begin_nested():
                        await session.execute(text("""
                            UPDATE zones SET min_confidence = :min_conf, required_ppe = :req_ppe, updated_at = now() WHERE id = :id
                        """), {"id": zone_id, "min_conf": min_confidence, "req_ppe": pg_enum_ppe_list})
                except Exception:
                    await session.execute(text("""
                        UPDATE zones SET required_ppe = :req_ppe, updated_at = now() WHERE id = :id
                    """), {"id": zone_id, "req_ppe": pg_enum_ppe_list})

                # Find all cameras assigned to this zone for effective analytics refresh
                cams = await session.execute(text("SELECT id FROM cameras WHERE zone_id = :z_id"), {"z_id": zone_id})
                cam_ids = [str(r.id) for r in cams.fetchall()]

        if cam_ids:
            try:
                await self.recalculate_effective_analytics(cam_ids)
            except Exception as e:
                logger.warning("recalculate_effective_analytics_warning zone_id=%s error=%s", zone_id, e)

        return await self.get_zone_ppe_rules(zone_id, min_confidence=min_confidence)

    # --- Camera Analytics Overrides & Effective Analytics (Phase 4) ---
    async def recalculate_effective_analytics(self, camera_ids: list[str] | str) -> None:
        if isinstance(camera_ids, str):
            camera_ids = [camera_ids]
        if not camera_ids:
            return

        async with self._session_factory() as session:
            async with session.begin():
                cat_rows = await session.execute(text("SELECT id, code, internal_code FROM analytics_catalog WHERE is_active = true"))
                catalog_items = cat_rows.fetchall()

                for cam_id in camera_ids:
                    c_row = await session.execute(text("""
                        SELECT c.id, c.organization_id AS camera_org_id, c.site_id AS camera_site_id, c.zone_id,
                               s.organization_id AS site_org_id,
                               z.site_id AS zone_site_id
                        FROM cameras c
                        LEFT JOIN sites s ON c.site_id = s.id
                        LEFT JOIN zones z ON c.zone_id = z.id
                        WHERE c.id = :id AND c.status != 'disabled'
                    """), {"id": cam_id})
                    c = c_row.fetchone()
                    if not c:
                        await session.execute(text("""
                            UPDATE camera_effective_analytics SET is_active = false, updated_at = now() WHERE camera_id = :id
                        """), {"id": cam_id})
                        continue

                    org_id = str(c.camera_org_id) if c.camera_org_id else None
                    if not org_id and c.site_org_id:
                        org_id = str(c.site_org_id)
                    if not org_id and c.zone_site_id:
                        z_site = await session.execute(text("SELECT organization_id FROM sites WHERE id = :s_id"), {"s_id": c.zone_site_id})
                        zs = z_site.fetchone()
                        if zs and zs.organization_id:
                            org_id = str(zs.organization_id)

                    zone_id = str(c.zone_id) if c.zone_id else None

                    active_sub_ids = set()
                    if org_id:
                        sub_rows = await session.execute(text("""
                            SELECT analytic_id, is_enabled, valid_until
                            FROM organization_subscriptions
                            WHERE organization_id = :org_id
                        """), {"org_id": org_id})
                        now = datetime.now(timezone.utc)
                        for sub in sub_rows.fetchall():
                            if sub.is_enabled and (not sub.valid_until or sub.valid_until.astimezone(timezone.utc) >= now):
                                active_sub_ids.add(str(sub.analytic_id))

                    zone_policies = {}
                    if zone_id:
                        zp_rows = await session.execute(text("""
                            SELECT analytic_id, is_enabled FROM zone_analytics_policies WHERE zone_id = :zone_id
                        """), {"zone_id": zone_id})
                        for zp in zp_rows.fetchall():
                            zone_policies[str(zp.analytic_id)] = bool(zp.is_enabled)

                    camera_overrides = {}
                    ov_rows = await session.execute(text("""
                        SELECT analytic_id, is_enabled FROM camera_analytics_overrides WHERE camera_id = :cam_id
                    """), {"cam_id": cam_id})
                    for ov in ov_rows.fetchall():
                        camera_overrides[str(ov.analytic_id)] = bool(ov.is_enabled)

                    for cat in catalog_items:
                        a_id = str(cat.id)
                        sub_active = a_id in active_sub_ids
                        zone_val = zone_policies.get(a_id, False)
                        override_val = camera_overrides.get(a_id)

                        if override_val is not None:
                            effective_enabled = override_val
                        else:
                            effective_enabled = zone_val

                        # Rule 1: Entitlement is mandatory
                        is_active = bool(sub_active and effective_enabled)

                        eff_config = None
                        if cat.internal_code == "uc3" and is_active and zone_id:
                            ppe_rows = await session.execute(text("""
                                SELECT ppe_type FROM uc3_zone_ppe_rules WHERE zone_id = :z_id AND required = true
                            """), {"z_id": zone_id})
                            req_ppe = [r.ppe_type for r in ppe_rows.fetchall()]

                            z_conf = 0.50
                            try:
                                async with session.begin_nested():
                                    zc_row = await session.execute(text("SELECT min_confidence FROM uc3_zones WHERE id = :z_id"), {"z_id": zone_id})
                                    zc = zc_row.fetchone()
                                    if zc and zc[0] is not None:
                                        z_conf = float(zc[0])
                                    else:
                                        zrc_row = await session.execute(text("SELECT min_confidence FROM zones WHERE id = :z_id"), {"z_id": zone_id})
                                        zrc = zrc_row.fetchone()
                                        if zrc and zrc[0] is not None:
                                            z_conf = float(zrc[0])
                            except Exception:
                                pass

                            eff_config = {"required_ppe": req_ppe, "min_confidence": z_conf}

                        await session.execute(text("""
                            INSERT INTO camera_effective_analytics (camera_id, analytic_id, is_active, effective_config, updated_at)
                            VALUES (:camera_id, :analytic_id, :is_active, CAST(:effective_config AS jsonb), now())
                            ON CONFLICT (camera_id, analytic_id)
                            DO UPDATE SET is_active = EXCLUDED.is_active, effective_config = EXCLUDED.effective_config, updated_at = now()
                        """), {
                            "camera_id": cam_id,
                            "analytic_id": a_id,
                            "is_active": is_active,
                            "effective_config": json.dumps(eff_config) if eff_config else None
                        })

    async def list_camera_analytics_overrides(self, camera_id: str) -> list[dict]:
        async with self._session_factory() as session:
            c_row = await session.execute(text("SELECT id FROM cameras WHERE id = :id"), {"id": camera_id})
            if not c_row.fetchone():
                raise ValueError(f"Camera {camera_id} not found")

            rows = await session.execute(text("""
                SELECT o.id, o.camera_id, o.analytic_id, o.is_enabled, o.created_at, o.updated_at,
                       a.code AS analytic_code, a.internal_code AS analytic_internal_code, a.display_name AS analytic_display_name
                FROM camera_analytics_overrides o
                JOIN analytics_catalog a ON o.analytic_id = a.id
                WHERE o.camera_id = :camera_id
                ORDER BY a.internal_code ASC
            """), {"camera_id": camera_id})
            results = []
            for r in rows.fetchall():
                m = dict(r._mapping)
                m["id"] = str(m["id"])
                m["camera_id"] = str(m["camera_id"])
                m["analytic_id"] = str(m["analytic_id"])
                results.append(m)
            return results

    async def set_camera_analytics_override(
        self,
        camera_id: str,
        analytic_id: str,
        is_enabled: bool,
        current_user: dict | None = None,
        user_org_id: str | None = None
    ) -> dict:
        eff_user_org_id = user_org_id or (current_user.get("org_id") if isinstance(current_user, dict) else None)

        async with self._session_factory() as session:
            async with session.begin():
                c_row = await session.execute(text("""
                    SELECT c.id, c.organization_id AS c_org, s.organization_id AS s_org
                    FROM cameras c
                    LEFT JOIN sites s ON c.site_id = s.id
                    WHERE c.id = :id
                """), {"id": camera_id})
                c = c_row.fetchone()
                if not c:
                    raise ValueError(f"Camera {camera_id} not found")

                cam_org_id = str(c.c_org) if c.c_org else (str(c.s_org) if c.s_org else None)
                if eff_user_org_id and cam_org_id and str(eff_user_org_id) != cam_org_id:
                    raise PermissionError(f"User organization {eff_user_org_id} does not match camera organization {cam_org_id}")

                a_row = await session.execute(text("""
                    SELECT id FROM analytics_catalog WHERE id::text = :id OR code = :id OR internal_code = :id
                """), {"id": analytic_id})
                a = a_row.fetchone()
                if not a:
                    raise ValueError(f"Analytic {analytic_id} not found in catalog")

                actual_analytic_id = str(a.id)

                if is_enabled and cam_org_id:
                    sub_row = await session.execute(text("""
                        SELECT max_cameras_allowed, is_enabled, valid_until
                        FROM organization_subscriptions
                        WHERE organization_id = :org_id AND analytic_id = :analytic_id
                    """), {"org_id": cam_org_id, "analytic_id": actual_analytic_id})
                    sub = sub_row.fetchone()

                    now = datetime.now(timezone.utc)
                    if not sub or not sub.is_enabled or (sub.valid_until and sub.valid_until.astimezone(timezone.utc) < now):
                        pass
                    elif sub and sub.max_cameras_allowed is not None:
                        eff_cur = await session.execute(text("""
                            SELECT is_active FROM camera_effective_analytics
                            WHERE camera_id = :camera_id AND analytic_id = :analytic_id
                        """), {"camera_id": camera_id, "analytic_id": actual_analytic_id})
                        ec = eff_cur.fetchone()
                        already_active = ec.is_active if ec else False

                        if not already_active:
                            cnt_row = await session.execute(text("""
                                SELECT COUNT(DISTINCT e.camera_id) AS cnt
                                FROM camera_effective_analytics e
                                JOIN cameras c ON e.camera_id = c.id
                                LEFT JOIN sites s ON c.site_id = s.id
                                WHERE (c.organization_id = :org_id OR s.organization_id = :org_id)
                                  AND e.analytic_id = :analytic_id
                                  AND e.is_active = true
                            """), {"org_id": cam_org_id, "analytic_id": actual_analytic_id})
                            current_usage = cnt_row.fetchone().cnt

                            if current_usage >= sub.max_cameras_allowed:
                                raise KeyError(f"ANALYTIC_CAMERA_LIMIT_EXCEEDED: Analytic camera limit ({sub.max_cameras_allowed}) reached for org {cam_org_id} (current usage: {current_usage})")

                ov_id = str(uuid.uuid4())
                await session.execute(text("""
                    INSERT INTO camera_analytics_overrides (id, camera_id, analytic_id, is_enabled, updated_at)
                    VALUES (:id, :camera_id, :analytic_id, :is_enabled, now())
                    ON CONFLICT (camera_id, analytic_id)
                    DO UPDATE SET is_enabled = EXCLUDED.is_enabled, updated_at = now()
                """), {
                    "id": ov_id,
                    "camera_id": camera_id,
                    "analytic_id": actual_analytic_id,
                    "is_enabled": is_enabled
                })

        await self.recalculate_effective_analytics([camera_id])

        overrides = await self.list_camera_analytics_overrides(camera_id)
        single = next((o for o in overrides if o["analytic_id"] == actual_analytic_id), None)
        return single or {}

    async def delete_camera_analytics_override(
        self,
        camera_id: str,
        analytic_id: str,
        current_user: dict | None = None,
        user_org_id: str | None = None
    ) -> None:
        eff_user_org_id = user_org_id or (current_user.get("org_id") if isinstance(current_user, dict) else None)

        async with self._session_factory() as session:
            async with session.begin():
                c_row = await session.execute(text("""
                    SELECT c.id, c.organization_id AS c_org, s.organization_id AS s_org
                    FROM cameras c
                    LEFT JOIN sites s ON c.site_id = s.id
                    WHERE c.id = :id
                """), {"id": camera_id})
                c = c_row.fetchone()
                if not c:
                    raise ValueError(f"Camera {camera_id} not found")

                cam_org_id = str(c.c_org) if c.c_org else (str(c.s_org) if c.s_org else None)
                if eff_user_org_id and cam_org_id and str(eff_user_org_id) != cam_org_id:
                    raise PermissionError(f"User organization {eff_user_org_id} does not match camera organization {cam_org_id}")

                a_row = await session.execute(text("""
                    SELECT id FROM analytics_catalog WHERE id::text = :id OR code = :id OR internal_code = :id
                """), {"id": analytic_id})
                a = a_row.fetchone()
                if not a:
                    raise ValueError(f"Analytic {analytic_id} not found in catalog")

                actual_analytic_id = str(a.id)

                await session.execute(text("""
                    DELETE FROM camera_analytics_overrides WHERE camera_id = :camera_id AND analytic_id = :analytic_id
                """), {"camera_id": camera_id, "analytic_id": actual_analytic_id})

        await self.recalculate_effective_analytics([camera_id])

    async def get_camera_effective_analytics(self, camera_id: str) -> list[dict]:
        await self.recalculate_effective_analytics([camera_id])

        async with self._session_factory() as session:
            c_row = await session.execute(text("""
                SELECT c.id, c.organization_id AS c_org, s.organization_id AS s_org, c.zone_id
                FROM cameras c
                LEFT JOIN sites s ON c.site_id = s.id
                WHERE c.id = :id
            """), {"id": camera_id})
            c = c_row.fetchone()
            if not c:
                raise ValueError(f"Camera {camera_id} not found")

            cam_org_id = str(c.c_org) if c.c_org else (str(c.s_org) if c.s_org else None)
            zone_id = str(c.zone_id) if c.zone_id else None

            sub_map = {}
            if cam_org_id:
                s_rows = await session.execute(text("SELECT analytic_id, is_enabled, valid_until FROM organization_subscriptions WHERE organization_id = :org_id"), {"org_id": cam_org_id})
                now = datetime.now(timezone.utc)
                for s in s_rows.fetchall():
                    active = bool(s.is_enabled and (not s.valid_until or s.valid_until.astimezone(timezone.utc) >= now))
                    sub_map[str(s.analytic_id)] = active

            zone_map = {}
            if zone_id:
                z_rows = await session.execute(text("SELECT analytic_id, is_enabled FROM zone_analytics_policies WHERE zone_id = :z_id"), {"z_id": zone_id})
                for z in z_rows.fetchall():
                    zone_map[str(z.analytic_id)] = bool(z.is_enabled)

            ov_map = {}
            o_rows = await session.execute(text("SELECT analytic_id, is_enabled FROM camera_analytics_overrides WHERE camera_id = :c_id"), {"c_id": camera_id})
            for o in o_rows.fetchall():
                ov_map[str(o.analytic_id)] = bool(o.is_enabled)

            eff_rows = await session.execute(text("""
                SELECT e.analytic_id, e.is_active, e.effective_config,
                       a.code, a.internal_code, a.display_name
                FROM camera_effective_analytics e
                JOIN analytics_catalog a ON e.analytic_id = a.id
                WHERE e.camera_id = :c_id
                ORDER BY a.internal_code ASC
            """), {"c_id": camera_id})

            results = []
            for r in eff_rows.fetchall():
                aid = str(r.analytic_id)
                ov_val = ov_map.get(aid)
                z_val = zone_map.get(aid, False)
                sub_val = sub_map.get(aid, False)

                if ov_val is not None:
                    src = "camera_override"
                elif z_val:
                    src = "zone"
                else:
                    src = "none"

                parsed_config = json.loads(r.effective_config) if isinstance(r.effective_config, str) else r.effective_config

                results.append({
                    "analytic_id": aid,
                    "internal_code": r.internal_code,
                    "code": r.code,
                    "display_name": r.display_name,
                    "is_active": bool(r.is_active),
                    "source": src,
                    "effective_config": parsed_config,
                    "zone_policy_enabled": z_val,
                    "override_enabled": ov_val,
                    "subscription_active": sub_val
                })
            return results


