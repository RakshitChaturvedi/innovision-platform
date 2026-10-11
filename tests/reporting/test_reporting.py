import os
import uuid
from datetime import datetime, timezone, timedelta
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from services.reporting.src.service import ReportingService
from services.auth.src.rbac import Role


@pytest_asyncio.fixture
async def session_factory():
    db_url = os.getenv(
        "DATABASE_URL_LOCAL",
        "postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform"
    )
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5433")

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def reporting_service(session_factory):
    yield ReportingService(session_factory)


@pytest_asyncio.fixture
async def setup_reporting_data(session_factory):
    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())

    site_a_id = str(uuid.uuid4())
    site_b_id = str(uuid.uuid4())

    zone_a_id = str(uuid.uuid4())
    zone_b_id = str(uuid.uuid4())

    camera_a_id = str(uuid.uuid4())
    camera_b_id = str(uuid.uuid4())

    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())
    superadmin_id = str(uuid.uuid4())

    alert_a1_id = str(uuid.uuid4())
    alert_a2_id = str(uuid.uuid4())
    alert_b1_id = str(uuid.uuid4())

    inc_a1_id = str(uuid.uuid4())
    inc_a2_id = str(uuid.uuid4())
    inc_b1_id = str(uuid.uuid4())

    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)
    two_hours_ago = now - timedelta(hours=2)

    async with session_factory() as session:
        async with session.begin():
            # Orgs
            await session.execute(text("""
                INSERT INTO organizations (id, name, code, created_at, updated_at)
                VALUES (:oa, 'Org A', :code_a, now(), now()),
                       (:ob, 'Org B', :code_b, now(), now())
            """), {
                "oa": org_a_id, "code_a": f"org_a_{uuid.uuid4().hex[:6]}",
                "ob": org_b_id, "code_b": f"org_b_{uuid.uuid4().hex[:6]}",
            })

            # Sites
            await session.execute(text("""
                INSERT INTO sites (id, organization_id, name, code, created_at, updated_at)
                VALUES (:sa, :oa, 'Site A', :code_sa, now(), now()),
                       (:sb, :ob, 'Site B', :code_sb, now(), now())
            """), {
                "sa": site_a_id, "oa": org_a_id, "code_sa": f"sa_{uuid.uuid4().hex[:6]}",
                "sb": site_b_id, "ob": org_b_id, "code_sb": f"sb_{uuid.uuid4().hex[:6]}",
            })

            # Zones
            await session.execute(text("""
                INSERT INTO zones (id, site_id, name, slug, created_at, updated_at)
                VALUES (:za, :sa, 'Zone A', :slug_za, now(), now()),
                       (:zb, :sb, 'Zone B', :slug_zb, now(), now())
            """), {
                "za": zone_a_id, "sa": site_a_id, "slug_za": f"za_{uuid.uuid4().hex[:6]}",
                "zb": zone_b_id, "sb": site_b_id, "slug_zb": f"zb_{uuid.uuid4().hex[:6]}",
            })

            # Cameras
            await session.execute(text("""
                INSERT INTO cameras (id, organization_id, site_id, name, rtsp_url, status, use_cases, created_at, updated_at)
                VALUES (:ca, :oa, :sa, 'Camera A', 'rtsp://cam_a', 'online', ARRAY['uc3'], now(), now()),
                       (:cb, :ob, :sb, 'Camera B', 'rtsp://cam_b', 'online', ARRAY['uc1'], now(), now())
            """), {
                "ca": camera_a_id, "oa": org_a_id, "sa": site_a_id,
                "cb": camera_b_id, "ob": org_b_id, "sb": site_b_id,
            })

            # Users
            await session.execute(text("""
                INSERT INTO users (id, organization_id, name, email, password_hash, role)
                VALUES (:ua, :oa, 'Admin A', :ea, 'hash', 'org_admin'),
                       (:ub, :ob, 'Admin B', :eb, 'hash', 'org_admin'),
                       (:sa, NULL, 'Super Admin', :esa, 'hash', 'superadmin')
            """), {
                "ua": user_a_id, "oa": org_a_id, "ea": f"a_{uuid.uuid4().hex[:8]}@test.com",
                "ub": user_b_id, "ob": org_b_id, "eb": f"b_{uuid.uuid4().hex[:8]}@test.com",
                "sa": superadmin_id, "esa": f"sa_{uuid.uuid4().hex[:8]}@test.com",
            })

            # Alerts
            await session.execute(text("""
                INSERT INTO alerts (id, alert_id, camera_id, source_uc, alert_type, severity, title, description, source_event_id, status, created_at)
                VALUES
                (:a1, :a1, :ca, 'uc3', 'ppe_violation', 'critical', 'No Helmet', 'No helmet detected', :se1, 'pending', :t1),
                (:a2, :a2, :ca, 'uc3', 'ppe_violation', 'medium', 'No Vest', 'No vest detected', :se2, 'resolved', :t2),
                (:b1, :b1, :cb, 'uc1', 'intrusion', 'high', 'Fence Breach', 'Fence breach detected', :se3, 'pending', :t1)
            """), {
                "a1": alert_a1_id, "a2": alert_a2_id, "b1": alert_b1_id,
                "ca": camera_a_id, "cb": camera_b_id,
                "se1": str(uuid.uuid4()), "se2": str(uuid.uuid4()), "se3": str(uuid.uuid4()),
                "t1": two_hours_ago, "t2": one_hour_ago,
            })

            # Incidents
            await session.execute(text("""
                INSERT INTO incidents (id, organization_id, site_id, zone_id, camera_id, title, description, severity, status, created_by, created_at, updated_at, resolved_at)
                VALUES
                (:ia1, :oa, :sa, :za, :ca, 'PPE Incident 1', 'Helmet violation', 'critical', 'resolved', :ua, :t1, :t2, :t2),
                (:ia2, :oa, :sa, :za, :ca, 'PPE Incident 2', 'Vest violation', 'medium', 'open', :ua, :t2, :t2, NULL),
                (:ib1, :ob, :sb, :zb, :cb, 'Intrusion Incident', 'Perimeter breach', 'high', 'open', :ub, :t1, :t1, NULL)
            """), {
                "ia1": inc_a1_id, "ia2": inc_a2_id, "ib1": inc_b1_id,
                "oa": org_a_id, "ob": org_b_id,
                "sa": site_a_id, "sb": site_b_id,
                "za": zone_a_id, "zb": zone_b_id,
                "ca": camera_a_id, "cb": camera_b_id,
                "ua": user_a_id, "ub": user_b_id,
                "t1": two_hours_ago, "t2": one_hour_ago,
            })

            # Link alerts to incidents
            await session.execute(text("""
                INSERT INTO incident_alerts (incident_id, alert_id, linked_at)
                VALUES (:ia1, :a1, now()), (:ia2, :a2, now()), (:ib1, :b1, now())
            """), {"ia1": inc_a1_id, "a1": alert_a1_id, "ia2": inc_a2_id, "a2": alert_a2_id, "ib1": inc_b1_id, "b1": alert_b1_id})

    return {
        "org_a_id": org_a_id, "org_b_id": org_b_id,
        "site_a_id": site_a_id, "site_b_id": site_b_id,
        "zone_a_id": zone_a_id, "zone_b_id": zone_b_id,
        "camera_a_id": camera_a_id, "camera_b_id": camera_b_id,
        "user_a_id": user_a_id, "user_b_id": user_b_id, "superadmin_id": superadmin_id,
    }


# --- Access Control Tests ---

@pytest.mark.asyncio
async def test_superadmin_global_reports(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["superadmin_id"], "role": Role.SUPERADMIN, "org_id": None}
    summary = await reporting_service.get_executive_summary(user)
    assert summary["total_alerts"] >= 3
    assert summary["total_incidents"] >= 3


@pytest.mark.asyncio
async def test_superadmin_filter_by_org(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["superadmin_id"], "role": Role.SUPERADMIN, "org_id": None}
    org_a = setup_reporting_data["org_a_id"]
    summary = await reporting_service.get_executive_summary(user, organization_id=org_a)
    assert summary["total_alerts"] == 2
    assert summary["total_incidents"] == 2


@pytest.mark.asyncio
async def test_org_admin_view_own_org(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    summary = await reporting_service.get_executive_summary(user)
    assert summary["total_alerts"] == 2
    assert summary["total_incidents"] == 2


@pytest.mark.asyncio
async def test_org_admin_cannot_access_other_org(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    with pytest.raises(HTTPException) as exc:
        await reporting_service.get_executive_summary(user, organization_id=setup_reporting_data["org_b_id"])
    assert exc.value.status_code == 403


# --- Summary & Counts Tests ---

@pytest.mark.asyncio
async def test_summary_alert_severity_counts(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    summary = await reporting_service.get_executive_summary(user)
    assert summary["critical_alerts"] == 1
    assert summary["medium_alerts"] == 1
    assert summary["total_alerts"] == 2


@pytest.mark.asyncio
async def test_summary_incident_status_counts(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    summary = await reporting_service.get_executive_summary(user)
    assert summary["resolved_incidents"] == 1
    assert summary["open_incidents"] == 1


# --- Trends Tests ---

@pytest.mark.asyncio
async def test_alerts_trend_aggregation(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    trend = await reporting_service.get_alerts_trend(user, bucket="hourly")
    assert len(trend) > 0
    total_in_trend = sum(t["total"] for t in trend)
    assert total_in_trend == 2


@pytest.mark.asyncio
async def test_incidents_trend_aggregation(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    trend = await reporting_service.get_incidents_trend(user, bucket="hourly")
    assert len(trend) > 0
    created_in_trend = sum(t["created"] for t in trend)
    assert created_in_trend == 2


# --- Breakdown Tests ---

@pytest.mark.asyncio
async def test_breakdown_by_site(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    breakdown = await reporting_service.get_location_breakdown(user, group_by="site")
    assert len(breakdown) >= 1
    site_a = next((b for b in breakdown if b["site_id"] == setup_reporting_data["site_a_id"]), None)
    assert site_a is not None
    assert site_a["alert_count"] == 2
    assert site_a["incident_count"] == 2


@pytest.mark.asyncio
async def test_breakdown_by_zone(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    breakdown = await reporting_service.get_location_breakdown(user, group_by="zone")
    assert len(breakdown) >= 1
    zone_a = next((b for b in breakdown if b["zone_id"] == setup_reporting_data["zone_a_id"]), None)
    assert zone_a is not None
    assert zone_a["incident_count"] == 2


@pytest.mark.asyncio
async def test_breakdown_by_camera(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    breakdown = await reporting_service.get_location_breakdown(user, group_by="camera")
    assert len(breakdown) >= 1
    cam_a = next((b for b in breakdown if b["camera_id"] == setup_reporting_data["camera_a_id"]), None)
    assert cam_a is not None
    assert cam_a["alert_count"] == 2


@pytest.mark.asyncio
async def test_breakdown_by_analytic(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    breakdown = await reporting_service.get_location_breakdown(user, group_by="analytic")
    assert len(breakdown) >= 1
    ppe = next((b for b in breakdown if b["internal_code"] == "uc3"), None)
    assert ppe is not None
    assert ppe["alert_count"] == 2


# --- Resolution Performance Tests ---

@pytest.mark.asyncio
async def test_resolution_metrics_calculation(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    report = await reporting_service.get_incidents_report(user)
    perf = report["resolution_performance"]
    assert perf["average_resolution_time"] is not None
    assert perf["average_resolution_time"] == 60.0  # 1 hour difference between created_at and resolved_at
    assert perf["median_resolution_time"] == 60.0


# --- Analytics Performance Tests ---

@pytest.mark.asyncio
async def test_analytics_performance(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    perf = await reporting_service.get_analytics_performance(user)
    assert len(perf) >= 4  # 4 analytics in catalog
    uc3 = next((p for p in perf if p["internal_code"] == "uc3"), None)
    assert uc3 is not None
    assert uc3["alert_count"] == 2


# --- Export CSV Tests ---

@pytest.mark.asyncio
async def test_export_report_csv(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    csv_str = await reporting_service.export_report_csv(user, report_type="alerts")
    assert "Analytic ID" in csv_str
    assert "PPE Detection" in csv_str


@pytest.mark.asyncio
async def test_export_report_csv_cross_org_protection(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    with pytest.raises(HTTPException) as exc:
        await reporting_service.export_report_csv(user, report_type="alerts", organization_id=setup_reporting_data["org_b_id"])
    assert exc.value.status_code == 403


# --- Edge Cases & Validation Tests ---

@pytest.mark.asyncio
async def test_invalid_date_range(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    start = "2026-10-10T00:00:00Z"
    end = "2026-10-01T00:00:00Z"
    with pytest.raises(HTTPException) as exc:
        await reporting_service.get_executive_summary(user, start_date=start, end_date=end)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_no_matching_records(reporting_service, setup_reporting_data):
    user = {"sub": setup_reporting_data["user_a_id"], "role": Role.ORG_ADMIN, "org_id": setup_reporting_data["org_a_id"]}
    # Query for future dates
    start = "2099-01-01T00:00:00Z"
    end = "2099-01-02T00:00:00Z"
    summary = await reporting_service.get_executive_summary(user, start_date=start, end_date=end)
    assert summary["total_alerts"] == 0
    assert summary["total_incidents"] == 0
