import logging
import statistics
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from services.auth.src.rbac import Role
from .schemas import (
    ExecutiveSummaryResponse,
    AlertsReportResponse,
    AlertAnalyticsSummary,
    AlertAnalyticsItem,
    AlertTrendItem,
    IncidentReportResponse,
    IncidentResolutionMetrics,
    IncidentTrendItem,
    BreakdownItem,
    AnalyticsPerformanceItem,
)

logger = logging.getLogger(__name__)


class ReportingService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def _resolve_org_id(self, user: dict, requested_org_id: Optional[str] = None) -> Optional[str]:
        user_role = user.get("role")
        user_org = user.get("org_id") or user.get("organization_id")

        if user_role != Role.SUPERADMIN:
            if not user_org:
                raise HTTPException(status_code=403, detail="User has no assigned organization")
            if requested_org_id and str(requested_org_id) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
            return str(user_org)

        return str(requested_org_id) if requested_org_id else None

    def _parse_dates(self, start_date: Optional[str | datetime], end_date: Optional[str | datetime]) -> tuple[Optional[datetime], Optional[datetime]]:
        s_dt = None
        e_dt = None

        if isinstance(start_date, str) and start_date:
            try:
                s_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO format.")
        elif isinstance(start_date, datetime):
            s_dt = start_date

        if isinstance(end_date, str) and end_date:
            try:
                e_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO format.")
        elif isinstance(end_date, datetime):
            e_dt = end_date

        if s_dt and e_dt and s_dt > e_dt:
            raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")

        return s_dt, e_dt

    async def _resolve_analytic_code(self, session: AsyncSession, analytic_id: Optional[str]) -> Optional[str]:
        if not analytic_id:
            return None
        row = await session.execute(text("""
            SELECT internal_code, code FROM analytics_catalog
            WHERE id::text = :aid OR internal_code = :aid OR code = :aid
        """), {"aid": str(analytic_id)})
        r = row.fetchone()
        if r:
            return r.internal_code
        return analytic_id

    # --- 1. Executive Summary ---
    async def get_executive_summary(
        self,
        user: dict,
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
        site_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        analytic_id: Optional[str] = None,
    ) -> dict:
        org_id = self._resolve_org_id(user, organization_id)
        s_dt, e_dt = self._parse_dates(start_date, end_date)

        async with self._session_factory() as session:
            analytic_code = await self._resolve_analytic_code(session, analytic_id)

            # Alert counts
            alert_where = []
            alert_params: dict[str, Any] = {}

            if org_id:
                alert_where.append("c.organization_id = :org_id")
                alert_params["org_id"] = org_id
            if site_id:
                alert_where.append("c.site_id = :site_id")
                alert_params["site_id"] = site_id
            if camera_id:
                alert_where.append("a.camera_id = :camera_id")
                alert_params["camera_id"] = camera_id
            if analytic_code:
                alert_where.append("a.source_uc::text = :analytic_code")
                alert_params["analytic_code"] = analytic_code
            if s_dt:
                alert_where.append("a.created_at >= :start_date")
                alert_params["start_date"] = s_dt
            if e_dt:
                alert_where.append("a.created_at <= :end_date")
                alert_params["end_date"] = e_dt

            a_sql_where = f"WHERE {' AND '.join(alert_where)}" if alert_where else ""

            alerts_row = await session.execute(text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical,
                    COUNT(CASE WHEN a.severity = 'high' THEN 1 END) AS high,
                    COUNT(CASE WHEN a.severity = 'medium' THEN 1 END) AS medium,
                    COUNT(CASE WHEN a.severity = 'low' THEN 1 END) AS low
                FROM alerts a
                LEFT JOIN cameras c ON a.camera_id = c.id
                {a_sql_where}
            """), alert_params)
            ar = alerts_row.fetchone()

            # Incident counts
            inc_where = []
            inc_params: dict[str, Any] = {}

            if org_id:
                inc_where.append("i.organization_id = :org_id")
                inc_params["org_id"] = org_id
            if site_id:
                inc_where.append("i.site_id = :site_id")
                inc_params["site_id"] = site_id
            if zone_id:
                inc_where.append("i.zone_id = :zone_id")
                inc_params["zone_id"] = zone_id
            if camera_id:
                inc_where.append("i.camera_id = :camera_id")
                inc_params["camera_id"] = camera_id
            if s_dt:
                inc_where.append("i.created_at >= :start_date")
                inc_params["start_date"] = s_dt
            if e_dt:
                inc_where.append("i.created_at <= :end_date")
                inc_params["end_date"] = e_dt

            i_sql_where = f"WHERE {' AND '.join(inc_where)}" if inc_where else ""

            inc_row = await session.execute(text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN i.status IN ('open', 'active') THEN 1 END) AS open_cnt,
                    COUNT(CASE WHEN i.status = 'investigating' THEN 1 END) AS investigating_cnt,
                    COUNT(CASE WHEN i.status = 'resolved' THEN 1 END) AS resolved_cnt,
                    COUNT(CASE WHEN i.status = 'closed' THEN 1 END) AS closed_cnt,
                    COUNT(CASE WHEN i.status = 'resolved' AND i.resolved_at >= DATE_TRUNC('day', now()) THEN 1 END) AS resolved_today_cnt
                FROM incidents i
                {i_sql_where}
            """), inc_params)
            ir = inc_row.fetchone()

            # Active cameras
            cam_where = ["c.status = 'online'"]
            cam_params: dict[str, Any] = {}
            if org_id:
                cam_where.append("c.organization_id = :org_id")
                cam_params["org_id"] = org_id
            if site_id:
                cam_where.append("c.site_id = :site_id")
                cam_params["site_id"] = site_id

            c_row = await session.execute(text(f"""
                SELECT COUNT(*) FROM cameras c WHERE {' AND '.join(cam_where)}
            """), cam_params)
            active_cams = c_row.scalar() or 0

            # Active analytics
            sub_params: dict[str, Any] = {}
            sub_where = ["s.is_enabled = true"]
            if org_id:
                sub_where.append("s.organization_id = :org_id")
                sub_params["org_id"] = org_id

            sub_row = await session.execute(text(f"""
                SELECT COUNT(DISTINCT s.analytic_id)
                FROM organization_subscriptions s
                WHERE {' AND '.join(sub_where)}
            """), sub_params)
            active_analytics = sub_row.scalar() or 0
            if active_analytics == 0 and not org_id:
                # default fallback count from catalog if no specific org sub query
                cat_row = await session.execute(text("SELECT COUNT(*) FROM analytics_catalog WHERE is_active = true"))
                active_analytics = cat_row.scalar() or 0

            return {
                "total_alerts": ar.total or 0 if ar else 0,
                "critical_alerts": ar.critical or 0 if ar else 0,
                "high_alerts": ar.high or 0 if ar else 0,
                "medium_alerts": ar.medium or 0 if ar else 0,
                "low_alerts": ar.low or 0 if ar else 0,
                "total_incidents": ir.total or 0 if ir else 0,
                "open_incidents": ir.open_cnt or 0 if ir else 0,
                "investigating_incidents": ir.investigating_cnt or 0 if ir else 0,
                "resolved_incidents": ir.resolved_cnt or 0 if ir else 0,
                "closed_incidents": ir.closed_cnt or 0 if ir else 0,
                "active_cameras": active_cams,
                "active_analytics": active_analytics,
                "resolved_today": ir.resolved_today_cnt or 0 if ir else 0,
            }

    # --- 2. Alert Analytics Report ---
    async def get_alerts_report(
        self,
        user: dict,
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
        site_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        analytic_id: Optional[str] = None,
        severity: Optional[str] = None,
    ) -> dict:
        org_id = self._resolve_org_id(user, organization_id)
        s_dt, e_dt = self._parse_dates(start_date, end_date)

        async with self._session_factory() as session:
            analytic_code = await self._resolve_analytic_code(session, analytic_id)

            alert_where = []
            alert_params: dict[str, Any] = {}

            if org_id:
                alert_where.append("c.organization_id = :org_id")
                alert_params["org_id"] = org_id
            if site_id:
                alert_where.append("c.site_id = :site_id")
                alert_params["site_id"] = site_id
            if camera_id:
                alert_where.append("a.camera_id = :camera_id")
                alert_params["camera_id"] = camera_id
            if analytic_code:
                alert_where.append("a.source_uc::text = :analytic_code")
                alert_params["analytic_code"] = analytic_code
            if severity:
                alert_where.append("a.severity::text = :severity")
                alert_params["severity"] = severity
            if s_dt:
                alert_where.append("a.created_at >= :start_date")
                alert_params["start_date"] = s_dt
            if e_dt:
                alert_where.append("a.created_at <= :end_date")
                alert_params["end_date"] = e_dt

            a_sql_where = f"WHERE {' AND '.join(alert_where)}" if alert_where else ""

            # Total summary
            summary_row = await session.execute(text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical,
                    COUNT(CASE WHEN a.severity = 'high' THEN 1 END) AS high,
                    COUNT(CASE WHEN a.severity = 'medium' THEN 1 END) AS medium,
                    COUNT(CASE WHEN a.severity = 'low' THEN 1 END) AS low
                FROM alerts a
                LEFT JOIN cameras c ON a.camera_id = c.id
                {a_sql_where}
            """), alert_params)
            sr = summary_row.fetchone()

            # Group by Analytics Catalog
            by_analytics_rows = await session.execute(text(f"""
                SELECT
                    cat.id AS analytic_id,
                    cat.internal_code,
                    cat.display_name,
                    COUNT(a.id) AS alert_count,
                    COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical_count,
                    COUNT(CASE WHEN a.severity = 'high' THEN 1 END) AS high_count,
                    COUNT(CASE WHEN a.severity = 'medium' THEN 1 END) AS medium_count,
                    COUNT(CASE WHEN a.severity = 'low' THEN 1 END) AS low_count
                FROM analytics_catalog cat
                LEFT JOIN alerts a ON (a.source_uc::text = cat.internal_code OR a.source_uc::text = cat.code)
                LEFT JOIN cameras c ON a.camera_id = c.id
                {a_sql_where}
                GROUP BY cat.id, cat.internal_code, cat.display_name
                ORDER BY cat.internal_code
            """), alert_params)

            by_analytics = [
                {
                    "analytic_id": str(r.analytic_id),
                    "internal_code": r.internal_code,
                    "display_name": r.display_name,
                    "alert_count": r.alert_count or 0,
                    "critical_count": r.critical_count or 0,
                    "high_count": r.high_count or 0,
                    "medium_count": r.medium_count or 0,
                    "low_count": r.low_count or 0,
                }
                for r in by_analytics_rows.fetchall()
            ]

            return {
                "summary": {
                    "total_alerts": sr.total or 0 if sr else 0,
                    "critical": sr.critical or 0 if sr else 0,
                    "high": sr.high or 0 if sr else 0,
                    "medium": sr.medium or 0 if sr else 0,
                    "low": sr.low or 0 if sr else 0,
                },
                "by_analytics": by_analytics,
            }

    # --- 3. Alert Trend Report ---
    async def get_alerts_trend(
        self,
        user: dict,
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
        site_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        analytic_id: Optional[str] = None,
        severity: Optional[str] = None,
        bucket: Optional[str] = None,
    ) -> list[dict]:
        org_id = self._resolve_org_id(user, organization_id)
        s_dt, e_dt = self._parse_dates(start_date, end_date)

        # Default bucket based on date range duration
        trunc_unit = "day"
        if bucket == "hourly":
            trunc_unit = "hour"
        elif bucket == "weekly":
            trunc_unit = "week"
        elif bucket == "daily":
            trunc_unit = "day"
        elif s_dt and e_dt:
            diff_days = (e_dt - s_dt).days
            if diff_days <= 2:
                trunc_unit = "hour"
            elif diff_days > 60:
                trunc_unit = "week"

        async with self._session_factory() as session:
            analytic_code = await self._resolve_analytic_code(session, analytic_id)

            alert_where = []
            alert_params: dict[str, Any] = {}

            if org_id:
                alert_where.append("c.organization_id = :org_id")
                alert_params["org_id"] = org_id
            if site_id:
                alert_where.append("c.site_id = :site_id")
                alert_params["site_id"] = site_id
            if camera_id:
                alert_where.append("a.camera_id = :camera_id")
                alert_params["camera_id"] = camera_id
            if analytic_code:
                alert_where.append("a.source_uc::text = :analytic_code")
                alert_params["analytic_code"] = analytic_code
            if severity:
                alert_where.append("a.severity::text = :severity")
                alert_params["severity"] = severity
            if s_dt:
                alert_where.append("a.created_at >= :start_date")
                alert_params["start_date"] = s_dt
            if e_dt:
                alert_where.append("a.created_at <= :end_date")
                alert_params["end_date"] = e_dt

            a_sql_where = f"WHERE {' AND '.join(alert_where)}" if alert_where else ""

            trend_rows = await session.execute(text(f"""
                SELECT
                    DATE_TRUNC('{trunc_unit}', a.created_at) AS bucket_date,
                    COUNT(*) AS total,
                    COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical,
                    COUNT(CASE WHEN a.severity = 'high' THEN 1 END) AS high,
                    COUNT(CASE WHEN a.severity = 'medium' THEN 1 END) AS medium,
                    COUNT(CASE WHEN a.severity = 'low' THEN 1 END) AS low
                FROM alerts a
                LEFT JOIN cameras c ON a.camera_id = c.id
                {a_sql_where}
                GROUP BY bucket_date
                ORDER BY bucket_date ASC
            """), alert_params)

            results = []
            for r in trend_rows.fetchall():
                d_str = r.bucket_date.isoformat() if r.bucket_date else ""
                results.append({
                    "date": d_str,
                    "total": r.total or 0,
                    "critical": r.critical or 0,
                    "high": r.high or 0,
                    "medium": r.medium or 0,
                    "low": r.low or 0,
                })
            return results

    # --- 4. Incident Report ---
    async def get_incidents_report(
        self,
        user: dict,
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
        site_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        assigned_to: Optional[str] = None,
    ) -> dict:
        org_id = self._resolve_org_id(user, organization_id)
        s_dt, e_dt = self._parse_dates(start_date, end_date)

        async with self._session_factory() as session:
            inc_where = []
            inc_params: dict[str, Any] = {}

            if org_id:
                inc_where.append("i.organization_id = :org_id")
                inc_params["org_id"] = org_id
            if site_id:
                inc_where.append("i.site_id = :site_id")
                inc_params["site_id"] = site_id
            if zone_id:
                inc_where.append("i.zone_id = :zone_id")
                inc_params["zone_id"] = zone_id
            if camera_id:
                inc_where.append("i.camera_id = :camera_id")
                inc_params["camera_id"] = camera_id
            if severity:
                inc_where.append("i.severity = :severity")
                inc_params["severity"] = severity
            if status:
                inc_where.append("i.status = :status")
                inc_params["status"] = status
            if assigned_to:
                inc_where.append("i.assigned_to = :assigned_to")
                inc_params["assigned_to"] = assigned_to
            if s_dt:
                inc_where.append("i.created_at >= :start_date")
                inc_params["start_date"] = s_dt
            if e_dt:
                inc_where.append("i.created_at <= :end_date")
                inc_params["end_date"] = e_dt

            i_sql_where = f"WHERE {' AND '.join(inc_where)}" if inc_where else ""

            counts_row = await session.execute(text(f"""
                SELECT
                    COUNT(*) AS total,
                    COUNT(CASE WHEN i.status IN ('open', 'active') THEN 1 END) AS open_cnt,
                    COUNT(CASE WHEN i.status = 'acknowledged' THEN 1 END) AS ack_cnt,
                    COUNT(CASE WHEN i.status = 'investigating' THEN 1 END) AS inv_cnt,
                    COUNT(CASE WHEN i.status = 'resolved' THEN 1 END) AS res_cnt,
                    COUNT(CASE WHEN i.status = 'closed' THEN 1 END) AS cls_cnt,
                    COUNT(CASE WHEN i.severity = 'critical' THEN 1 END) AS critical_cnt,
                    COUNT(CASE WHEN i.severity = 'high' THEN 1 END) AS high_cnt,
                    COUNT(CASE WHEN i.severity = 'medium' THEN 1 END) AS medium_cnt,
                    COUNT(CASE WHEN i.severity = 'low' THEN 1 END) AS low_cnt
                FROM incidents i
                {i_sql_where}
            """), inc_params)
            cr = counts_row.fetchone()

            # Calculate resolution metrics from resolved incidents
            res_where = list(inc_where)
            res_where.append("i.status = 'resolved'")
            res_where.append("i.resolved_at IS NOT NULL")
            res_where.append("i.created_at IS NOT NULL")

            res_sql_where = f"WHERE {' AND '.join(res_where)}"

            res_time_rows = await session.execute(text(f"""
                SELECT i.created_at, i.resolved_at
                FROM incidents i
                {res_sql_where}
            """), inc_params)

            durations_minutes = []
            for r in res_time_rows.fetchall():
                if r.created_at and r.resolved_at and r.resolved_at >= r.created_at:
                    dur = (r.resolved_at - r.created_at).total_seconds() / 60.0
                    durations_minutes.append(dur)

            avg_res = round(statistics.mean(durations_minutes), 2) if durations_minutes else None
            med_res = round(statistics.median(durations_minutes), 2) if durations_minutes else None
            fast_res = round(min(durations_minutes), 2) if durations_minutes else None
            slow_res = round(max(durations_minutes), 2) if durations_minutes else None

            return {
                "total_incidents": cr.total or 0 if cr else 0,
                "open": cr.open_cnt or 0 if cr else 0,
                "acknowledged": cr.ack_cnt or 0 if cr else 0,
                "investigating": cr.inv_cnt or 0 if cr else 0,
                "resolved": cr.res_cnt or 0 if cr else 0,
                "closed": cr.cls_cnt or 0 if cr else 0,
                "critical": cr.critical_cnt or 0 if cr else 0,
                "high": cr.high_cnt or 0 if cr else 0,
                "medium": cr.medium_cnt or 0 if cr else 0,
                "low": cr.low_cnt or 0 if cr else 0,
                "resolution_performance": {
                    "average_resolution_time": avg_res,
                    "median_resolution_time": med_res,
                    "fastest_resolution_time": fast_res,
                    "slowest_resolution_time": slow_res,
                },
            }

    # --- 5. Incident Trend ---
    async def get_incidents_trend(
        self,
        user: dict,
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
        site_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        severity: Optional[str] = None,
        bucket: Optional[str] = None,
    ) -> list[dict]:
        org_id = self._resolve_org_id(user, organization_id)
        s_dt, e_dt = self._parse_dates(start_date, end_date)

        trunc_unit = "day"
        if bucket == "hourly":
            trunc_unit = "hour"
        elif bucket == "weekly":
            trunc_unit = "week"
        elif bucket == "daily":
            trunc_unit = "day"

        async with self._session_factory() as session:
            inc_where = []
            inc_params: dict[str, Any] = {}

            if org_id:
                inc_where.append("i.organization_id = :org_id")
                inc_params["org_id"] = org_id
            if site_id:
                inc_where.append("i.site_id = :site_id")
                inc_params["site_id"] = site_id
            if zone_id:
                inc_where.append("i.zone_id = :zone_id")
                inc_params["zone_id"] = zone_id
            if camera_id:
                inc_where.append("i.camera_id = :camera_id")
                inc_params["camera_id"] = camera_id
            if severity:
                inc_where.append("i.severity = :severity")
                inc_params["severity"] = severity
            if s_dt:
                inc_where.append("i.created_at >= :start_date")
                inc_params["start_date"] = s_dt
            if e_dt:
                inc_where.append("i.created_at <= :end_date")
                inc_params["end_date"] = e_dt

            i_sql_where = f"WHERE {' AND '.join(inc_where)}" if inc_where else ""

            trend_rows = await session.execute(text(f"""
                SELECT
                    DATE_TRUNC('{trunc_unit}', i.created_at) AS bucket_date,
                    COUNT(*) AS created,
                    COUNT(CASE WHEN i.status = 'resolved' THEN 1 END) AS resolved,
                    COUNT(CASE WHEN i.status IN ('open', 'active', 'acknowledged', 'investigating') THEN 1 END) AS open,
                    COUNT(CASE WHEN i.severity = 'critical' THEN 1 END) AS critical
                FROM incidents i
                {i_sql_where}
                GROUP BY bucket_date
                ORDER BY bucket_date ASC
            """), inc_params)

            results = []
            for r in trend_rows.fetchall():
                d_str = r.bucket_date.isoformat() if r.bucket_date else ""
                results.append({
                    "date": d_str,
                    "created": r.created or 0,
                    "resolved": r.resolved or 0,
                    "open": r.open or 0,
                    "critical": r.critical or 0,
                })
            return results

    # --- 6. Location / Asset Breakdown ---
    async def get_location_breakdown(
        self,
        user: dict,
        group_by: str = "site",
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
        site_id: Optional[str] = None,
        zone_id: Optional[str] = None,
    ) -> list[dict]:
        org_id = self._resolve_org_id(user, organization_id)
        s_dt, e_dt = self._parse_dates(start_date, end_date)

        group_by = (group_by or "site").lower()
        if group_by not in ("site", "zone", "camera", "analytic"):
            raise HTTPException(status_code=400, detail="group_by must be one of: site, zone, camera, analytic")

        async with self._session_factory() as session:
            # Build filters
            params: dict[str, Any] = {}
            a_where = []
            i_where = []

            if org_id:
                params["org_id"] = org_id
                a_where.append("c.organization_id = :org_id")
                i_where.append("i.organization_id = :org_id")
            if site_id:
                params["site_id"] = site_id
                a_where.append("c.site_id = :site_id")
                i_where.append("i.site_id = :site_id")
            if zone_id:
                params["zone_id"] = zone_id
                i_where.append("i.zone_id = :zone_id")
            if s_dt:
                params["start_date"] = s_dt
                a_where.append("a.created_at >= :start_date")
                i_where.append("i.created_at >= :start_date")
            if e_dt:
                params["end_date"] = e_dt
                a_where.append("a.created_at <= :end_date")
                i_where.append("i.created_at <= :end_date")

            a_cond = f"WHERE {' AND '.join(a_where)}" if a_where else ""
            i_cond = f"WHERE {' AND '.join(i_where)}" if i_where else ""

            if group_by == "site":
                sql = f"""
                    WITH site_alerts AS (
                        SELECT c.site_id,
                               COUNT(a.id) AS alert_count,
                               COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical_alert_count
                        FROM alerts a
                        JOIN cameras c ON a.camera_id = c.id
                        {a_cond}
                        GROUP BY c.site_id
                    ), site_incidents AS (
                        SELECT i.site_id,
                               COUNT(i.id) AS incident_count,
                               COUNT(CASE WHEN i.status IN ('open', 'active', 'investigating', 'acknowledged') THEN 1 END) AS open_incident_count
                        FROM incidents i
                        {i_cond}
                        GROUP BY i.site_id
                    )
                    SELECT
                        s.id AS site_id,
                        s.name AS site_name,
                        COALESCE(sa.alert_count, 0) AS alert_count,
                        COALESCE(si.incident_count, 0) AS incident_count,
                        COALESCE(sa.critical_alert_count, 0) AS critical_alert_count,
                        COALESCE(si.open_incident_count, 0) AS open_incident_count
                    FROM sites s
                    LEFT JOIN site_alerts sa ON s.id = sa.site_id
                    LEFT JOIN site_incidents si ON s.id = si.site_id
                    WHERE (:org_id IS NULL OR s.organization_id = :org_id)
                    ORDER BY alert_count DESC, incident_count DESC
                """
                rows = await session.execute(text(sql), {"org_id": org_id, **params})
                return [
                    {
                        "site_id": str(r.site_id),
                        "site_name": r.site_name,
                        "alert_count": r.alert_count,
                        "incident_count": r.incident_count,
                        "critical_alert_count": r.critical_alert_count,
                        "open_incident_count": r.open_incident_count,
                    }
                    for r in rows.fetchall()
                ]

            elif group_by == "zone":
                sql = f"""
                    WITH zone_incidents AS (
                        SELECT i.zone_id,
                               COUNT(i.id) AS incident_count,
                               COUNT(CASE WHEN i.status IN ('open', 'active', 'investigating', 'acknowledged') THEN 1 END) AS open_incident_count
                        FROM incidents i
                        {i_cond}
                        GROUP BY i.zone_id
                    ), zone_alerts AS (
                        SELECT c.site_id,
                               COUNT(a.id) AS alert_count,
                               COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical_alert_count
                        FROM alerts a
                        JOIN cameras c ON a.camera_id = c.id
                        {a_cond}
                        GROUP BY c.site_id
                    )
                    SELECT
                        z.id AS zone_id,
                        z.name AS zone_name,
                        s.name AS site_name,
                        COALESCE(za.alert_count, 0) AS alert_count,
                        COALESCE(zi.incident_count, 0) AS incident_count,
                        COALESCE(za.critical_alert_count, 0) AS critical_alert_count,
                        COALESCE(zi.open_incident_count, 0) AS open_incident_count
                    FROM zones z
                    LEFT JOIN sites s ON z.site_id = s.id
                    LEFT JOIN zone_incidents zi ON z.id = zi.zone_id
                    LEFT JOIN zone_alerts za ON z.site_id = za.site_id
                    WHERE (:org_id IS NULL OR s.organization_id = :org_id)
                    ORDER BY alert_count DESC, incident_count DESC
                """
                rows = await session.execute(text(sql), {"org_id": org_id, **params})
                return [
                    {
                        "zone_id": str(r.zone_id),
                        "zone_name": r.zone_name,
                        "site_name": r.site_name,
                        "alert_count": r.alert_count,
                        "incident_count": r.incident_count,
                        "critical_alert_count": r.critical_alert_count,
                        "open_incident_count": r.open_incident_count,
                    }
                    for r in rows.fetchall()
                ]

            elif group_by == "camera":
                sql = f"""
                    WITH cam_alerts AS (
                        SELECT a.camera_id,
                               COUNT(a.id) AS alert_count,
                               COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical_alert_count
                        FROM alerts a
                        JOIN cameras c ON a.camera_id = c.id
                        {a_cond}
                        GROUP BY a.camera_id
                    ), cam_incidents AS (
                        SELECT i.camera_id,
                               COUNT(i.id) AS incident_count,
                               COUNT(CASE WHEN i.status IN ('open', 'active', 'investigating', 'acknowledged') THEN 1 END) AS open_incident_count
                        FROM incidents i
                        {i_cond}
                        GROUP BY i.camera_id
                    )
                    SELECT
                        c.id AS camera_id,
                        c.name AS camera_name,
                        s.name AS site_name,
                        COALESCE(ca.alert_count, 0) AS alert_count,
                        COALESCE(ci.incident_count, 0) AS incident_count,
                        COALESCE(ca.critical_alert_count, 0) AS critical_alert_count,
                        COALESCE(ci.open_incident_count, 0) AS open_incident_count
                    FROM cameras c
                    LEFT JOIN sites s ON c.site_id = s.id
                    LEFT JOIN cam_alerts ca ON c.id = ca.camera_id
                    LEFT JOIN cam_incidents ci ON c.id = ci.camera_id
                    WHERE (:org_id IS NULL OR c.organization_id = :org_id)
                    ORDER BY alert_count DESC, incident_count DESC
                """
                rows = await session.execute(text(sql), {"org_id": org_id, **params})
                return [
                    {
                        "camera_id": str(r.camera_id),
                        "camera_name": r.camera_name,
                        "site_name": r.site_name,
                        "alert_count": r.alert_count,
                        "incident_count": r.incident_count,
                        "critical_alert_count": r.critical_alert_count,
                        "open_incident_count": r.open_incident_count,
                    }
                    for r in rows.fetchall()
                ]

            else:  # analytic
                sql = f"""
                    WITH cat_alerts AS (
                        SELECT cat.id AS analytic_id,
                               COUNT(a.id) AS alert_count,
                               COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical_alert_count
                        FROM analytics_catalog cat
                        LEFT JOIN alerts a ON (a.source_uc::text = cat.internal_code OR a.source_uc::text = cat.code)
                        LEFT JOIN cameras c ON a.camera_id = c.id
                        {a_cond}
                        GROUP BY cat.id
                    ), cat_incidents AS (
                        SELECT cat.id AS analytic_id,
                               COUNT(i.id) AS incident_count,
                               COUNT(CASE WHEN i.status IN ('open', 'active', 'investigating', 'acknowledged') THEN 1 END) AS open_incident_count
                        FROM analytics_catalog cat
                        LEFT JOIN alerts a ON (a.source_uc::text = cat.internal_code OR a.source_uc::text = cat.code)
                        LEFT JOIN incident_alerts ia ON ia.alert_id = a.id
                        LEFT JOIN incidents i ON ia.incident_id = i.id
                        {i_cond}
                        GROUP BY cat.id
                    )
                    SELECT
                        cat.id AS analytic_id,
                        cat.internal_code,
                        cat.display_name,
                        COALESCE(ca.alert_count, 0) AS alert_count,
                        COALESCE(ci.incident_count, 0) AS incident_count,
                        COALESCE(ca.critical_alert_count, 0) AS critical_alert_count,
                        COALESCE(ci.open_incident_count, 0) AS open_incident_count
                    FROM analytics_catalog cat
                    LEFT JOIN cat_alerts ca ON cat.id = ca.analytic_id
                    LEFT JOIN cat_incidents ci ON cat.id = ci.analytic_id
                    ORDER BY alert_count DESC, incident_count DESC
                """
                rows = await session.execute(text(sql), {"org_id": org_id, **params})
                return [
                    {
                        "analytic_id": str(r.analytic_id),
                        "internal_code": r.internal_code,
                        "display_name": r.display_name,
                        "alert_count": r.alert_count,
                        "incident_count": r.incident_count,
                        "critical_alert_count": r.critical_alert_count,
                        "open_incident_count": r.open_incident_count,
                    }
                    for r in rows.fetchall()
                ]

    # --- 7. Analytics Performance Report ---
    async def get_analytics_performance(
        self,
        user: dict,
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
    ) -> list[dict]:
        org_id = self._resolve_org_id(user, organization_id)
        s_dt, e_dt = self._parse_dates(start_date, end_date)

        async with self._session_factory() as session:
            params: dict[str, Any] = {}
            a_where = []
            i_where = []

            if org_id:
                params["org_id"] = org_id
                a_where.append("c.organization_id = :org_id")
                i_where.append("i.organization_id = :org_id")
            if s_dt:
                params["start_date"] = s_dt
                a_where.append("a.created_at >= :start_date")
                i_where.append("i.created_at >= :start_date")
            if e_dt:
                params["end_date"] = e_dt
                a_where.append("a.created_at <= :end_date")
                i_where.append("i.created_at <= :end_date")

            a_cond = f"WHERE {' AND '.join(a_where)}" if a_where else ""
            i_cond = f"WHERE {' AND '.join(i_where)}" if i_where else ""

            sql = f"""
                WITH cat_alerts AS (
                    SELECT cat.id AS analytic_id,
                           COUNT(a.id) AS alert_count,
                           COUNT(CASE WHEN a.severity = 'critical' THEN 1 END) AS critical_alert_count
                    FROM analytics_catalog cat
                    LEFT JOIN alerts a ON (a.source_uc::text = cat.internal_code OR a.source_uc::text = cat.code)
                    LEFT JOIN cameras c ON a.camera_id = c.id
                    {a_cond}
                    GROUP BY cat.id
                ), cat_incidents AS (
                    SELECT cat.id AS analytic_id,
                           COUNT(i.id) AS incident_count
                    FROM analytics_catalog cat
                    LEFT JOIN alerts a ON (a.source_uc::text = cat.internal_code OR a.source_uc::text = cat.code)
                    LEFT JOIN incident_alerts ia ON ia.alert_id = a.id
                    LEFT JOIN incidents i ON ia.incident_id = i.id
                    {i_cond}
                    GROUP BY cat.id
                ), org_subs AS (
                    SELECT analytic_id, is_enabled
                    FROM organization_subscriptions
                    WHERE (:org_id IS NULL OR organization_id = :org_id)
                )
                SELECT
                    cat.id AS analytic_id,
                    cat.internal_code,
                    cat.display_name,
                    cat.is_active AS catalog_active,
                    COALESCE(os.is_enabled, cat.is_active) AS is_active,
                    COALESCE(ca.alert_count, 0) AS alert_count,
                    COALESCE(ci.incident_count, 0) AS incident_count,
                    COALESCE(ca.critical_alert_count, 0) AS critical_alert_count
                FROM analytics_catalog cat
                LEFT JOIN cat_alerts ca ON cat.id = ca.analytic_id
                LEFT JOIN cat_incidents ci ON cat.id = ci.analytic_id
                LEFT JOIN org_subs os ON cat.id = os.analytic_id
                ORDER BY cat.internal_code ASC
            """
            rows = await session.execute(text(sql), {"org_id": org_id, **params})
            return [
                {
                    "analytic_id": str(r.analytic_id),
                    "internal_code": r.internal_code,
                    "display_name": r.display_name,
                    "is_active": bool(r.is_active),
                    "alert_count": r.alert_count,
                    "incident_count": r.incident_count,
                    "critical_alert_count": r.critical_alert_count,
                }
                for r in rows.fetchall()
            ]

    # --- 8. Export CSV ---
    async def export_report_csv(
        self,
        user: dict,
        report_type: str,
        start_date: Optional[str | datetime] = None,
        end_date: Optional[str | datetime] = None,
        organization_id: Optional[str] = None,
        site_id: Optional[str] = None,
        zone_id: Optional[str] = None,
        camera_id: Optional[str] = None,
        analytic_id: Optional[str] = None,
        severity: Optional[str] = None,
        group_by: str = "site",
    ) -> str:
        report_type = report_type.lower()
        output = io.StringIO()
        writer = csv.writer(output)

        if report_type == "summary":
            data = await self.get_executive_summary(
                user, start_date=start_date, end_date=end_date,
                organization_id=organization_id, site_id=site_id,
                zone_id=zone_id, camera_id=camera_id, analytic_id=analytic_id
            )
            writer.writerow(["Metric", "Value"])
            for k, v in data.items():
                writer.writerow([k, v])

        elif report_type in ("alerts", "alert"):
            data = await self.get_alerts_report(
                user, start_date=start_date, end_date=end_date,
                organization_id=organization_id, site_id=site_id,
                zone_id=zone_id, camera_id=camera_id, analytic_id=analytic_id,
                severity=severity
            )
            writer.writerow(["Analytic ID", "Internal Code", "Display Name", "Alert Count", "Critical", "High", "Medium", "Low"])
            for item in data.get("by_analytics", []):
                writer.writerow([
                    item["analytic_id"], item["internal_code"], item["display_name"],
                    item["alert_count"], item["critical_count"], item["high_count"],
                    item["medium_count"], item["low_count"]
                ])

        elif report_type in ("incidents", "incident"):
            data = await self.get_incidents_report(
                user, start_date=start_date, end_date=end_date,
                organization_id=organization_id, site_id=site_id,
                zone_id=zone_id, camera_id=camera_id, severity=severity
            )
            writer.writerow(["Metric", "Value"])
            for k, v in data.items():
                if k == "resolution_performance" and isinstance(v, dict):
                    for rk, rv in v.items():
                        writer.writerow([f"resolution_{rk}", rv if rv is not None else "N/A"])
                else:
                    writer.writerow([k, v])

        elif report_type == "breakdown":
            data = await self.get_location_breakdown(
                user, group_by=group_by, start_date=start_date, end_date=end_date,
                organization_id=organization_id, site_id=site_id, zone_id=zone_id
            )
            if data:
                headers = list(data[0].keys())
                writer.writerow(headers)
                for item in data:
                    writer.writerow([item.get(h, "") for h in headers])
            else:
                writer.writerow(["No data"])

        elif report_type in ("analytics", "analytics_performance"):
            data = await self.get_analytics_performance(
                user, start_date=start_date, end_date=end_date,
                organization_id=organization_id
            )
            writer.writerow(["Analytic ID", "Internal Code", "Display Name", "Is Active", "Alert Count", "Incident Count", "Critical Alert Count"])
            for item in data:
                writer.writerow([
                    item["analytic_id"], item["internal_code"], item["display_name"],
                    item["is_active"], item["alert_count"], item["incident_count"],
                    item["critical_alert_count"]
                ])

        else:
            raise HTTPException(status_code=400, detail=f"Unsupported report_type for export: {report_type}")

        return output.getvalue()
