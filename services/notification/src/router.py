import os
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncGenerator

from services.auth.src.rbac import get_current_user, require_role, Role
from shared.platform_client.db import get_session_factory
from services.notification.src.config import settings
from services.notification.src.schemas import (
    NotificationItem,
    NotificationListResponse,
    NotificationPreferenceBulkUpdate,
    NotificationPreferenceItem,
    UnreadCountResponse,
)
from services.notification.src.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])

_database_url = settings.database_url or os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform"
)
_session_factory = get_session_factory(_database_url)


def get_notification_service() -> NotificationService:
    return NotificationService(_session_factory)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


# --- Notification Listing & Status Endpoints ---

@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_read: Optional[bool] = Query(None),
    type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.list_notifications(
        user=user,
        page=page,
        page_size=page_size,
        is_read=is_read,
        type_filter=type,
        severity_filter=severity,
    )


@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.get_unread_count(user=user)


@router.put("/read-all", response_model=UnreadCountResponse)
async def mark_all_as_read(
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.mark_all_as_read(user=user)


@router.put("/{notification_id}/read", response_model=NotificationItem)
async def mark_as_read(
    notification_id: str,
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.mark_as_read(user=user, notification_id=notification_id)


# --- Notification Preferences Endpoints ---

@router.get("/preferences", response_model=list[NotificationPreferenceItem])
async def get_notification_preferences(
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.get_user_preferences(user=user)


@router.put("/preferences", response_model=list[NotificationPreferenceItem])
async def update_notification_preferences(
    body: NotificationPreferenceBulkUpdate,
    user: dict = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
):
    return await service.update_user_preferences(user=user, update_items=body.preferences)
