import os
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from services.notification.src.service import (
    NotificationService,
    create_user_notification,
    dispatch_alert_notifications,
    dispatch_incident_assigned_notification,
    dispatch_incident_status_notification,
)
from services.notification.src.schemas import NotificationPreferenceUpdate
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
async def notification_service(session_factory):
    yield NotificationService(session_factory)


@pytest_asyncio.fixture
async def setup_test_data(session_factory):
    """Creates Org A, Org B, Users, Sites, Zones, Cameras for testing."""
    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())

    user_a1_id = str(uuid.uuid4())
    user_a2_id = str(uuid.uuid4())
    user_b1_id = str(uuid.uuid4())
    superadmin_id = str(uuid.uuid4())

    site_a_id = str(uuid.uuid4())
    zone_a_id = str(uuid.uuid4())
    camera_a_id = str(uuid.uuid4())

    async with session_factory() as session:
        async with session.begin():
            # Create Orgs
            await session.execute(
                text("""
                    INSERT INTO organizations (id, name, code, created_at, updated_at)
                    VALUES (:oa, 'Notif Org A', :code_a, now(), now()),
                           (:ob, 'Notif Org B', :code_b, now(), now())
                """),
                {
                    "oa": org_a_id, "code_a": f"notif_a_{uuid.uuid4().hex[:6]}",
                    "ob": org_b_id, "code_b": f"notif_b_{uuid.uuid4().hex[:6]}"
                }
            )

            # Create Users
            await session.execute(
                text("""
                    INSERT INTO users (id, organization_id, email, password_hash, name, role, is_active, created_at, updated_at)
                    VALUES
                        (:u_a1, :oa, :e_a1, 'hash', 'Org A Admin 1', 'org_admin', true, now(), now()),
                        (:u_a2, :oa, :e_a2, 'hash', 'Org A Admin 2', 'org_admin', true, now(), now()),
                        (:u_b1, :ob, :e_b1, 'hash', 'Org B Admin 1', 'org_admin', true, now(), now()),
                        (:u_sa, NULL, :e_sa, 'hash', 'Global Superadmin', 'superadmin', true, now(), now())
                """),
                {
                    "u_a1": user_a1_id, "oa": org_a_id, "e_a1": f"a1_{uuid.uuid4().hex[:6]}@test.com",
                    "u_a2": user_a2_id, "e_a2": f"a2_{uuid.uuid4().hex[:6]}@test.com",
                    "u_b1": user_b1_id, "ob": org_b_id, "e_b1": f"b1_{uuid.uuid4().hex[:6]}@test.com",
                    "u_sa": superadmin_id, "e_sa": f"sa_{uuid.uuid4().hex[:6]}@test.com",
                }
            )

            # Create Site, Zone, Camera in Org A
            await session.execute(
                text("""
                    INSERT INTO sites (id, organization_id, name, code, created_at, updated_at)
                    VALUES (:s_a, :oa, 'Notif Site A', :site_code, now(), now())
                """),
                {"s_a": site_a_id, "oa": org_a_id, "site_code": f"site_{uuid.uuid4().hex[:6]}"}
            )

            await session.execute(
                text("""
                    INSERT INTO zones (id, site_id, name, slug, created_at, updated_at)
                    VALUES (:z_a, :s_a, 'Notif Zone A', :slug_a, now(), now())
                """),
                {"z_a": zone_a_id, "s_a": site_a_id, "slug_a": f"notif_zone_{uuid.uuid4().hex[:8]}"}
            )

            await session.execute(
                text("""
                    INSERT INTO cameras (id, organization_id, site_id, zone_id, name, rtsp_url, created_at, updated_at)
                    VALUES (:c_a, :oa, :s_a, :z_a, 'CAM-NOTIF-01', 'rtsp://localhost/stream', now(), now())
                """),
                {"c_a": camera_a_id, "oa": org_a_id, "s_a": site_a_id, "z_a": zone_a_id}
            )

    return {
        "org_a_id": org_a_id,
        "org_b_id": org_b_id,
        "user_a1": {"sub": user_a1_id, "role": Role.ORG_ADMIN, "org_id": org_a_id},
        "user_a2": {"sub": user_a2_id, "role": Role.ORG_ADMIN, "org_id": org_a_id},
        "user_b1": {"sub": user_b1_id, "role": Role.ORG_ADMIN, "org_id": org_b_id},
        "superadmin": {"sub": superadmin_id, "role": Role.SUPERADMIN},
        "camera_a_id": camera_a_id,
    }


@pytest.mark.asyncio
async def test_notification_creation_and_list(session_factory, notification_service, setup_test_data):
    user = setup_test_data["user_a1"]

    # 1. Create notification
    n = await create_user_notification(
        session_factory=session_factory,
        recipient_user_id=user["sub"],
        organization_id=user["org_id"],
        type_str="critical_alert",
        title="Critical Intruders Detected",
        message="Unauthorized entry in Zone A",
        severity="critical",
        resource_type="alert",
        resource_id=str(uuid.uuid4()),
        metadata={"camera_name": "CAM-NOTIF-01"},
    )
    assert n is not None
    assert n["recipient_user_id"] == user["sub"]
    assert n["is_read"] is False

    # 2. List notifications
    res = await notification_service.list_notifications(user=user, page=1, page_size=10)
    assert res.total >= 1
    assert res.unread_count >= 1
    found = any(item.id == n["id"] for item in res.items)
    assert found

    # 3. Unread count endpoint
    unread_res = await notification_service.get_unread_count(user=user)
    assert unread_res.unread_count >= 1


@pytest.mark.asyncio
async def test_alert_notification_dispatch(session_factory, notification_service, setup_test_data):
    user_a1 = setup_test_data["user_a1"]
    user_a2 = setup_test_data["user_a2"]
    user_b1 = setup_test_data["user_b1"]
    camera_a_id = setup_test_data["camera_a_id"]

    alert_row = {
        "id": str(uuid.uuid4()),
        "alert_id": str(uuid.uuid4()),
        "camera_id": camera_a_id,
        "title": "Unattended Smoke Detected",
        "severity": "critical",
        "source_uc": "uc2",
    }

    # Dispatch notifications for critical alert
    await dispatch_alert_notifications(session_factory, alert_row)

    # Org A admins (User A1 and User A2) should have received notifications
    res_a1 = await notification_service.list_notifications(user=user_a1)
    res_a2 = await notification_service.list_notifications(user=user_a2)
    res_b1 = await notification_service.list_notifications(user=user_b1)

    assert any("Smoke" in n.title for n in res_a1.items)
    assert any("Smoke" in n.title for n in res_a2.items)
    # Org B admin should NOT receive Org A's notification
    assert not any("Smoke" in n.title for n in res_b1.items)


@pytest.mark.asyncio
async def test_incident_notification_dispatch(session_factory, notification_service, setup_test_data):
    user_a1 = setup_test_data["user_a1"]

    inc_dict = {
        "id": str(uuid.uuid4()),
        "organization_id": user_a1["org_id"],
        "title": "Main Gate Barrier Jam",
        "severity": "high",
        "status": "open",
        "assigned_to": user_a1["sub"],
    }

    # Test Assignment notification
    await dispatch_incident_assigned_notification(session_factory, inc_dict, user_a1["sub"])

    res = await notification_service.list_notifications(user=user_a1)
    assert any(n.type == "incident_assigned" for n in res.items)

    # Test Status change notification
    await dispatch_incident_status_notification(session_factory, inc_dict, old_status="open", new_status="investigating")

    res_after = await notification_service.list_notifications(user=user_a1)
    assert any(n.type == "incident_status_changed" for n in res_after.items)


@pytest.mark.asyncio
async def test_mark_as_read_and_read_all(session_factory, notification_service, setup_test_data):
    user = setup_test_data["user_a1"]

    n1 = await create_user_notification(session_factory, user["sub"], user["org_id"], "high_alert", "High Alert 1", "Msg 1")
    n2 = await create_user_notification(session_factory, user["sub"], user["org_id"], "high_alert", "High Alert 2", "Msg 2")

    # Mark single notification as read
    read_item = await notification_service.mark_as_read(user=user, notification_id=n1["id"])
    assert read_item.is_read is True
    assert read_item.read_at is not None

    # Idempotent mark as read again
    read_again = await notification_service.mark_as_read(user=user, notification_id=n1["id"])
    assert read_again.is_read is True

    # Mark all as read
    await notification_service.mark_all_as_read(user=user)
    unread_res = await notification_service.get_unread_count(user=user)
    assert unread_res.unread_count == 0


@pytest.mark.asyncio
async def test_user_and_tenant_notification_isolation(session_factory, notification_service, setup_test_data):
    user_a1 = setup_test_data["user_a1"]
    user_b1 = setup_test_data["user_b1"]

    # Create notification for User A1
    n_a1 = await create_user_notification(session_factory, user_a1["sub"], user_a1["org_id"], "critical_alert", "Org A Alert", "Secret Org A msg")

    # User B1 tries to mark User A1's notification as read -> 404 / access denied
    with pytest.raises(HTTPException) as exc_info:
        await notification_service.mark_as_read(user=user_b1, notification_id=n_a1["id"])
    assert exc_info.value.status_code == 404

    # User B1 list_notifications does NOT contain User A1's notification
    res_b1 = await notification_service.list_notifications(user=user_b1)
    assert not any(item.id == n_a1["id"] for item in res_b1.items)


@pytest.mark.asyncio
async def test_notification_preferences(session_factory, notification_service, setup_test_data):
    user = setup_test_data["user_a1"]

    # 1. Fetch default preferences
    prefs = await notification_service.get_user_preferences(user=user)
    assert len(prefs) >= 4
    crit_pref = next(p for p in prefs if p.notification_type == "critical_alert")
    assert crit_pref.in_app_enabled is True

    # 2. Update preference to disable in-app for critical_alert
    updated_prefs = await notification_service.update_user_preferences(
        user=user,
        update_items=[
            NotificationPreferenceUpdate(notification_type="critical_alert", in_app_enabled=False, email_enabled=False)
        ]
    )

    crit_updated = next(p for p in updated_prefs if p.notification_type == "critical_alert")
    assert crit_updated.in_app_enabled is False
    assert crit_updated.email_enabled is False

    # 3. Creating critical_alert when in_app_enabled is False should NOT persist notification
    n = await create_user_notification(
        session_factory=session_factory,
        recipient_user_id=user["sub"],
        organization_id=user["org_id"],
        type_str="critical_alert",
        title="Disabled Crit Alert",
        message="Should not be stored",
    )
    # The record should not be stored in DB (in_app_enabled = False)
    async with session_factory() as session:
        res = await session.execute(
            text("SELECT * FROM notifications WHERE id = :id"),
            {"id": n["id"]}
        )
        assert res.fetchone() is None

    # 4. Verify audit event was created
    async with session_factory() as session:
        audit_res = await session.execute(
            text("SELECT * FROM audit_log WHERE action = 'notification_preferences_updated' AND user_id::text = :uid"),
            {"uid": str(user["sub"])}
        )
        assert audit_res.fetchone() is not None


@pytest.mark.asyncio
async def test_notification_idempotency(session_factory, notification_service, setup_test_data):
    user = setup_test_data["user_a1"]
    res_id = str(uuid.uuid4())

    # First call
    n1 = await create_user_notification(
        session_factory=session_factory,
        recipient_user_id=user["sub"],
        organization_id=user["org_id"],
        type_str="critical_alert",
        title="Deduplication Test Alert",
        message="Message 1",
        severity="critical",
        resource_type="alert",
        resource_id=res_id,
    )

    # Second call with exact same parameters (retry)
    n2 = await create_user_notification(
        session_factory=session_factory,
        recipient_user_id=user["sub"],
        organization_id=user["org_id"],
        type_str="critical_alert",
        title="Deduplication Test Alert",
        message="Message 1",
        severity="critical",
        resource_type="alert",
        resource_id=res_id,
    )

    assert n1["id"] == n2["id"]
    assert n2.get("is_duplicate") is True

    # Verify database has exactly 1 record for this resource_id
    async with session_factory() as session:
        res = await session.execute(
            text("SELECT COUNT(*) FROM notifications WHERE recipient_user_id = :uid AND resource_id = :rid"),
            {"uid": user["sub"], "rid": res_id}
        )
        count = res.scalar()
        assert count == 1


@pytest.mark.asyncio
async def test_superadmin_notification_scope(session_factory, notification_service, setup_test_data):
    user_a1 = setup_test_data["user_a1"]
    user_b1 = setup_test_data["user_b1"]
    superadmin = setup_test_data["superadmin"]
    camera_a_id = setup_test_data["camera_a_id"]

    alert_row = {
        "id": str(uuid.uuid4()),
        "alert_id": str(uuid.uuid4()),
        "camera_id": camera_a_id,
        "title": "Superadmin Scope Alert Test",
        "severity": "critical",
        "source_uc": "uc1",
    }

    # Dispatch critical alert
    await dispatch_alert_notifications(session_factory, alert_row)

    # Check recipient notifications
    res_a1 = await notification_service.list_notifications(user=user_a1)
    res_sa = await notification_service.list_notifications(user=superadmin)
    res_b1 = await notification_service.list_notifications(user=user_b1)

    # Org A Admin receives it
    assert any("Superadmin Scope" in n.title for n in res_a1.items)
    # Global Superadmin receives it
    assert any("Superadmin Scope" in n.title for n in res_sa.items)
    # Org B Admin does NOT receive it
    assert not any("Superadmin Scope" in n.title for n in res_b1.items)


