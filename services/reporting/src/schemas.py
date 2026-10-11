from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class ExecutiveSummaryResponse(BaseModel):
    total_alerts: int
    critical_alerts: int
    high_alerts: int
    medium_alerts: int
    low_alerts: int

    total_incidents: int
    open_incidents: int
    investigating_incidents: int
    resolved_incidents: int
    closed_incidents: int

    active_cameras: int
    active_analytics: int

    resolved_today: int


class AlertAnalyticsItem(BaseModel):
    analytic_id: str
    internal_code: str
    display_name: str
    alert_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int


class AlertAnalyticsSummary(BaseModel):
    total_alerts: int
    critical: int
    high: int
    medium: int
    low: int


class AlertsReportResponse(BaseModel):
    summary: AlertAnalyticsSummary
    by_analytics: list[AlertAnalyticsItem]


class AlertTrendItem(BaseModel):
    date: str
    total: int
    critical: int
    high: int
    medium: int
    low: int


class IncidentResolutionMetrics(BaseModel):
    average_resolution_time: Optional[float] = None
    median_resolution_time: Optional[float] = None
    fastest_resolution_time: Optional[float] = None
    slowest_resolution_time: Optional[float] = None


class IncidentReportResponse(BaseModel):
    total_incidents: int
    open: int
    acknowledged: int
    investigating: int
    resolved: int
    closed: int
    critical: int
    high: int
    medium: int
    low: int
    resolution_performance: IncidentResolutionMetrics


class IncidentTrendItem(BaseModel):
    date: str
    created: int
    resolved: int
    open: int
    critical: int


class BreakdownItem(BaseModel):
    site_id: Optional[str] = None
    site_name: Optional[str] = None
    zone_id: Optional[str] = None
    zone_name: Optional[str] = None
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    analytic_id: Optional[str] = None
    internal_code: Optional[str] = None
    display_name: Optional[str] = None
    alert_count: int
    incident_count: int
    critical_alert_count: int
    open_incident_count: int


class AnalyticsPerformanceItem(BaseModel):
    analytic_id: str
    internal_code: str
    display_name: str
    is_active: bool
    alert_count: int
    incident_count: int
    critical_alert_count: int
