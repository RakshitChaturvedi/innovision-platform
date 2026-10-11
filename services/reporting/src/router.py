import os
import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import AsyncGenerator

from services.auth.src.rbac import require_role, Role, get_current_user
from shared.platform_client.db import get_session_factory

from .config import settings
from .service import ReportingService
from .tasks import generate_report_task
from .storage import presigned_download_url
from .schemas import (
    ExecutiveSummaryResponse,
    AlertsReportResponse,
    AlertTrendItem,
    IncidentReportResponse,
    IncidentTrendItem,
    BreakdownItem,
    AnalyticsPerformanceItem,
)

router = APIRouter(prefix="/reports", tags=["reports"])
_session_factory = get_session_factory(
    settings.database_url or os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform"
    )
)


def get_service() -> ReportingService:
    return ReportingService(_session_factory)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _session_factory() as session:
        yield session


# --- Phase 6C Endpoints ---

@router.get("/summary", response_model=ExecutiveSummaryResponse)
async def get_summary(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    analytic_id: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    return await service.get_executive_summary(
        user,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        analytic_id=analytic_id,
    )


@router.get("/alerts")
async def get_alerts_report(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    analytic_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    if format and format.lower() == "csv":
        csv_content = await service.export_report_csv(
            user,
            report_type="alerts",
            start_date=start_date,
            end_date=end_date,
            organization_id=organization_id,
            site_id=site_id,
            zone_id=zone_id,
            camera_id=camera_id,
            analytic_id=analytic_id,
            severity=severity,
        )
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="report_alerts.csv"'},
        )

    return await service.get_alerts_report(
        user,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        analytic_id=analytic_id,
        severity=severity,
    )


@router.get("/alerts/trend", response_model=list[AlertTrendItem])
async def get_alerts_trend(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    analytic_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    bucket: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    return await service.get_alerts_trend(
        user,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        analytic_id=analytic_id,
        severity=severity,
        bucket=bucket,
    )


@router.get("/alerts/export")
async def export_alerts_csv(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    analytic_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    csv_content = await service.export_report_csv(
        user,
        report_type="alerts",
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        analytic_id=analytic_id,
        severity=severity,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="report_alerts.csv"'},
    )


@router.get("/incidents")
async def get_incidents_report(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    assigned_to: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    if format and format.lower() == "csv":
        csv_content = await service.export_report_csv(
            user,
            report_type="incidents",
            start_date=start_date,
            end_date=end_date,
            organization_id=organization_id,
            site_id=site_id,
            zone_id=zone_id,
            camera_id=camera_id,
            severity=severity,
        )
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="report_incidents.csv"'},
        )

    return await service.get_incidents_report(
        user,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        severity=severity,
        status=status,
        assigned_to=assigned_to,
    )


@router.get("/incidents/trend", response_model=list[IncidentTrendItem])
async def get_incidents_trend(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    bucket: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    return await service.get_incidents_trend(
        user,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        severity=severity,
        bucket=bucket,
    )


@router.get("/incidents/export")
async def export_incidents_csv(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    csv_content = await service.export_report_csv(
        user,
        report_type="incidents",
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        severity=severity,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="report_incidents.csv"'},
    )


@router.get("/breakdown", response_model=list[BreakdownItem])
async def get_location_breakdown(
    group_by: str = Query("site"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    if format and format.lower() == "csv":
        csv_content = await service.export_report_csv(
            user,
            report_type="breakdown",
            group_by=group_by,
            start_date=start_date,
            end_date=end_date,
            organization_id=organization_id,
            site_id=site_id,
            zone_id=zone_id,
        )
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="report_breakdown_{group_by}.csv"'},
        )

    return await service.get_location_breakdown(
        user,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
    )


@router.get("/analytics", response_model=list[AnalyticsPerformanceItem])
async def get_analytics_performance(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    format: Optional[str] = Query(None),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    if format and format.lower() == "csv":
        csv_content = await service.export_report_csv(
            user,
            report_type="analytics",
            start_date=start_date,
            end_date=end_date,
            organization_id=organization_id,
        )
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="report_analytics_performance.csv"'},
        )

    return await service.get_analytics_performance(
        user,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
    )


@router.get("/export")
async def export_generic_csv(
    report_type: str = Query("summary"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    organization_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    zone_id: Optional[str] = Query(None),
    camera_id: Optional[str] = Query(None),
    analytic_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    group_by: str = Query("site"),
    user: dict = Depends(get_current_user),
    service: ReportingService = Depends(get_service),
):
    csv_content = await service.export_report_csv(
        user,
        report_type=report_type,
        start_date=start_date,
        end_date=end_date,
        organization_id=organization_id,
        site_id=site_id,
        zone_id=zone_id,
        camera_id=camera_id,
        analytic_id=analytic_id,
        severity=severity,
        group_by=group_by,
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="report_{report_type}.csv"'},
    )


# --- Legacy/Async PDF Report Generation Endpoints (Preserved) ---

@router.post("/generate", dependencies=[Depends(require_role(Role.OPERATOR))])
async def generate(
    report_type: str,
    date_start: str,
    date_end: str,
    camera_ids: list[str] | None = None,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report_id = str(uuid.uuid4())

    async with db.begin():
        await db.execute(text("""
            INSERT INTO reports
                (id, generated_by, camera_ids, date_range_start, date_range_end, status)
            VALUES
                (:id, :generated_by, :camera_ids, :start, :end, 'pending')
        """), {
            "id": report_id,
            "generated_by": user["sub"],
            "camera_ids": camera_ids or [],
            "start": datetime.fromisoformat(date_start),
            "end": datetime.fromisoformat(date_end),
        })

    generate_report_task.apply_async(
        args=[report_id, report_type, date_start, date_end, camera_ids]
    )

    return {"report_id": report_id, "status": "pending"}


@router.get("/{report_id}/status")
async def status(report_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT * FROM reports WHERE id = :id"), {"id": report_id}
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    if user.get("role") != Role.SUPERADMIN:
        if str(row.generated_by) != str(user.get("sub")):
            u_row = await db.execute(text("SELECT organization_id FROM users WHERE id = :id"), {"id": row.generated_by})
            target_user = u_row.fetchone()
            user_org = user.get("org_id") or user.get("organization_id")
            if not target_user or str(target_user.organization_id) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization report access forbidden")
    return dict(row._mapping)


@router.get("/{report_id}/download")
async def download(report_id: str, user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT status, object_key, generated_by FROM reports WHERE id = :id"), {"id": report_id}
    )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")
    if user.get("role") != Role.SUPERADMIN:
        if str(row.generated_by) != str(user.get("sub")):
            u_row = await db.execute(text("SELECT organization_id FROM users WHERE id = :id"), {"id": row.generated_by})
            target_user = u_row.fetchone()
            user_org = user.get("org_id") or user.get("organization_id")
            if not target_user or str(target_user.organization_id) != str(user_org):
                raise HTTPException(status_code=403, detail="Cross-organization report access forbidden")
    if row.status != "complete" or not row.object_key:
        raise HTTPException(status_code=409, detail=f"Report not ready — status: {row.status}")

    url = presigned_download_url(row.object_key)
    return {"download_url": url}


@router.get("")
async def list_reports(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.get("role") == Role.SUPERADMIN:
        rows = await db.execute(text("""
            SELECT * FROM reports ORDER BY created_at DESC LIMIT 50
        """))
    else:
        user_org = user.get("org_id") or user.get("organization_id")
        rows = await db.execute(text("""
            SELECT r.* FROM reports r
            JOIN users u ON r.generated_by = u.id
            WHERE u.organization_id = :org_id OR r.generated_by = :user_id
            ORDER BY r.created_at DESC LIMIT 50
        """), {"org_id": str(user_org) if user_org else None, "user_id": user.get("sub")})
    return [dict(r._mapping) for r in rows.fetchall()]