from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from services.camera_registry.src.schemas import (
    CameraCreate, CameraConfigUpdate, CameraResponse, CameraStatusUpdate,
    OrganizationCreate, OrganizationResponse,
    SiteCreate, SiteResponse,
    ZoneCreate, ZoneResponse,
    CameraAssignZone,
    AnalyticsCatalogResponse,
    OrganizationSubscriptionCreate, OrganizationSubscriptionUpdate, OrganizationSubscriptionResponse,
    ZoneAnalyticsPolicyItem, ZoneAnalyticsPolicyUpdate,
    ZoneAnalyticsPolicyBulkItem, ZoneAnalyticsPolicyBulkUpdate,
    ZonePPERuleItem, ZonePPERulesConfig,
    CameraAnalyticsOverrideItem, CameraAnalyticsOverrideUpdate, CameraEffectiveAnalyticItem
)
from services.camera_registry.src.service import CameraRegistryService
from services.auth.src.rbac import get_current_user, require_role, require_organization_access, Role, verify_resource_org
from uuid import UUID

router = APIRouter(prefix="/cameras", tags=["camera-registry"])
analytics_router = APIRouter(prefix="/analytics", tags=["analytics-catalog"])
organizations_router = APIRouter(prefix="/organizations", tags=["organization-subscriptions"])
zones_router = APIRouter(prefix="/zones", tags=["zone-analytics"])

def get_service() -> CameraRegistryService:
    raise RuntimeError("Camera Registry service dependency not configured")

def _user_org_id(user: dict) -> str | None:
    if user.get("role") == Role.SUPERADMIN:
        return None
    return user.get("org_id") or user.get("organization_id")

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

@organizations_router.post("/{organization_id}/subscriptions", response_model=OrganizationSubscriptionResponse, status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
@router.post("/organizations/{organization_id}/subscriptions", response_model=OrganizationSubscriptionResponse, status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_organization_subscription(
    organization_id: str,
    body: OrganizationSubscriptionCreate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if not user_org or str(user_org) != str(organization_id):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
    try:
        return await service.create_organization_subscription(organization_id, body)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=409, detail=str(e))

@organizations_router.put("/{organization_id}/subscriptions/{analytic_id}", response_model=OrganizationSubscriptionResponse, dependencies=[Depends(require_role(Role.ADMIN))])
@router.put("/organizations/{organization_id}/subscriptions/{analytic_id}", response_model=OrganizationSubscriptionResponse, dependencies=[Depends(require_role(Role.ADMIN))])
async def update_organization_subscription(
    organization_id: str,
    analytic_id: str,
    body: OrganizationSubscriptionUpdate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if not user_org or str(user_org) != str(organization_id):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
    try:
        res = await service.update_organization_subscription(organization_id, analytic_id, body)
        if not res:
            raise HTTPException(status_code=404, detail="Subscription not found")
        return res
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@organizations_router.delete("/{organization_id}/subscriptions/{analytic_id}", status_code=204, dependencies=[Depends(require_role(Role.ADMIN))])
@router.delete("/organizations/{organization_id}/subscriptions/{analytic_id}", status_code=204, dependencies=[Depends(require_role(Role.ADMIN))])
async def delete_organization_subscription(
    organization_id: str,
    analytic_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    if user.get("role") != Role.SUPERADMIN:
        user_org = _user_org_id(user)
        if not user_org or str(user_org) != str(organization_id):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
    try:
        await service.delete_organization_subscription(organization_id, analytic_id)
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
        return await service.update_zone_ppe_rules(zone_id, body.rules, body.min_confidence, user_org_id=_user_org_id(user))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

# --- Organizations ---
@router.post("/organizations", response_model=OrganizationResponse, status_code=201, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def create_organization(
    body: OrganizationCreate,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service)
):
    return await service.create_organization(body)

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
    return await service.create_site(body)

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

# --- Zones ---
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
    return await service.create_zone(body)

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
    return await service.create_camera(body)

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
    camera = await service.get_camera(camera_id)
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
    return {"status": "updated"}

@router.delete("/{camera_id}", status_code=204, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def delete_camera(
    camera_id: str,
    user: dict = Depends(get_current_user),
    service: CameraRegistryService = Depends(get_service),
): 
    await service.delete_camera(camera_id)

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