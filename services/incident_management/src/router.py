import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header
from shared.platform_client.db import get_session_factory
from services.auth.src.rbac import get_current_user, require_role, Role

from .config import settings
from .service import IncidentService
from .schemas import (
    IncidentCreate,
    IncidentUpdate,
    IncidentStatusUpdate,
    IncidentAssignUpdate,
    IncidentResponse,
    IncidentDetailResponse,
    IncidentSummaryResponse,
)

router = APIRouter(prefix="/incidents", tags=["incidents"])

def get_service() -> IncidentService:
    db_url = settings.database_url or os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform"
    )
    session_factory = get_session_factory(db_url)
    return IncidentService(session_factory)


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    organization_id: Optional[str] = None,
    site_id: Optional[str] = None,
    zone_id: Optional[str] = None,
    camera_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.list_incidents(
        user=user,
        status=status,
        severity=severity,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        assigned_to=assigned_to,
        source_type=source_type,
        limit=limit,
        offset=offset,
    )


@router.get("/summary", response_model=IncidentSummaryResponse)
async def get_incident_summary(
    organization_id: Optional[str] = None,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.get_incident_summary(user=user, organization_id=organization_id)


@router.get("/{incident_id}", response_model=IncidentDetailResponse)
async def get_incident(
    incident_id: str,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.get_incident(incident_id, user=user)


@router.post("", response_model=IncidentDetailResponse, status_code=201, dependencies=[Depends(require_role(Role.OPERATOR))])
async def create_incident(
    body: IncidentCreate,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.create_incident(data=body.model_dump(), user=user)


@router.put("/{incident_id}", response_model=IncidentDetailResponse, dependencies=[Depends(require_role(Role.OPERATOR))])
async def update_incident(
    incident_id: str,
    body: IncidentUpdate,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.update_incident(incident_id=incident_id, data=body.model_dump(exclude_unset=True), user=user)


@router.put("/{incident_id}/status", response_model=IncidentDetailResponse, dependencies=[Depends(require_role(Role.OPERATOR))])
async def update_status(
    incident_id: str,
    body: IncidentStatusUpdate,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.update_status(incident_id=incident_id, new_status=body.status, user=user)


@router.put("/{incident_id}/assign", response_model=IncidentDetailResponse, dependencies=[Depends(require_role(Role.OPERATOR))])
async def assign_incident(
    incident_id: str,
    body: IncidentAssignUpdate,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.assign_incident(incident_id=incident_id, assignee_id=body.assigned_to, user=user)


@router.post("/{incident_id}/alerts/{alert_id}", response_model=IncidentDetailResponse, dependencies=[Depends(require_role(Role.OPERATOR))])
async def link_alert(
    incident_id: str,
    alert_id: str,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.link_alert(incident_id=incident_id, alert_id=alert_id, user=user)


@router.delete("/{incident_id}/alerts/{alert_id}", response_model=IncidentDetailResponse, dependencies=[Depends(require_role(Role.OPERATOR))])
async def unlink_alert(
    incident_id: str,
    alert_id: str,
    user: dict = Depends(get_current_user),
    service: IncidentService = Depends(get_service),
):
    return await service.unlink_alert(incident_id=incident_id, alert_id=alert_id, user=user)
