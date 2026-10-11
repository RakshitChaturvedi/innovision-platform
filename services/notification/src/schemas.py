from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class NotificationItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    organization_id: Optional[str] = None
    recipient_user_id: str
    type: str
    title: str
    message: str
    severity: str = "medium"
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_read: bool = False
    created_at: datetime
    read_at: Optional[datetime] = None


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total: int
    unread_count: int
    page: int
    page_size: int
    total_pages: int


class UnreadCountResponse(BaseModel):
    unread_count: int


class NotificationPreferenceItem(BaseModel):
    notification_type: str
    display_name: str
    description: str
    in_app_enabled: bool = True
    email_enabled: bool = True


class NotificationPreferenceUpdate(BaseModel):
    notification_type: str
    in_app_enabled: Optional[bool] = None
    email_enabled: Optional[bool] = None


class NotificationPreferenceBulkUpdate(BaseModel):
    preferences: list[NotificationPreferenceUpdate]
