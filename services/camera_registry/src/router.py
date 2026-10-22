import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Header
from typing import Optional

from services.camera_registry.src.schemas import (
    CameraCreate, CameraConfigUpdate, CameraResponse, CameraStatusUpdate,
    OrganizationCreate, OrganizationUpdate, OrganizationStatusUpdate, OrganizationResponse,
    SiteCreate, SiteUpdate, SiteResponse,
    ZoneCreate, ZoneUpdate, ZoneResponse,
    CameraAssignZone,
    AnalyticsCatalogResponse,
    OrganizationSubscriptionCreate, OrganizationSubscriptionUpdate, OrganizationSubscriptionResponse,
    ZoneAnalyticsPolicyItem, ZoneAnalyticsPolicyUpdate,
    ZoneAnalyticsPolicyBulkItem, ZoneAnalyticsPolicyBulkUpdate,
    ZonePPERuleItem, ZonePPERulesConfig,
    CameraAnalyticsOverrideItem, CameraAnalyticsOverrideUpdate, CameraEffectiveAnalyticItem,
    VideoSessionResponse, VideoSessionProcessResponse, VideoSessionCreateRequest
)
from services.camera_registry.src.service import CameraRegistryService
from services.camera_registry.src.video_sessions import CameraRegistryVideoSessionCoordinator
from services.auth.src.rbac import get_current_user, require_role, require_organization_access, Role, verify_resource_org
from services.audit.src.writer import write_audit_entry
from uuid import UUID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["camera-registry"])
analytics_router = APIRouter(prefix="/analytics", tags=["analytics-catalog"])
organizations_router = APIRouter(prefix="/organizations", tags=["organization-subscriptions"])
zones_router = APIRouter(prefix="/zones", tags=["zone-analytics"])

def get_service() -> CameraRegistryService:
    raise RuntimeError("Camera Registry service dependency not configured")

def get_video_coordinator(service: CameraRegistryService = Depends(get_service)) -> CameraRegistryVideoSessionCoordinator:
    return CameraRegistryVideoSessionCoordinator(redis_client=service._redis)

def _user_org_id(user: dict) -> str | None:
    if user.get("role") == Role.SUPERADMIN:
        return None
    return user.get("org_id") or user.get("organization_id")

async def _audit(service: CameraRegistryService, action: str, entity_type: str, entity_id: str, user: dict, metadata: dict | None = None) -> None:
    try:
        await write_audit_entry(
            session_factory=service._session_factory,
            service="camera_registry",
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            user_id=user.get("sub"),
            metadata=metadata or {}
        )
    except Exception as e:
        logger.error(f"Audit log write failed for action={action} entity={entity_type}:{entity_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Security audit logging failed: {e}. Administrative mutation aborted to preserve compliance integrity."
        )

# --- Analytics Catalog Endpoints ---
@analytics_router.get("/catalog", response_model=list[AnalyticsCatalogResponse])
@router.get("/analytics/catalog", response_model=list[AnalyticsCatalogResponse])
async def list_analytics_catalog(
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    return await service.list_analytics_catalog()

# --- Organization Subscriptions Endpoints ---
@organizations_router.get("/{organization_id}/subscriptions", response_model=list[OrganizationSubscriptionResponse])
@router.get("/organizations/{organization_id}/subscriptions", response_model=list[OrganizationSubscriptionResponse])
async def list_organization_subscriptions(
    organization_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if not user_org or str(user_org) != str(organization_id):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
    try:
        return await service.list_organization_subscriptions(organization_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@organizations_router.post("/{organization_id}/subscriptions", response_model=OrganizationSubscriptionResponse, status_code=201, dependencies=[Depends(require_role(Role.SUPERADMIN))])
@router.post("/organizations/{organization_id}/subscriptions", response_model=OrganizationSubscriptionResponse, status_code=201, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def create_organization_subscription(
    organization_id: str,
    body: OrganizationSubscriptionCreate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: SUPERADMIN role required to manage organization subscriptions")
    try:
        created = await service.create_organization_subscription(organization_id, body)
        await _audit(service, "subscription_created", "organization_subscription", str(created["id"]), user, {"organization_id": organization_id, "analytic_id": str(body.analytic_id), "max_cameras_allowed": body.max_cameras_allowed})
        return created
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))

@organizations_router.put("/{organization_id}/subscriptions/{analytic_id}", response_model=OrganizationSubscriptionResponse, dependencies=[Depends(require_role(Role.SUPERADMIN))])
@router.put("/organizations/{organization_id}/subscriptions/{analytic_id}", response_model=OrganizationSubscriptionResponse, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def update_organization_subscription(
    organization_id: str,
    analytic_id: str,
    body: OrganizationSubscriptionUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: SUPERADMIN role required to manage organization subscriptions")
    try:
        res = await service.update_organization_subscription(organization_id, analytic_id, body)
        if not res:
            raise HTTPException(status_code=404, detail="Subscription not found")
        await _audit(service, "subscription_updated", "organization_subscription", str(res["id"]), user, {"organization_id": organization_id, "analytic_id": analytic_id, "max_cameras_allowed": body.max_cameras_allowed, "is_enabled": body.is_enabled})
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@organizations_router.delete("/{organization_id}/subscriptions/{analytic_id}", status_code=204, dependencies=[Depends(require_role(Role.SUPERADMIN))])
@router.delete("/organizations/{organization_id}/subscriptions/{analytic_id}", status_code=204, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def delete_organization_subscription(
    organization_id: str,
    analytic_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: SUPERADMIN role required to manage organization subscriptions")
    try:
        await service.delete_organization_subscription(organization_id, analytic_id)
        await _audit(service, "subscription_deleted", "organization_subscription", f"{organization_id}:{analytic_id}", user, {"organization_id": organization_id, "analytic_id": analytic_id})
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Zone Analytics & PPE Policy Endpoints ---
@zones_router.get("/{zone_id}/analytics", response_model=list[ZoneAnalyticsPolicyItem])
@router.get("/zones/{zone_id}/analytics", response_model=list[ZoneAnalyticsPolicyItem])
async def list_zone_analytics_policies(
    zone_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    zone = await service.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    verify_resource_org(zone.get("organization_id"), user)
    try:
        return await service.list_zone_analytics_policies(zone_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@zones_router.put("/{zone_id}/analytics/{analytic_id}", response_model=ZoneAnalyticsPolicyItem, dependencies=[Depends(require_role(Role.ADMIN))])
@router.put("/zones/{zone_id}/analytics/{analytic_id}", response_model=ZoneAnalyticsPolicyItem, dependencies=[Depends(require_role(Role.ADMIN))])
async def update_zone_analytics_policy(
    zone_id: str,
    analytic_id: str,
    body: ZoneAnalyticsPolicyUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    try:
        return await service.update_zone_analytics_policy(zone_id, analytic_id, body.is_enabled, user_org_id=_user_org_id(user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

@zones_router.put("/{zone_id}/analytics", response_model=list[ZoneAnalyticsPolicyItem], dependencies=[Depends(require_role(Role.ADMIN))])
@router.put("/zones/{zone_id}/analytics", response_model=list[ZoneAnalyticsPolicyItem], dependencies=[Depends(require_role(Role.ADMIN))])
async def bulk_update_zone_analytics_policies(
    zone_id: str,
    body: ZoneAnalyticsPolicyBulkUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    try:
        items = [{"analytic_id": str(item.analytic_id), "is_enabled": item.is_enabled} for item in body.items]
        return await service.bulk_update_zone_analytics_policies(zone_id, items, user_org_id=_user_org_id(user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

@zones_router.get("/{zone_id}/ppe-rules", response_model=ZonePPERulesConfig)
@router.get("/zones/{zone_id}/ppe-rules", response_model=ZonePPERulesConfig)
async def get_zone_ppe_rules(
    zone_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    zone = await service.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    verify_resource_org(zone.get("organization_id"), user)
    try:
        return await service.get_zone_ppe_rules(zone_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@zones_router.put("/{zone_id}/ppe-rules", response_model=ZonePPERulesConfig, dependencies=[Depends(require_role(Role.ADMIN))])
@router.put("/zones/{zone_id}/ppe-rules", response_model=ZonePPERulesConfig, dependencies=[Depends(require_role(Role.ADMIN))])
async def update_zone_ppe_rules(
    zone_id: str,
    body: ZonePPERulesConfig,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    try:
        rules = body.ppe_rules if (body.ppe_rules and len(body.ppe_rules) > 0) else (body.rules or [])
        return await service.update_zone_ppe_rules(zone_id, rules, body.min_confidence, user_org_id=_user_org_id(user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

# --- Organizations ---
@organizations_router.post("", response_model=OrganizationResponse, status_code=201, dependencies=[Depends(require_role(Role.SUPERADMIN))])
@router.post("/organizations", response_model=OrganizationResponse, status_code=201, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def create_organization(
    body: OrganizationCreate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    org = await service.create_organization(body)
    await _audit(service, "organization_created", "organization", org["id"], user, {"name": org["name"], "code": org["code"]})
    return org

@organizations_router.get("", response_model=list[OrganizationResponse])
@router.get("/organizations", response_model=list[OrganizationResponse])
async def list_organizations(
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    orgs = await service.list_organizations()
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if user_org:
            return [o for o in orgs if str(o["id"]) == str(user_org)]
        return []
    return orgs

@organizations_router.put("/{organization_id}", response_model=OrganizationResponse, dependencies=[Depends(require_role(Role.SUPERADMIN))])
@router.put("/organizations/{organization_id}", response_model=OrganizationResponse, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def update_organization(
    organization_id: str,
    body: OrganizationUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: SUPERADMIN role required")
    org = await service.get_organization(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    updated = await service.update_organization(organization_id, body)
    await _audit(
        service,
        "organization_updated",
        "organization",
        organization_id,
        user,
        {"name": updated.get("name"), "tier": updated.get("tier")}
    )
    return updated

@organizations_router.put("/{organization_id}/status", response_model=OrganizationResponse, dependencies=[Depends(require_role(Role.SUPERADMIN))])
@router.put("/organizations/{organization_id}/status", response_model=OrganizationResponse, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def update_organization_status(
    organization_id: str,
    body: OrganizationStatusUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        raise HTTPException(status_code=403, detail="Forbidden: SUPERADMIN role required")
    org = await service.get_organization(organization_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    updated = await service.update_organization_status(organization_id, body.is_active)
    await _audit(
        service,
        "organization_status_updated",
        "organization",
        organization_id,
        user,
        {"is_active": body.is_active, "name": updated.get("name")}
    )
    return updated

# --- Sites ---
@router.post("/sites", response_model=SiteResponse, status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_site(
    body: SiteCreate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if not user_org or str(body.organization_id) != str(user_org):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
    site = await service.create_site(body)
    await _audit(service, "site_created", "site", site["id"], user, {"name": site["name"], "code": site["code"]})
    return site

@router.get("/sites", response_model=list[SiteResponse])
async def list_sites(
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if organization_id and str(organization_id) != str(user_org):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
        organization_id = user_org
    return await service.list_sites(organization_id)

@router.get("/sites/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    site = await service.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    verify_resource_org(site.get("organization_id"), user)
    return site

@router.put("/sites/{site_id}", response_model=SiteResponse, dependencies=[Depends(require_role(Role.ADMIN))])
async def update_site(
    site_id: str,
    body: SiteUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    site = await service.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    verify_resource_org(site.get("organization_id"), user)
    updated = await service.update_site(site_id, body)
    await _audit(service, "site_updated", "site", site_id, user, {"name": updated.get("name"), "code": updated.get("code")})
    return updated

@router.delete("/sites/{site_id}", status_code=204, dependencies=[Depends(require_role(Role.ADMIN))])
async def delete_site(
    site_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    site = await service.get_site(site_id)
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    verify_resource_org(site.get("organization_id"), user)
    try:
        await service.delete_site(site_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Site deletion aborted due to safety check failure for site_id={site_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Administrative deletion aborted: database safety dependency check failed. Consult server logs."
        )
    await _audit(service, "site_deleted", "site", site_id, user, {"name": site.get("name"), "code": site.get("code")})

# --- Zones ---
@zones_router.post("", response_model=ZoneResponse, status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
@router.post("/zones", response_model=ZoneResponse, status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_zone(
    body: ZoneCreate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if body.site_id:
            site = await service.get_site(str(body.site_id))
            if not site or str(site.get("organization_id")) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
    zone = await service.create_zone(body)
    await _audit(service, "zone_created", "zone", zone["id"], user, {"name": zone["name"]})
    return zone

@zones_router.get("", response_model=list[ZoneResponse])
@router.get("/zones", response_model=list[ZoneResponse])
async def list_zones(
    site_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if site_id:
            site = await service.get_site(site_id)
            if not site or str(site.get("organization_id")) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
            return await service.list_zones(site_id)
        zones = await service.list_zones(None)
        return [z for z in zones if str(z.get("organization_id")) == str(user_org)]
    return await service.list_zones(site_id)

@zones_router.get("/{zone_id}", response_model=ZoneResponse)
@router.get("/zones/{zone_id}", response_model=ZoneResponse)
async def get_zone(
    zone_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    zone = await service.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    verify_resource_org(zone.get("organization_id"), user)
    return zone

@zones_router.put("/{zone_id}", response_model=ZoneResponse, dependencies=[Depends(require_role(Role.ADMIN))])
@router.put("/zones/{zone_id}", response_model=ZoneResponse, dependencies=[Depends(require_role(Role.ADMIN))])
async def update_zone(
    zone_id: str,
    body: ZoneUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    zone = await service.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    verify_resource_org(zone.get("organization_id"), user)
    updated = await service.update_zone(zone_id, body)
    await _audit(service, "zone_updated", "zone", zone_id, user, {"name": updated.get("name"), "zone_type": updated.get("zone_type")})
    return updated

@zones_router.delete("/{zone_id}", status_code=204, dependencies=[Depends(require_role(Role.ADMIN))])
@router.delete("/zones/{zone_id}", status_code=204, dependencies=[Depends(require_role(Role.ADMIN))])
async def delete_zone(
    zone_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    zone = await service.get_zone(zone_id)
    if not zone:
        raise HTTPException(status_code=404, detail="Zone not found")
    verify_resource_org(zone.get("organization_id"), user)
    try:
        await service.delete_zone(zone_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Zone deletion aborted due to safety check failure for zone_id={zone_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail="Administrative deletion aborted: database safety dependency check failed. Consult server logs."
        )
    await _audit(service, "zone_deleted", "zone", zone_id, user, {"name": zone.get("name"), "site_id": str(zone.get("site_id")) if zone.get("site_id") else None})

# --- Camera Endpoints ---
@router.post("", status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_camera(
    body: CameraCreate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if body.organization_id and str(body.organization_id) != str(user_org):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
        if body.site_id:
            site = await service.get_site(str(body.site_id))
            if not site or str(site.get("organization_id")) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
        if not body.organization_id and user_org:
            body.organization_id = UUID(str(user_org))
    cam = await service.create_camera(body)
    await _audit(service, "camera_created", "camera", cam["id"], user, {"name": cam["name"], "location": cam.get("location")})
    return cam

@router.get("")
async def list_cameras(
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    cameras = await service.get_active_cameras()
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if user_org:
            return [c for c in cameras if str(c.get("organization_id")) == str(user_org)]
    return cameras

@router.get("/by-uc/{uc_id}")
async def cameras_for_uc(
    uc_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    camera_ids = await service.get_cameras_for_uc(uc_id)
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        active_cams = await service.get_active_cameras()
        org_cam_ids = {str(c["id"]) for c in active_cams if str(c.get("organization_id")) == str(user_org)}
        camera_ids = [cid for cid in camera_ids if cid in org_cam_ids]
    return {"uc_id": uc_id, "camera_ids": camera_ids}

@router.put("/{camera_id}/assign-zone", dependencies=[Depends(require_role(Role.ADMIN))])
async def assign_camera_zone(
    camera_id: str,
    body: CameraAssignZone,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    camera = await service.get_camera(camera_id, include_disabled=True)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)

    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if body.site_id:
            site = await service.get_site(str(body.site_id))
            if not site or str(site.get("organization_id")) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
        if body.zone_id:
            zone = await service.get_zone(str(body.zone_id))
            if not zone or str(zone.get("organization_id")) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization access forbidden")

    res = await service.assign_camera_zone(
        camera_id,
        site_id=str(body.site_id) if body.site_id else None,
        zone_id=str(body.zone_id) if body.zone_id else None,
        lifecycle_state=body.lifecycle_state
    )
    if not res:
        raise HTTPException(status_code=404, detail="Camera not found")
    await _audit(
        service,
        "camera_zone_assigned",
        "camera",
        camera_id,
        user,
        {"site_id": str(body.site_id) if body.site_id else None, "zone_id": str(body.zone_id) if body.zone_id else None, "lifecycle_state": body.lifecycle_state}
    )
    return res

@router.get("/{camera_id}/hierarchy")
async def get_camera_hierarchy(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    res = await service.get_camera_hierarchy(camera_id)
    if not res:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(res.get("organization_id") or (res.get("organization") or {}).get("id"), user)
    return res

@router.put("/{camera_id}/config", dependencies=[Depends(require_role(Role.ADMIN))])
async def update_config(
    camera_id: str,
    body: CameraConfigUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    await service.update_config(camera_id, body)
    await _audit(
        service,
        "camera_config_updated",
        "camera",
        camera_id,
        user,
        {"fields": list(body.model_dump(exclude_unset=True).keys())}
    )
    return {"status": "updated"}

@router.delete("/{camera_id}", status_code=204, dependencies=[Depends(require_role(Role.ADMIN))])
async def delete_camera(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
): 
    camera = await service.get_camera(camera_id, include_disabled=True)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    await service.decommission_camera(camera_id)
    await _audit(
        service,
        "camera_decommissioned",
        "camera",
        camera_id,
        user,
        {"name": camera.get("name"), "status": "disabled", "lifecycle_state": "disabled"}
    )

@router.put("/{camera_id}/decommission", dependencies=[Depends(require_role(Role.ADMIN))])
async def decommission_camera(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id, include_disabled=True)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    updated = await service.decommission_camera(camera_id)
    await _audit(
        service,
        "camera_decommissioned",
        "camera",
        camera_id,
        user,
        {"name": camera.get("name"), "status": "disabled", "lifecycle_state": "disabled"}
    )
    return updated

@router.get("/{camera_id}")
async def get_camera_by_id(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    return camera

@router.get("/{camera_id}/status")
async def get_status(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404)
    verify_resource_org(camera.get("organization_id"), user)
    return {
        "camera_id": camera_id,
        "status": camera["status"],
        "use_cases": camera["use_cases"],
    }

@router.patch("/{camera_id}/status", dependencies=[Depends(require_role(Role.ADMIN))])
async def update_status(
    camera_id: str,
    body: CameraStatusUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    await service.update_status(camera_id, body.status)
    return {
        "camera_id": camera_id,
        "status": body.status,
    }

# --- Camera Analytics Overrides & Effective Analytics ---
@router.get("/{camera_id}/analytics/overrides", response_model=list[CameraAnalyticsOverrideItem])
async def list_camera_analytics_overrides(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    try:
        return await service.list_camera_analytics_overrides(camera_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.put("/{camera_id}/analytics/{analytic_id}/override", response_model=CameraAnalyticsOverrideItem, dependencies=[Depends(require_role(Role.ADMIN))])
async def set_camera_analytics_override(
    camera_id: str,
    analytic_id: str,
    body: CameraAnalyticsOverrideUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    try:
        return await service.set_camera_analytics_override(camera_id, analytic_id, body.is_enabled, user_org_id=_user_org_id(user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.delete("/{camera_id}/analytics/{analytic_id}/override", status_code=204, dependencies=[Depends(require_role(Role.ADMIN))])
async def delete_camera_analytics_override(
    camera_id: str,
    analytic_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    try:
        await service.delete_camera_analytics_override(camera_id, analytic_id, user_org_id=_user_org_id(user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("/{camera_id}/analytics/effective", response_model=list[CameraEffectiveAnalyticItem])
async def get_camera_effective_analytics(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    try:
        return await service.get_camera_effective_analytics(camera_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# --- Camera-Based Video Upload & Video Sessions (Phases B & C) ---
@router.post(
    "/{camera_id}/upload-video",
    response_model=VideoSessionResponse,
    status_code=201,
    dependencies=[Depends(require_role(Role.OPERATOR))]
)
async def upload_camera_video(
    camera_id: str,
    request: Request,
    filename: Optional[str] = Query(default=None),
    x_filename: Optional[str] = Header(default=None),
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
    coordinator: CameraRegistryVideoSessionCoordinator = Depends(get_video_coordinator),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)

    # Determine filename
    chosen_filename = filename or x_filename

    # Read body
    content_type = request.headers.get("content-type", "")
    body_bytes = await request.body()

    # Check if request passed JSON reference to existing test video
    if "application/json" in content_type and body_bytes:
        try:
            json_body = json.loads(body_bytes.decode("utf-8"))
            test_fname = json_body.get("filename")
            if test_fname:
                try:
                    return await coordinator.create_session_from_existing_test_video(
                        camera_id=camera_id,
                        organization_id=camera.get("organization_id"),
                        video_filename=test_fname,
                        target_fps=float(camera.get("fps", 10.0)),
                    )
                except FileNotFoundError as e:
                    raise HTTPException(status_code=404, detail=str(e))
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
        except json.JSONDecodeError:
            pass

    if not body_bytes or len(body_bytes) == 0:
        raise HTTPException(status_code=400, detail="Video upload payload cannot be empty")

    if not chosen_filename:
        chosen_filename = f"video_{uuid.uuid4().hex[:8]}.mp4"

    try:
        session = await coordinator.create_session_from_bytes(
            camera_id=camera_id,
            organization_id=camera.get("organization_id"),
            filename=chosen_filename,
            content=body_bytes,
            target_fps=float(camera.get("fps", 10.0)),
        )
        return session
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process video upload: {e}")

@router.get("/{camera_id}/video-sessions", response_model=list[VideoSessionResponse])
async def list_camera_video_sessions(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
    coordinator: CameraRegistryVideoSessionCoordinator = Depends(get_video_coordinator),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)
    return await coordinator.list_camera_sessions(camera_id)

@router.get("/{camera_id}/video-sessions/{session_id}", response_model=VideoSessionResponse)
async def get_camera_video_session(
    camera_id: str,
    session_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
    coordinator: CameraRegistryVideoSessionCoordinator = Depends(get_video_coordinator),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)

    session = await coordinator.get_session(session_id)
    if not session or str(session.get("camera_id")) != str(camera_id):
        raise HTTPException(status_code=404, detail=f"Video session '{session_id}' not found for camera '{camera_id}'")
    return session

@router.post(
    "/{camera_id}/video-sessions/{session_id}/process",
    response_model=VideoSessionProcessResponse,
    dependencies=[Depends(require_role(Role.OPERATOR))]
)
async def process_camera_video_session(
    camera_id: str,
    session_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
    coordinator: CameraRegistryVideoSessionCoordinator = Depends(get_video_coordinator),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)

    session = await coordinator.get_session(session_id)
    if not session or str(session.get("camera_id")) != str(camera_id):
        raise HTTPException(status_code=404, detail="Video session not found")

    # Source Isolation Guard: Never interleave with active live RTSP stream
    if camera.get("status") == "online" and not camera.get("is_simulation", False):
        # Check if live RTSP stream exists in Redis and has recent live frames
        latest_frames = await service._redis.xrevrange(f"frames:{camera_id}", max="+", min="-", count=1)
        if latest_frames:
            try:
                raw_payload = latest_frames[0][1].get(b"data") or latest_frames[0][1].get("data")
                if raw_payload:
                    f_data = json.loads(raw_payload.decode("utf-8") if isinstance(raw_payload, bytes) else raw_payload)
                    # Only block if stream is live RTSP (not a finished/prior video upload session)
                    # and the frame was published recently (within the last 15 seconds)
                    if f_data.get("source_type") != "uploaded_video":
                        ts_str = f_data.get("timestamp")
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if (datetime.now(timezone.utc) - ts).total_seconds() < 15.0:
                                raise HTTPException(
                                    status_code=409,
                                    detail="CAMERA_LIVE_BUSY: Cannot start video upload session while live RTSP ingestion is actively running on this camera. Stop live stream before starting uploaded video session."
                                )
            except HTTPException:
                raise
            except Exception as e:
                logger.warning("live_stream_check_failed camera_id=%s error=%s", camera_id, e)

    # Resolve effective analytics dynamically
    eff_items = await service.get_camera_effective_analytics(camera_id)
    active_analytics = [item["internal_code"] for item in eff_items if item.get("is_active")]

    try:
        updated_session = await coordinator.call_ingestion_start(
            session_id=session_id,
            effective_analytics=active_analytics,
            fps=float(camera.get("fps", 10.0)),
        )
        return {
            "session_id": session_id,
            "camera_id": camera_id,
            "status": updated_session.get("status", "processing"),
            "message": f"Video session started successfully. Active analytics: {active_analytics or ['none']}",
            "effective_analytics": active_analytics,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post(
    "/{camera_id}/video-sessions/{session_id}/stop",
    response_model=VideoSessionProcessResponse,
    dependencies=[Depends(require_role(Role.OPERATOR))]
)
async def stop_camera_video_session(
    camera_id: str,
    session_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
    coordinator: CameraRegistryVideoSessionCoordinator = Depends(get_video_coordinator),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    verify_resource_org(camera.get("organization_id"), user)

    session = await coordinator.get_session(session_id)
    if not session or str(session.get("camera_id")) != str(camera_id):
        raise HTTPException(status_code=404, detail="Video session not found")

    try:
        stopped_session = await coordinator.call_ingestion_stop(session_id)
        return {
            "session_id": session_id,
            "camera_id": camera_id,
            "status": stopped_session.get("status", "stopped"),
            "message": "Video session playback stopped",
            "effective_analytics": stopped_session.get("effective_analytics", []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))