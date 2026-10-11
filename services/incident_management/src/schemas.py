from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class IncidentCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    severity: str = Field(default="medium")  # low, medium, high, critical
    organization_id: Optional[str] = None
    site_id: Optional[str] = None
    zone_id: Optional[str] = None
    camera_id: Optional[str] = None
    source_type: str = Field(default="alert")  # alert, manual
    assigned_to: Optional[str] = None
    alert_ids: Optional[List[str]] = Field(default_factory=list)

class IncidentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    site_id: Optional[str] = None
    zone_id: Optional[str] = None
    camera_id: Optional[str] = None
    assigned_to: Optional[str] = None

class IncidentStatusUpdate(BaseModel):
    status: str  # open, acknowledged, investigating, resolved, closed

class IncidentAssignUpdate(BaseModel):
    assigned_to: Optional[str] = None

class LinkedAlertItem(BaseModel):
    alert_id: str
    source_uc: Optional[str] = None
    title: Optional[str] = None
    severity: Optional[str] = None
    camera_id: Optional[str] = None
    timestamp: Optional[str] = None
    linked_at: Optional[str] = None

class IncidentResponse(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    organization_id: str
    organization_name: Optional[str] = None
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    source_type: str
    created_by: Optional[str] = None
    created_by_name: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_to_name: Optional[str] = None
    created_at: str
    updated_at: str
    acknowledged_at: Optional[str] = None
    investigating_at: Optional[str] = None
    resolved_at: Optional[str] = None
    closed_at: Optional[str] = None
    linked_alerts: Optional[List[LinkedAlertItem]] = Field(default_factory=list)

class IncidentDetailResponse(BaseModel):
    incident: IncidentResponse
    linked_alerts: List[LinkedAlertItem] = Field(default_factory=list)
    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    valid_next_states: List[str] = Field(default_factory=list)

class IncidentSummaryResponse(BaseModel):
    open_count: int = 0
    investigating_count: int = 0
    critical_count: int = 0
    resolved_today_count: int = 0
