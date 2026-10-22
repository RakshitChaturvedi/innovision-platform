import os
import pytest
import uuid
import httpx
from unittest.mock import patch
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from services.auth.src.jwt import create_access_token
from services.camera_registry.src import router as router_module
from services.camera_registry.src.service import CameraRegistryService
from services.ingestion.src.camera_manager import CameraManager
from services.ingestion.src.stream_decoder import StreamDecoder
from conftest import get_safe_test_db_url


class DummyRedis:
    async def publish(self, channel, message):
        pass


def get_auth_headers(user_id: str, role: str, org_id: str | None = None, camera_ids: list[str] | None = None):
    token = create_access_token(user_id=user_id, role=role, camera_ids=camera_ids or [], org_id=org_id)
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


@pytest.mark.asyncio
async def test_full_crud_rbac_and_dependency_safeguards():
    # Detect DB URL dynamically with safety guard
    db_url = get_safe_test_db_url()
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5432")

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    dummy_redis = DummyRedis()
    registry_service = CameraRegistryService(session_factory=session_factory, redis_client=dummy_redis)

    app = FastAPI(title="Test Camera Registry")
    app.include_router(router_module.router)
    app.include_router(router_module.analytics_router)
    app.include_router(router_module.organizations_router)
    app.include_router(router_module.zones_router)
    app.dependency_overrides[router_module.get_service] = lambda: registry_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # Define actors with valid UUIDs
        superadmin_headers = get_auth_headers(str(uuid.uuid4()), "superadmin", None)
        
        # 1. Superadmin creates two tenant organizations for isolation testing
        org_a_code = f"rbac_a_{uuid.uuid4().hex[:6]}"
        resp_org_a = await client.post(
            "/cameras/organizations",
            headers=superadmin_headers,
            json={"name": "Tenant Alpha", "code": org_a_code, "tier": "enterprise"}
        )
        assert resp_org_a.status_code == 201, resp_org_a.text
        org_a = resp_org_a.json()
        org_a_id = str(org_a["id"])

        org_b_code = f"rbac_b_{uuid.uuid4().hex[:6]}"
        resp_org_b = await client.post(
            "/cameras/organizations",
            headers=superadmin_headers,
            json={"name": "Tenant Beta", "code": org_b_code, "tier": "enterprise"}
        )
        assert resp_org_b.status_code == 201, resp_org_b.text
        org_b = resp_org_b.json()
        org_b_id = str(org_b["id"])

        # Org Admins and Users
        org_a_admin_headers = get_auth_headers(str(uuid.uuid4()), "org_admin", org_a_id)
        org_b_admin_headers = get_auth_headers(str(uuid.uuid4()), "org_admin", org_b_id)
        operator_a_headers = get_auth_headers(str(uuid.uuid4()), "operator", org_a_id)
        viewer_a_headers = get_auth_headers(str(uuid.uuid4()), "viewer", org_a_id)

        # -------------------------------------------------------------
        # PART 1: Superadmin Org Updates & Deactivation with RBAC
        # -------------------------------------------------------------
        # Allowed: Superadmin updates organization details
        update_resp = await client.put(
            f"/cameras/organizations/{org_a_id}",
            headers=superadmin_headers,
            json={"name": "Tenant Alpha Updated", "tier": "enterprise"}
        )
        assert update_resp.status_code == 200, update_resp.text
        assert update_resp.json()["name"] == "Tenant Alpha Updated"

        # Allowed: Superadmin deactivates organization
        deact_resp = await client.put(
            f"/cameras/organizations/{org_a_id}/status",
            headers=superadmin_headers,
            json={"is_active": False}
        )
        assert deact_resp.status_code == 200, deact_resp.text
        assert deact_resp.json()["is_active"] is False

        # Reactivate for subsequent tests
        react_resp = await client.put(
            f"/cameras/organizations/{org_a_id}/status",
            headers=superadmin_headers,
            json={"is_active": True}
        )
        assert react_resp.status_code == 200
        assert react_resp.json()["is_active"] is True

        # Denied: ORG_ADMIN attempts to update organization details
        denied_org_update = await client.put(
            f"/cameras/organizations/{org_a_id}",
            headers=org_a_admin_headers,
            json={"name": "Hacked Org", "tier": "unlimited"}
        )
        assert denied_org_update.status_code == 403

        # Denied: ORG_ADMIN attempts to deactivate organization
        denied_org_deact = await client.put(
            f"/cameras/organizations/{org_a_id}/status",
            headers=org_a_admin_headers,
            json={"is_active": False}
        )
        assert denied_org_deact.status_code == 403

        # Denied: Operator and Viewer
        assert (await client.put(f"/cameras/organizations/{org_a_id}", headers=operator_a_headers, json={"name": "X"})).status_code == 403
        assert (await client.put(f"/cameras/organizations/{org_a_id}", headers=viewer_a_headers, json={"name": "X"})).status_code == 403

        # -------------------------------------------------------------
        # PART 2: Site CRUD, Dependency Validation & RBAC
        # -------------------------------------------------------------
        # Allowed: Org A Admin creates Site in Org A
        site_resp = await client.post(
            "/cameras/sites",
            headers=org_a_admin_headers,
            json={"organization_id": org_a_id, "name": "Alpha Cement Plant", "code": f"site_{uuid.uuid4().hex[:6]}", "timezone": "UTC"}
        )
        assert site_resp.status_code in (200, 201), site_resp.text
        site_a = site_resp.json()
        site_a_id = str(site_a["id"])

        # Allowed: Org A Admin updates Site
        site_update_resp = await client.put(
            f"/cameras/sites/{site_a_id}",
            headers=org_a_admin_headers,
            json={"name": "Alpha Plant - Main Unit", "timezone": "Asia/Kolkata"}
        )
        assert site_update_resp.status_code == 200, site_update_resp.text
        assert site_update_resp.json()["name"] == "Alpha Plant - Main Unit"

        # Denied: Cross-org Admin (Org B Admin) attempts to update Site in Org A
        cross_site_update = await client.put(
            f"/cameras/sites/{site_a_id}",
            headers=org_b_admin_headers,
            json={"name": "Tampered Plant"}
        )
        assert cross_site_update.status_code == 403

        # Denied: Operator and Viewer attempt to update Site
        assert (await client.put(f"/cameras/sites/{site_a_id}", headers=operator_a_headers, json={"name": "Oper"})).status_code == 403
        assert (await client.put(f"/cameras/sites/{site_a_id}", headers=viewer_a_headers, json={"name": "View"})).status_code == 403

        # -------------------------------------------------------------
        # PART 3: Zone CRUD, Dependency Safeguards & RBAC
        # -------------------------------------------------------------
        # Allowed: Org A Admin creates Zone in Site A
        zone_resp = await client.post(
            "/cameras/zones",
            headers=org_a_admin_headers,
            json={"site_id": site_a_id, "name": "Kiln Preheater Area", "zone_type": "industrial", "risk_level": "high"}
        )
        assert zone_resp.status_code in (200, 201), zone_resp.text
        zone_a = zone_resp.json()
        zone_a_id = str(zone_a["id"])

        # Allowed: Org A Admin updates Zone
        zone_update_resp = await client.put(
            f"/cameras/zones/{zone_a_id}",
            headers=org_a_admin_headers,
            json={"name": "Kiln Preheater Tower (Active)", "risk_level": "critical"}
        )
        assert zone_update_resp.status_code == 200, zone_update_resp.text
        assert zone_update_resp.json()["name"] == "Kiln Preheater Tower (Active)"

        # Denied: Cross-org Admin attempts to update Zone
        assert (await client.put(f"/cameras/zones/{zone_a_id}", headers=org_b_admin_headers, json={"name": "Tamper"})).status_code == 403

        # Dependency Safeguard: Attempting to delete Site with active zone must fail with 409 Conflict
        site_del_blocked = await client.delete(
            f"/cameras/sites/{site_a_id}",
            headers=org_a_admin_headers
        )
        assert site_del_blocked.status_code == 409
        assert "Cannot delete site: active zones are associated with this site" in site_del_blocked.json()["detail"]

        # -------------------------------------------------------------
        # PART 4: Camera Creation, Decommissioning & Safe Zone Deletion
        # -------------------------------------------------------------
        # Create Camera and assign to Zone A
        cam_resp = await client.post(
            "/cameras",
            headers=org_a_admin_headers,
            json={"name": "Alpha Kiln Cam 01", "rtsp_url": "rtsp://localhost:8554/live/alpha_kiln1", "use_cases": ["uc3"], "lifecycle_state": "unassigned"}
        )
        assert cam_resp.status_code in (200, 201), cam_resp.text
        cam_a = cam_resp.json()
        cam_a_id = str(cam_a["id"])

        assign_resp = await client.put(
            f"/cameras/{cam_a_id}/assign-zone",
            headers=org_a_admin_headers,
            json={"zone_id": zone_a_id, "lifecycle_state": "active"}
        )
        assert assign_resp.status_code == 200, assign_resp.text

        # Dependency Safeguard: Attempting to delete Zone with active camera must fail with 409 Conflict
        zone_del_blocked = await client.delete(
            f"/cameras/zones/{zone_a_id}",
            headers=org_a_admin_headers
        )
        assert zone_del_blocked.status_code == 409
        assert "Cannot delete zone: active cameras are" in zone_del_blocked.json()["detail"]

        # Denied: Cross-org Admin attempts to decommission camera
        cross_cam_decomm = await client.put(
            f"/cameras/{cam_a_id}/decommission",
            headers=org_b_admin_headers
        )
        assert cross_cam_decomm.status_code == 403

        # Denied: Operator and Viewer attempt to decommission camera
        assert (await client.put(f"/cameras/{cam_a_id}/decommission", headers=operator_a_headers)).status_code == 403
        assert (await client.put(f"/cameras/{cam_a_id}/decommission", headers=viewer_a_headers)).status_code == 403

        # Allowed: Org A Admin decommissions Camera
        cam_decomm_resp = await client.put(
            f"/cameras/{cam_a_id}/decommission",
            headers=org_a_admin_headers
        )
        assert cam_decomm_resp.status_code == 200, cam_decomm_resp.text
        decomm_data = cam_decomm_resp.json()
        assert decomm_data["lifecycle_state"] == "disabled"
        assert decomm_data["status"] == "disabled"

        # HISTORY SAFEGUARD: Even when decommissioned, camera STILL references zone_a_id.
        # Deleting zone_a_id must still fail with 409 Conflict to preserve historical records!
        zone_del_decomm_blocked = await client.delete(
            f"/cameras/zones/{zone_a_id}",
            headers=org_a_admin_headers
        )
        assert zone_del_decomm_blocked.status_code == 409, zone_del_decomm_blocked.text
        assert "Cannot delete zone: active cameras are assigned to this zone (or decommissioned cameras still reference it)" in zone_del_decomm_blocked.json()["detail"]

        # To safely delete the zone, the decommissioned camera must be explicitly unassigned
        unassign_resp = await client.put(
            f"/cameras/{cam_a_id}/assign-zone",
            headers=org_a_admin_headers,
            json={"zone_id": None, "site_id": None, "lifecycle_state": "disabled"}
        )
        assert unassign_resp.status_code == 200

        # Now that camera has been unassigned, Zone deletion succeeds (204 No Content)
        zone_del_resp = await client.delete(
            f"/cameras/zones/{zone_a_id}",
            headers=org_a_admin_headers
        )
        assert zone_del_resp.status_code in (200, 204), zone_del_resp.text

        # Now that Zone is deleted and camera is unassigned from site, Site deletion succeeds (204 No Content)
        site_del_resp = await client.delete(
            f"/cameras/sites/{site_a_id}",
            headers=org_a_admin_headers
        )
        assert site_del_resp.status_code in (200, 204), site_del_resp.text

    # -------------------------------------------------------------
    # PART 5: Audit Log Verification
    # -------------------------------------------------------------
    async with session_factory() as session:
        # Check audit log entries created during this test
        res = await session.execute(
            text("""
                SELECT action, entity_type, entity_id 
                FROM audit_log 
                WHERE entity_id IN (:org_a_id, :site_a_id, :zone_a_id, :cam_a_id)
                ORDER BY timestamp ASC
            """),
            {"org_a_id": org_a_id, "site_a_id": site_a_id, "zone_a_id": zone_a_id, "cam_a_id": cam_a_id}
        )
        audit_rows = res.fetchall()
        actions = [row[0] for row in audit_rows]
        assert "organization_updated" in actions
        assert "organization_status_updated" in actions
        assert "site_created" in actions
        assert "site_updated" in actions
        assert "zone_created" in actions
        assert "zone_updated" in actions
        assert "camera_decommissioned" in actions
        assert "zone_deleted" in actions
        assert "site_deleted" in actions
    await engine.dispose()


@pytest.mark.asyncio
async def test_subscription_mutation_rbac_superadmin_only():
    """Verifies BLK-02: Only SUPERADMIN can create, update, or delete organization subscriptions.
    ORG_ADMIN, legacy ADMIN, OPERATOR, and VIEWER are strictly rejected with 403 Forbidden,
    and rejected requests do NOT mutate subscription state.
    """
    db_url = get_safe_test_db_url()
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5432")

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    dummy_redis = DummyRedis()
    registry_service = CameraRegistryService(session_factory=session_factory, redis_client=dummy_redis)

    app = FastAPI(title="Test Camera Registry Subscriptions")
    app.include_router(router_module.router)
    app.include_router(router_module.analytics_router)
    app.include_router(router_module.organizations_router)
    app.dependency_overrides[router_module.get_service] = lambda: registry_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        superadmin_headers = get_auth_headers(str(uuid.uuid4()), "superadmin", None)

        # 1. Superadmin creates test organization
        org_code = f"sub_rbac_{uuid.uuid4().hex[:6]}"
        resp_org = await client.post(
            "/cameras/organizations",
            headers=superadmin_headers,
            json={"name": "Subscription Tenant", "code": org_code, "tier": "enterprise"}
        )
        assert resp_org.status_code == 201
        org_id = str(resp_org.json()["id"])

        # Fetch available analytics catalog to get analytic_id
        cat_resp = await client.get("/cameras/analytics/catalog", headers=superadmin_headers)
        assert cat_resp.status_code == 200
        analytic_id = str(cat_resp.json()[0]["id"])

        # Define non-superadmin actors for this tenant
        org_admin_headers = get_auth_headers(str(uuid.uuid4()), "org_admin", org_id)
        legacy_admin_headers = get_auth_headers(str(uuid.uuid4()), "admin", org_id)
        operator_headers = get_auth_headers(str(uuid.uuid4()), "operator", org_id)
        viewer_headers = get_auth_headers(str(uuid.uuid4()), "viewer", org_id)

        sub_payload = {"analytic_id": analytic_id, "max_cameras_allowed": 5, "is_enabled": True}

        # 2. Denied subscription creation for all non-superadmin roles
        assert (await client.post(f"/cameras/organizations/{org_id}/subscriptions", headers=org_admin_headers, json=sub_payload)).status_code == 403
        assert (await client.post(f"/cameras/organizations/{org_id}/subscriptions", headers=legacy_admin_headers, json=sub_payload)).status_code == 403
        assert (await client.post(f"/cameras/organizations/{org_id}/subscriptions", headers=operator_headers, json=sub_payload)).status_code == 403
        assert (await client.post(f"/cameras/organizations/{org_id}/subscriptions", headers=viewer_headers, json=sub_payload)).status_code == 403

        # Verify no subscription was created after rejections
        list_resp = await client.get(f"/cameras/organizations/{org_id}/subscriptions", headers=superadmin_headers)
        assert list_resp.status_code == 200
        assert len(list_resp.json()) == 0

        # 3. Allowed: Superadmin creates subscription
        create_resp = await client.post(
            f"/cameras/organizations/{org_id}/subscriptions",
            headers=superadmin_headers,
            json=sub_payload
        )
        assert create_resp.status_code == 201, create_resp.text
        sub_data = create_resp.json()
        assert sub_data["max_cameras_allowed"] == 5

        # 4. Denied subscription update for non-superadmin roles
        update_payload = {"max_cameras_allowed": 10, "is_enabled": True}
        assert (await client.put(f"/cameras/organizations/{org_id}/subscriptions/{analytic_id}", headers=org_admin_headers, json=update_payload)).status_code == 403
        assert (await client.put(f"/cameras/organizations/{org_id}/subscriptions/{analytic_id}", headers=legacy_admin_headers, json=update_payload)).status_code == 403

        # Verify state unchanged after rejected updates
        verify_resp = await client.get(f"/cameras/organizations/{org_id}/subscriptions", headers=superadmin_headers)
        assert verify_resp.json()[0]["max_cameras_allowed"] == 5

        # 5. Allowed: Superadmin updates subscription
        super_update_resp = await client.put(
            f"/cameras/organizations/{org_id}/subscriptions/{analytic_id}",
            headers=superadmin_headers,
            json=update_payload
        )
        assert super_update_resp.status_code == 200
        assert super_update_resp.json()["max_cameras_allowed"] == 10

        # 6. Denied subscription deletion for non-superadmin roles
        assert (await client.delete(f"/cameras/organizations/{org_id}/subscriptions/{analytic_id}", headers=org_admin_headers)).status_code == 403
        assert (await client.delete(f"/cameras/organizations/{org_id}/subscriptions/{analytic_id}", headers=legacy_admin_headers)).status_code == 403

        # 7. Allowed: Superadmin deletes subscription
        super_del_resp = await client.delete(
            f"/cameras/organizations/{org_id}/subscriptions/{analytic_id}",
            headers=superadmin_headers
        )
        assert super_del_resp.status_code == 204

        # Verify deletion confirmed
        empty_list = await client.get(f"/cameras/organizations/{org_id}/subscriptions", headers=superadmin_headers)
        assert len(empty_list.json()) == 0

    await engine.dispose()


def test_upload_only_camera_isolation_from_live_ingestion():
    """Verifies BLK-01: Upload-only cameras are identified and excluded from live RTSP capture,
    and StreamDecoder explicitly rejects upload:// sources.
    """
    # 1. Test CameraManager.is_live_camera logic
    upload_cam_1 = {"id": "cam-1", "source_type": "uploaded_video", "rtsp_url": "upload://dock_cam"}
    upload_cam_2 = {"id": "cam-2", "source_type": "upload", "rtsp_url": "rtsp://10.0.0.1/live"}
    upload_cam_3 = {"id": "cam-3", "source_type": "rtsp", "rtsp_url": "upload://gate_cam"}
    empty_url_cam = {"id": "cam-4", "source_type": "rtsp", "rtsp_url": ""}
    live_rtsp_cam = {"id": "cam-5", "source_type": "rtsp", "rtsp_url": "rtsp://192.168.1.10:554/feed"}

    assert CameraManager.is_live_camera(upload_cam_1) is False
    assert CameraManager.is_live_camera(upload_cam_2) is False
    assert CameraManager.is_live_camera(upload_cam_3) is False
    assert CameraManager.is_live_camera(empty_url_cam) is False
    assert CameraManager.is_live_camera(live_rtsp_cam) is True

    # 2. Test StreamDecoder rejects upload:// source with clear error
    decoder = StreamDecoder(source="upload://dock_cam")
    with pytest.raises(ValueError, match="Cannot decode stream for upload-only camera source"):
        decoder._build_command()

    # 3. Test StreamDecoder accepts valid rtsp:// source
    rtsp_decoder = StreamDecoder(source="rtsp://192.168.1.10:554/feed")
    cmd = rtsp_decoder._build_command()
    assert "-rtsp_transport" in cmd
    assert "rtsp://192.168.1.10:554/feed" in cmd


@pytest.mark.asyncio
async def test_audit_failure_blocks_mutation():
    """Verifies BLK-03: If audit log write fails, the administrative mutation does NOT silently succeed."""
    db_url = get_safe_test_db_url()
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5432")

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    dummy_redis = DummyRedis()
    registry_service = CameraRegistryService(session_factory=session_factory, redis_client=dummy_redis)

    app = FastAPI(title="Test Camera Registry")
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.get_service] = lambda: registry_service

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        superadmin_headers = get_auth_headers(str(uuid.uuid4()), "superadmin", None)

        # Mock write_audit_entry to simulate database audit log write failure
        with patch("services.camera_registry.src.router.write_audit_entry", side_effect=RuntimeError("Audit database connection lost")):
            resp = await client.post(
                "/cameras/organizations",
                headers=superadmin_headers,
                json={"name": "Failing Audit Org", "code": f"fail_{uuid.uuid4().hex[:6]}"}
            )
            # Must fail with 500 and clear error; must NOT return 201 Created
            assert resp.status_code == 500
            assert "Security audit logging failed" in resp.json()["detail"]

    await engine.dispose()
