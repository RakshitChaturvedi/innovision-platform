import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncGenerator

from services.auth.src.rbac import get_current_user, require_role, Role
from shared.platform_client.db import get_session_factory
from services.audit.src.config import settings
from services.audit.src.schemas import (
    AuditLogItem,
    AuditLogResponse,
    OrganizationSettings,
    OrganizationUpdate,
    SettingsResponse,
)
from services.audit.src.service import AuditService, SettingsService

router = APIRouter(prefix="/audit", tags=["audit"])
settings_router = APIRouter(prefix="/settings", tags=["settings"])

_database_url = settings.database_url or os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform"
)
_session_factory = get_session_factory(_database_url)


def get_audit_service() -> AuditService:
    return AuditService(_session_factory)


def get_settings_service() -> SettingsService:
    return SettingsService(_session_factory)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


# --- Audit Endpoints ---

@router.get("", response_model=AuditLogResponse, dependencies=[Depends(require_role(Role.ORG_ADMIN))])
async def list_audit(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    actor_user_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(get_current_user),
    service: AuditService = Depends(get_audit_service),
):
    return await service.list_audit_logs(
        user=user,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/{entry_id}", response_model=AuditLogItem, dependencies=[Depends(require_role(Role.ORG_ADMIN))])
async def get_audit_entry(
    entry_id: str,
    user: dict = Depends(get_current_user),
    service: AuditService = Depends(get_audit_service),
):
    return await service.get_audit_log(entry_id=entry_id, user=user)


# --- Settings Endpoints ---

@settings_router.get("", response_model=SettingsResponse, dependencies=[Depends(require_role(Role.ORG_ADMIN))])
async def get_settings(
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: SettingsService = Depends(get_settings_service),
):
    return await service.get_settings(user=user, target_org_id=organization_id)


@settings_router.get("/organization", response_model=OrganizationSettings, dependencies=[Depends(require_role(Role.ORG_ADMIN))])
async def get_organization_settings(
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: SettingsService = Depends(get_settings_service),
):
    res = await service.get_settings(user=user, target_org_id=organization_id)
    if not res.organization:
        raise HTTPException(status_code=404, detail="Organization settings not found")
    return res.organization


@settings_router.put("/organization", response_model=OrganizationSettings, dependencies=[Depends(require_role(Role.ORG_ADMIN))])
async def update_organization_settings(
    body: OrganizationUpdate,
    organization_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: SettingsService = Depends(get_settings_service),
):
    return await service.update_organization_settings(
        user=user,
        update_data=body,
        target_org_id=organization_id,
    )