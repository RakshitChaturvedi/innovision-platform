from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

from shared.contracts.enums import CameraStatus

class OrganizationCreate(BaseModel):
    name: str
    code: str
    tier: str = "enterprise"
    is_active: bool = True

class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    code: str
    tier: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

class SiteCreate(BaseModel):
    organization_id: UUID
    name: str
    code: str
    address: Optional[str] = None
    timezone: str = "UTC"

class SiteResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    code: str
    address: Optional[str] = None
    timezone: str
    created_at: datetime
    updated_at: datetime

class ZoneCreate(BaseModel):
    site_id: Optional[UUID] = None
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    zone_type: str = "general"
    risk_level: str = "medium"
    is_active: bool = True

class ZoneResponse(BaseModel):
    id: UUID
    site_id: Optional[UUID] = None
    name: str
    slug: Optional[str] = None
    description: Optional[str] = None
    zone_type: str
    risk_level: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    organization_id: Optional[UUID] = None

class CameraCreate(BaseModel):
    name: str
    location: Optional[str] = None
    rtsp_url: str
    use_cases: list[str] = Field(default_factory=list)
    fps: int = Field(default=15, ge=1, le=60)
    organization_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    zone_id: Optional[UUID] = None
    lifecycle_state: str = "unassigned"
    source_type: str = "rtsp"
    source_url: Optional[str] = None
    is_simulation: bool = False

class CameraAssignZone(BaseModel):
    site_id: Optional[UUID] = None
    zone_id: Optional[UUID] = None
    lifecycle_state: Optional[str] = None

class CameraConfigUpdate(BaseModel):
    use_cases: Optional[list[str]] = None
    fps: Optional[int] = None
    organization_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    zone_id: Optional[UUID] = None
    lifecycle_state: Optional[str] = None

class CameraResponse(BaseModel):
    id: UUID
    name: str
    location: Optional[str] = None
    status: CameraStatus
    use_cases: list[str]
    fps: int
    created_at: datetime
    organization_id: Optional[UUID] = None
    site_id: Optional[UUID] = None
    zone_id: Optional[UUID] = None
    lifecycle_state: str = "unassigned"
    source_type: str = "rtsp"
    source_url: Optional[str] = None
    is_simulation: bool = False

class CameraStatusUpdate(BaseModel):
    status: CameraStatus

# --- Analytics Catalog & Subscriptions (Phase 2) ---
class AnalyticsCatalogResponse(BaseModel):
    id: UUID
    code: str
    internal_code: str
    display_name: str
    description: Optional[str] = None
    category: str
    icon_key: Optional[str] = None
    is_active: bool
    created_at: datetime

class OrganizationSubscriptionCreate(BaseModel):
    analytic_id: UUID
    is_enabled: bool = True
    max_cameras_allowed: int = Field(default=20, ge=0)
    valid_until: Optional[datetime] = None

class OrganizationSubscriptionUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    max_cameras_allowed: Optional[int] = Field(default=None, ge=0)
    valid_until: Optional[datetime] = None

class OrganizationSubscriptionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    analytic_id: UUID
    analytic_code: Optional[str] = None
    analytic_internal_code: Optional[str] = None
    analytic_display_name: Optional[str] = None
    is_enabled: bool
    max_cameras_allowed: int
    valid_until: Optional[datetime] = None
    status: str
    created_at: datetime

# --- Zone Analytics Policies & PPE Rules (Phase 3) ---
class ZoneAnalyticsPolicyItem(BaseModel):
    analytic_id: UUID
    internal_code: str
    code: str
    display_name: str
    category: str
    is_enabled: bool

class ZoneAnalyticsPolicyUpdate(BaseModel):
    is_enabled: bool

class ZoneAnalyticsPolicyBulkItem(BaseModel):
    analytic_id: UUID
    is_enabled: bool

class ZoneAnalyticsPolicyBulkUpdate(BaseModel):
    policies: list[ZoneAnalyticsPolicyBulkItem]

class ZonePPERuleItem(BaseModel):
    ppe_type: str
    required: bool = True
    severity: str = "high"
    grace_seconds: int = 0

class ZonePPERulesConfig(BaseModel):
    zone_id: Optional[UUID] = None
    ppe_rules: list[ZonePPERuleItem] = Field(default_factory=list)
    rules: Optional[list[ZonePPERuleItem]] = None
    min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)

# --- Camera Analytics Overrides & Effective Analytics (Phase 4) ---
class CameraAnalyticsOverrideItem(BaseModel):
    id: UUID
    camera_id: UUID
    analytic_id: UUID
    analytic_code: Optional[str] = None
    analytic_internal_code: Optional[str] = None
    analytic_display_name: Optional[str] = None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

class CameraAnalyticsOverrideUpdate(BaseModel):
    is_enabled: bool

class CameraEffectiveAnalyticItem(BaseModel):
    analytic_id: UUID
    internal_code: str
    code: str
    display_name: str
    is_active: bool
    source: str
    effective_config: Optional[dict] = None
    zone_policy_enabled: bool = False
    override_enabled: Optional[bool] = None
    subscription_active: bool = False

# --- Video Upload & Processing Sessions ---
class VideoSessionResponse(BaseModel):
    session_id: UUID
    camera_id: UUID
    organization_id: Optional[UUID] = None
    original_filename: str
    storage_path: str
    file_size_bytes: int
    status: str
    fps: float = 10.0
    total_frames: int = 0
    processed_frames: int = 0
    error_message: Optional[str] = None
    effective_analytics: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

class VideoSessionProcessResponse(BaseModel):
    session_id: UUID
    camera_id: UUID
    status: str
    message: str
    effective_analytics: list[str] = Field(default_factory=list)

class VideoSessionCreateRequest(BaseModel):
    filename: Optional[str] = None
