from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditLogItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

    id: str
    timestamp: datetime
    service: str
    action: str
    resource_type: str
    resource_id: str
    actor_user_id: Optional[str] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    actor_role: Optional[str] = None
    source_uc: Optional[str] = None
    organization_id: Optional[str] = None
    description: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogResponse(BaseModel):
    items: list[AuditLogItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class OrganizationSettings(BaseModel):
    id: str
    name: str
    code: str
    tier: str
    timezone: str
    is_active: bool
    created_at: datetime
    updated_at: datetime


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    timezone: Optional[str] = Field(None, min_length=1, max_length=100)


class SecuritySettings(BaseModel):
    auth_provider: str = "Enterprise JWT Authentication"
    session_duration: str = "24 Hours"
    supported_roles: list[str] = ["superadmin", "org_admin"]
    user_management_url: str = "/admin/users"


class PlatformSettings(BaseModel):
    platform_name: str = "Innovision Enterprise Safety Platform"
    version: str = "v2.4.0"
    environment: str = "Production"
    status: str = "healthy"
    services_count: int = 6


class SubscriptionSummaryItem(BaseModel):
    analytic_id: str
    name: str
    code: str
    status: str
    description: Optional[str] = None


class SettingsResponse(BaseModel):
    organization: Optional[OrganizationSettings] = None
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    platform: PlatformSettings = Field(default_factory=PlatformSettings)
    subscriptions: list[SubscriptionSummaryItem] = Field(default_factory=list)
