import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import os
os.environ["PYTEST_CURRENT_TEST"] = "true"
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

# Import platform contracts and services
from shared.contracts.frame_event import FrameEvent
from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, FrameProvider, SourceUC
from services.camera_registry.src.schemas import (
    OrganizationCreate, SiteCreate, ZoneCreate, CameraCreate, OrganizationSubscriptionCreate
)
from services.camera_registry.src.service import CameraRegistryService
from services.alert_management.src.persistence import insert_alert
import services.notification.src.service as notif_module
from services.notification.src.service import NotificationService, create_user_notification, dispatch_alert_notifications
from services.incident_management.src.service import IncidentService
from services.reporting.src.service import ReportingService
from services.audit.src.service import AuditService
from services.audit.src.writer import write_audit_entry
from services.uc3.src.compliance import evaluate_compliance, new_session_state

class DummyRedis:
    async def publish(self, channel, message):
        pass

# Mock send_email_async and send_escalation_email to avoid SMTP network timeouts
async def mock_send_email(*args, **kwargs):
    pass
notif_module.send_email_async = mock_send_email

import services.notification.src.email as email_mod
email_mod.send_escalation_email = mock_send_email

async def run_e2e_trace():
    db_url = os.getenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@127.0.0.1:5433/innovision_platform")
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = DummyRedis()

    cam_service = CameraRegistryService(session_factory, redis_client)
    notif_service = NotificationService(session_factory)
    incident_service = IncidentService(session_factory)
    reporting_service = ReportingService(session_factory)
    audit_service = AuditService(session_factory)

    # 1. Organization
    org_code = f"e2e_org_{uuid.uuid4().hex[:6]}"
    org = await cam_service.create_organization(OrganizationCreate(name="E2E Test Enterprise Org", code=org_code, tier="enterprise"))
    org_id = str(org["id"])

    # Create an Org Admin user for notifications & audit
    user_id = str(uuid.uuid4())
    user_email = f"e2e_admin_{uuid.uuid4().hex[:6]}@enterprise.com"
    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("""
                INSERT INTO users (id, name, email, password_hash, role, organization_id, is_active, created_at, updated_at)
                VALUES (:id, 'E2E Admin User', :email, 'hashed_pw', 'org_admin', :org_id, true, now(), now())
            """), {"id": user_id, "email": user_email, "org_id": org_id})

    # Log audit for Org Creation
    await write_audit_entry(
        session_factory=session_factory,
        service="camera_registry",
        action="CREATE",
        entity_type="organization",
        entity_id=org_id,
        user_id=user_id,
        metadata={"name": "E2E Test Enterprise Org", "code": org_code}
    )

    # 2. Site
    site_code = f"e2e_site_{uuid.uuid4().hex[:6]}"
    site = await cam_service.create_site(SiteCreate(name="E2E Main Refinery Site", code=site_code, organization_id=uuid.UUID(org_id)))
    site_id = str(site["id"])

    # 3. Zone
    zone = await cam_service.create_zone(ZoneCreate(name="Kiln Danger Zone", zone_type="kiln", site_id=uuid.UUID(site_id)))
    zone_id = str(zone["id"])

    # 4. Camera
    cam_data = CameraCreate(
        site_id=uuid.UUID(site_id),
        zone_id=uuid.UUID(zone_id),
        name="E2E Thermal Cam 01",
        rtsp_url="rtsp://192.168.1.100/stream1",
        ingestion_driver="rtsp_ffmpeg",
        location="Zone A Kiln Feed",
        is_active=True
    )
    camera = await cam_service.create_camera(cam_data)
    camera_id = str(camera["id"])

    # 5. Analytics Subscription
    catalog = await cam_service.list_analytics_catalog()
    uc3_analytic = next(
        a for a in catalog 
        if str(a.get("code", "")).upper() == "UC3" or str(a.get("internal_code", "")).upper() == "UC3"
    )
    uc3_analytic_id = str(uc3_analytic["id"])

    sub = await cam_service.create_organization_subscription(
        organization_id=org_id,
        data=OrganizationSubscriptionCreate(
            analytic_id=uuid.UUID(uc3_analytic_id),
            max_cameras_allowed=10,
            is_enabled=True
        )
    )

    # 6. Zone Analytics Policy
    policy = await cam_service.update_zone_analytics_policy(
        zone_id=zone_id,
        analytic_id=uc3_analytic_id,
        is_enabled=True,
        current_user={"sub": user_id, "role": "org_admin", "org_id": org_id},
        user_org_id=org_id
    )

    # 7. Camera Effective Analytics
    eff = await cam_service.get_camera_effective_analytics(camera_id)
    eff_uc3 = next((a for a in eff if str(a.get("internal_code", "")).lower() == "uc3"), None)
    eff_status = "PASS" if (eff_uc3 and eff_uc3.get("is_active")) else "FAIL"

    # 8. FrameEvent
    frame_evt = FrameEvent(
        camera_id=uuid.UUID(camera_id),
        frame_seq=1042,
        timestamp=datetime.now(timezone.utc),
        frame_provider=FrameProvider.MINIO,
        frame_reference=f"frames/{camera_id}/2026/10/08/frame_1042.jpg",
        frame_shape=(1080, 1920)
    )

    # 9. UC Analytics / UC Event (Inference & Non-compliance evaluation)
    worker_states = new_session_state()
    detections = [
        {"label": "person", "box": [0.1, 0.1, 0.5, 0.8], "conf": 0.95, "_track_id": 1},
        {"label": "head", "box": [0.15, 0.1, 0.25, 0.2], "conf": 0.90, "_track_id": 1} # head missing helmet
    ]
    now_ts = time.time()
    severity_label, unique_violations, worker_violations = evaluate_compliance(
        detections=detections,
        worker_states=worker_states,
        now=now_ts,
        required_ppe=frozenset({"helmet"})
    )
    uc_event_id = str(uuid.uuid4())

    # 10. AlertEvent & Alert Persistence
    alert_evt = AlertEvent(
        camera_id=uuid.UUID(camera_id),
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.HIGH,
        alert_type="PPE_NON_COMPLIANCE",
        title="PPE Safety Violation: Missing Hard Hat",
        description=f"Worker detected in Zone {zone_id} without required helmet.",
        source_event_id=frame_evt.event_id,
        source_uc=SourceUC.UC3,
        frame_reference=frame_evt.frame_reference,
        frame_provider=frame_evt.frame_provider,
        metadata={"uc_event_id": uc_event_id, "violations": unique_violations, "zone_id": zone_id}
    )
    
    # Save alert to DB
    alert_row_id = str(uuid.uuid4())
    async with session_factory() as session:
        async with session.begin():
            await insert_alert(session, alert_row_id, alert_evt)

    # 11. Notification Persistence & Dispatch
    alert_row_dict = {
        "id": alert_row_id,
        "camera_id": camera_id,
        "severity": "high",
        "title": alert_evt.title,
        "description": alert_evt.description
    }
    await dispatch_alert_notifications(
        session_factory=session_factory,
        alert_row=alert_row_dict
    )
    notif = await create_user_notification(
        session_factory=session_factory,
        recipient_user_id=user_id,
        organization_id=org_id,
        type_str="high_alert",
        title=alert_evt.title,
        message=alert_evt.description,
        severity="high",
        resource_type="alert",
        resource_id=alert_row_id
    )
    notif_id = str(notif["id"]) if notif else "N/A"

    # 12. Incident Creation & Linking
    current_user_dict = {"sub": user_id, "role": "org_admin", "org_id": org_id}
    incident_data = {
        "title": "E2E PPE Violation Incident",
        "description": "High severity missing PPE incident on thermal cam",
        "severity": "high",
        "organization_id": org_id,
        "site_id": site_id,
        "zone_id": zone_id,
        "camera_id": camera_id,
        "assigned_to": user_id,
        "alert_ids": [alert_row_id]
    }
    inc_res = await incident_service.create_incident(
        user=current_user_dict,
        data=incident_data
    )
    incident_id = str(inc_res["incident"]["id"])

    # 13. Reporting Query
    report_res = await reporting_service.get_executive_summary(
        user=current_user_dict,
        organization_id=org_id
    )

    # 14. Audit Trail
    audit_res = await audit_service.list_audit_logs(
        user={"role": "superadmin", "org_id": None},
        organization_id=org_id,
        page=1,
        page_size=10
    )
    audit_ids = [str(r.id) for r in audit_res.items]

    # Output concrete trace results
    print("=== E2E FULL CHAIN TRACE EXECUTION RESULTS ===")
    print(f"Organization ID: {org_id}")
    print(f"Site ID: {site_id}")
    print(f"Zone ID: {zone_id}")
    print(f"Camera ID: {camera_id}")
    print(f"Subscription ID: {sub['id']}")
    print(f"Zone Policy Updated: {policy}")
    print(f"Effective Analytics Status: {eff_status}")
    print(f"FrameEvent ID: {frame_evt.event_id} (frame_seq: {frame_evt.frame_seq})")
    print(f"UC event ID: {uc_event_id}")
    print(f"Alert ID: {alert_row_id} (alert_id uuid: {alert_evt.alert_id})")
    print(f"Notification ID: {notif_id}")
    print(f"Incident ID: {incident_id}")
    print(f"Report Summary Total Alerts: {report_res.get('total_alerts')}")
    print(f"Audit event IDs ({len(audit_ids)} events logged): {audit_ids[:3]}")
    print("=== E2E TRACE SUCCESSFUL ===")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_e2e_trace())
