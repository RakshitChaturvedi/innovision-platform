import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from services.incident_management.src.service import IncidentService
from services.auth.src.rbac import Role

@pytest_asyncio.fixture
async def session_factory():
    from conftest import get_safe_test_db_url
    db_url = get_safe_test_db_url()
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5433")

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()

@pytest_asyncio.fixture
async def incident_service(session_factory):
    yield IncidentService(session_factory)

@pytest_asyncio.fixture
async def setup_test_data(session_factory):
    """Creates Org A, Org B, Sites, Cameras, Alerts, and Users for testing."""
    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())

    site_a_id = str(uuid.uuid4())
    site_b_id = str(uuid.uuid4())

    camera_a_id = str(uuid.uuid4())
    camera_b_id = str(uuid.uuid4())

    user_a_id = str(uuid.uuid4())
    user_b_id = str(uuid.uuid4())
    superadmin_user_id = str(uuid.uuid4())

    alert_a_id = str(uuid.uuid4())
    alert_b_id = str(uuid.uuid4())

    async with session_factory() as session:
        async with session.begin():
            # Create Orgs
            await session.execute(text("""
                INSERT INTO organizations (id, name, code, created_at, updated_at)
                VALUES (:oa, 'Incident Org A', :code_a, now(), now()),
                       (:ob, 'Incident Org B', :code_b, now(), now())
            """), {
                "oa": org_a_id, "code_a": f"inc_a_{uuid.uuid4().hex[:6]}",
                "ob": org_b_id, "code_b": f"inc_b_{uuid.uuid4().hex[:6]}"
            })

            # Create Sites
            await session.execute(text("""
                INSERT INTO sites (id, organization_id, name, code, created_at, updated_at)
                VALUES (:sa, :oa, 'Site A', :code_sa, now(), now()),
                       (:sb, :ob, 'Site B', :code_sb, now(), now())
            """), {
                "sa": site_a_id, "oa": org_a_id, "code_sa": f"sa_{uuid.uuid4().hex[:6]}",
                "sb": site_b_id, "ob": org_b_id, "code_sb": f"sb_{uuid.uuid4().hex[:6]}"
            })

            # Create Cameras
            await session.execute(text("""
                INSERT INTO cameras (id, site_id, name, rtsp_url, status, created_at, updated_at)
                VALUES (:ca, :sa, 'Camera A', 'rtsp://cam_a', 'online', now(), now()),
                       (:cb, :sb, 'Camera B', 'rtsp://cam_b', 'online', now(), now())
            """), {
                "ca": camera_a_id, "sa": site_a_id,
                "cb": camera_b_id, "sb": site_b_id,
            })

            # Create Users
            await session.execute(text("""
                INSERT INTO users (id, name, email, password_hash, role, organization_id, is_active, created_at, updated_at)
                VALUES (:ua, 'User A', :ea, 'hash', 'org_admin', :oa, true, now(), now()),
                       (:ub, 'User B', :eb, 'hash', 'org_admin', :ob, true, now(), now()),
                       (:sa, 'Super Admin', :esa, 'hash', 'superadmin', NULL, true, now(), now())
            """), {
                "ua": user_a_id, "ea": f"user_a_{uuid.uuid4().hex[:6]}@example.com", "oa": org_a_id,
                "ub": user_b_id, "eb": f"user_b_{uuid.uuid4().hex[:6]}@example.com", "ob": org_b_id,
                "sa": superadmin_user_id, "esa": f"super_{uuid.uuid4().hex[:6]}@example.com",
            })

            # Create Alerts
            await session.execute(text("""
                INSERT INTO alerts (id, alert_id, camera_id, source_uc, alert_type, title, description, severity, status, source_event_id, created_at)
                VALUES (:ala, :ala, :ca, 'uc1', 'intrusion', 'Perimeter Intrusion Org A', 'Description Org A', 'high', 'pending', :ala, now()),
                       (:alb, :alb, :cb, 'uc3', 'no_helmet', 'PPE Violation Org B', 'Description Org B', 'critical', 'pending', :alb, now())
            """), {
                "ala": alert_a_id, "ca": camera_a_id,
                "alb": alert_b_id, "cb": camera_b_id,
            })

    return {
        "org_a_id": org_a_id,
        "org_b_id": org_b_id,
        "site_a_id": site_a_id,
        "site_b_id": site_b_id,
        "camera_a_id": camera_a_id,
        "camera_b_id": camera_b_id,
        "user_a_id": user_a_id,
        "user_b_id": user_b_id,
        "superadmin_user_id": superadmin_user_id,
        "alert_a_id": alert_a_id,
        "alert_b_id": alert_b_id,
        "user_a_context": {"sub": user_a_id, "role": Role.ORG_ADMIN.value, "org_id": org_a_id},
        "user_b_context": {"sub": user_b_id, "role": Role.ORG_ADMIN.value, "org_id": org_b_id},
        "superadmin_context": {"sub": superadmin_user_id, "role": Role.SUPERADMIN.value, "org_id": None},
    }


@pytest.mark.asyncio
async def test_incident_creation_and_retrieval(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    # 1. Create incident as ORG_ADMIN in Org A
    create_data = {
        "title": "Unauthorized Perimeter Entry",
        "description": "Intruder detected on West Perimeter",
        "severity": "high",
        "site_id": ctx["site_a_id"],
        "camera_id": ctx["camera_a_id"],
        "source_type": "alert",
        "alert_ids": [ctx["alert_a_id"]],
    }
    result = await incident_service.create_incident(create_data, user_a)
    inc = result["incident"]

    assert inc["title"] == "Unauthorized Perimeter Entry"
    assert inc["organization_id"] == ctx["org_a_id"]
    assert inc["severity"] == "high"
    assert inc["status"] == "open"
    assert len(result["linked_alerts"]) == 1
    assert result["linked_alerts"][0]["alert_id"] == ctx["alert_a_id"]

    # 2. Retrieve incident
    get_res = await incident_service.get_incident(inc["id"], user_a)
    assert get_res["incident"]["id"] == inc["id"]
    assert get_res["incident"]["title"] == "Unauthorized Perimeter Entry"


@pytest.mark.asyncio
async def test_incident_listing_and_filtering(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    # Create 2 incidents in Org A
    await incident_service.create_incident({"title": "Inc 1", "severity": "low"}, user_a)
    await incident_service.create_incident({"title": "Inc 2", "severity": "critical"}, user_a)

    list_res = await incident_service.list_incidents(user=user_a)
    assert len(list_res) >= 2

    # Filter by severity
    crit_res = await incident_service.list_incidents(user=user_a, severity="critical")
    assert all(i["severity"] == "critical" for i in crit_res)


@pytest.mark.asyncio
async def test_organization_isolation(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]
    user_b = ctx["user_b_context"]

    # Create incident in Org A
    inc = (await incident_service.create_incident({"title": "Org A Incident"}, user_a))["incident"]

    # Org Admin B attempts to access Org A incident -> rejected (403)
    with pytest.raises(HTTPException) as exc_info:
        await incident_service.get_incident(inc["id"], user_b)
    assert exc_info.value.status_code == 403

    # Org Admin B attempts to list Org A incidents by specifying org_a_id -> rejected (403)
    with pytest.raises(HTTPException) as exc_info:
        await incident_service.list_incidents(user=user_b, organization_id=ctx["org_a_id"])
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_superadmin_global_access(incident_service, setup_test_data):
    ctx = setup_test_data
    superadmin = ctx["superadmin_context"]
    user_a = ctx["user_a_context"]

    # Org A creates incident
    inc = (await incident_service.create_incident({"title": "Org A Incident for Superadmin"}, user_a))["incident"]

    # SUPERADMIN can retrieve Org A incident
    res = await incident_service.get_incident(inc["id"], superadmin)
    assert res["incident"]["id"] == inc["id"]

    # SUPERADMIN can create incident for Org B by supplying organization_id
    create_b = {
        "title": "Superadmin Created Inc in Org B",
        "organization_id": ctx["org_b_id"],
        "severity": "medium",
    }
    res_b = await incident_service.create_incident(create_b, superadmin)
    assert res_b["incident"]["organization_id"] == ctx["org_b_id"]


@pytest.mark.asyncio
async def test_cross_org_assignee_rejection(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    inc = (await incident_service.create_incident({"title": "Assignee Test"}, user_a))["incident"]

    # Org Admin A attempts to assign User B (from Org B) -> rejected (400)
    with pytest.raises(HTTPException) as exc_info:
        await incident_service.assign_incident(inc["id"], ctx["user_b_id"], user_a)
    assert exc_info.value.status_code == 400
    assert "Assigned user does not belong" in exc_info.value.detail


@pytest.mark.asyncio
async def test_incident_status_transitions_and_timestamps(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    inc = (await incident_service.create_incident({"title": "Status Workflow Test"}, user_a))["incident"]
    inc_id = inc["id"]

    assert inc["status"] == "open"
    assert inc["acknowledged_at"] is None

    # Transition: open -> acknowledged
    res_ack = await incident_service.update_status(inc_id, "acknowledged", user_a)
    assert res_ack["incident"]["status"] == "acknowledged"
    assert res_ack["incident"]["acknowledged_at"] is not None

    # Transition: acknowledged -> investigating
    res_inv = await incident_service.update_status(inc_id, "investigating", user_a)
    assert res_inv["incident"]["status"] == "investigating"
    assert res_inv["incident"]["investigating_at"] is not None

    # Transition: investigating -> resolved
    res_res = await incident_service.update_status(inc_id, "resolved", user_a)
    assert res_res["incident"]["status"] == "resolved"
    assert res_res["incident"]["resolved_at"] is not None

    # Transition: resolved -> closed
    res_cls = await incident_service.update_status(inc_id, "closed", user_a)
    assert res_cls["incident"]["status"] == "closed"
    assert res_cls["incident"]["closed_at"] is not None


@pytest.mark.asyncio
async def test_invalid_status_transition_rejection(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    inc = (await incident_service.create_incident({"title": "Invalid Transition Test"}, user_a))["incident"]
    inc_id = inc["id"]

    # Attempt transition from open directly to closed (if closed requires resolved)
    with pytest.raises(HTTPException) as exc_info:
        await incident_service.update_status(inc_id, "closed", user_a)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_alert_linking_unlinking_and_deduplication(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    inc = (await incident_service.create_incident({"title": "Alert Link Test"}, user_a))["incident"]
    inc_id = inc["id"]
    alert_a = ctx["alert_a_id"]

    # Link Alert A
    link_res = await incident_service.link_alert(inc_id, alert_a, user_a)
    assert len(link_res["linked_alerts"]) == 1

    # Duplicate link attempt should not error or create duplicates
    link_res_dup = await incident_service.link_alert(inc_id, alert_a, user_a)
    assert len(link_res_dup["linked_alerts"]) == 1

    # Unlink Alert A
    unlink_res = await incident_service.unlink_alert(inc_id, alert_a, user_a)
    assert len(unlink_res["linked_alerts"]) == 0


@pytest.mark.asyncio
async def test_nonexistent_resources(incident_service, setup_test_data):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    # Nonexistent incident
    with pytest.raises(HTTPException) as exc_info:
        await incident_service.get_incident(str(uuid.uuid4()), user_a)
    assert exc_info.value.status_code == 404

    # Link nonexistent alert
    inc = (await incident_service.create_incident({"title": "Link Nonexistent Alert"}, user_a))["incident"]
    with pytest.raises(HTTPException) as exc_info:
        await incident_service.link_alert(inc["id"], str(uuid.uuid4()), user_a)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_audit_log_entries_created(incident_service, setup_test_data, session_factory):
    ctx = setup_test_data
    user_a = ctx["user_a_context"]

    inc = (await incident_service.create_incident({"title": "Audit Test Incident"}, user_a))["incident"]
    await incident_service.update_status(inc["id"], "acknowledged", user_a)
    await incident_service.assign_incident(inc["id"], ctx["user_a_id"], user_a)

    async with session_factory() as session:
        rows = await session.execute(text("""
            SELECT action FROM audit_log WHERE entity_id = :id ORDER BY timestamp ASC
        """), {"id": inc["id"]})
        actions = [r.action for r in rows.fetchall()]

        assert "incident_created" in actions
        assert "incident_status_changed" in actions
        assert "incident_assigned" in actions
