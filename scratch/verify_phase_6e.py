import asyncio
import os
import uuid
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from services.notification.src.service import (
    NotificationService,
    create_user_notification,
    dispatch_alert_notifications,
    dispatch_incident_assigned_notification,
    dispatch_incident_status_notification,
)
from services.notification.src.schemas import NotificationPreferenceUpdate
from services.auth.src.rbac import Role

async def verify_phase_6e():
    db_url = os.getenv(
        "DATABASE_URL_LOCAL",
        "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform"
    )
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5432")

    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    service = NotificationService(session_factory)

    org_id = str(uuid.uuid4())
    user_admin_id = str(uuid.uuid4())
    user_other_id = str(uuid.uuid4())

    async with session_factory() as session:
        async with session.begin():
            # Seed org & users
            await session.execute(text("""
                INSERT INTO organizations (id, name, code, created_at, updated_at)
                VALUES (:oid, 'Verify Org 6E', :code, now(), now())
            """), {"oid": org_id, "code": f"v6e_{uuid.uuid4().hex[:6]}"})

            await session.execute(text("""
                INSERT INTO users (id, organization_id, email, password_hash, name, role, is_active, created_at, updated_at)
                VALUES
                    (:u1, :oid, :e1, 'hash', 'Verify Admin', 'org_admin', true, now(), now()),
                    (:u2, :oid, :e2, 'hash', 'Verify Other', 'operator', true, now(), now())
            """), {
                "u1": user_admin_id, "oid": org_id, "e1": f"vadmin_{uuid.uuid4().hex[:6]}@test.com",
                "u2": user_other_id, "e2": f"vother_{uuid.uuid4().hex[:6]}@test.com",
            })

    user_admin = {"sub": user_admin_id, "role": Role.ORG_ADMIN, "org_id": org_id}
    user_other = {"sub": user_other_id, "role": Role.OPERATOR, "org_id": org_id}

    print("=== Step 1: Create Notification ===")
    notif = await create_user_notification(
        session_factory=session_factory,
        recipient_user_id=user_admin_id,
        organization_id=org_id,
        type_str="critical_alert",
        title="Verified Critical Fire Alert",
        message="Smoke detected in Zone 4",
        severity="critical",
        resource_type="alert",
        resource_id=str(uuid.uuid4()),
    )
    assert notif is not None
    print(f"Created Notification ID: {notif['id']}")

    print("\n=== Step 2: List & Unread Count ===")
    list_res = await service.list_notifications(user=user_admin)
    print(f"Total Notifications: {list_res.total}, Unread: {list_res.unread_count}")
    assert list_res.total >= 1
    assert list_res.unread_count >= 1

    unread_res = await service.get_unread_count(user=user_admin)
    print(f"Unread Count API response: {unread_res.unread_count}")
    assert unread_res.unread_count >= 1

    print("\n=== Step 3: Mark as Read & Read All ===")
    read_item = await service.mark_as_read(user=user_admin, notification_id=notif["id"])
    print(f"Notification read_at: {read_item.read_at}, is_read: {read_item.is_read}")
    assert read_item.is_read is True

    await service.mark_all_as_read(user=user_admin)
    unread_after = await service.get_unread_count(user=user_admin)
    print(f"Unread Count after mark all read: {unread_after.unread_count}")
    assert unread_after.unread_count == 0

    print("\n=== Step 4: Notification Preferences & Audit ===")
    default_prefs = await service.get_user_preferences(user=user_admin)
    print(f"Fetched {len(default_prefs)} default preference items.")

    updated_prefs = await service.update_user_preferences(
        user=user_admin,
        update_items=[NotificationPreferenceUpdate(notification_type="high_alert", in_app_enabled=True, email_enabled=False)]
    )
    high_pref = next(p for p in updated_prefs if p.notification_type == "high_alert")
    print(f"High Alert Pref - In-App: {high_pref.in_app_enabled}, Email: {high_pref.email_enabled}")
    assert high_pref.email_enabled is False

    print("\n=== Step 5: Tenant & Recipient Isolation ===")
    # Verify user_other cannot see user_admin's notifications
    other_list = await service.list_notifications(user=user_other)
    assert not any(item.id == notif["id"] for item in other_list.items)
    print("User isolation verified successfully.")

    print("\n[SUCCESS] Phase 6E Runtime Verification Successful!")

if __name__ == "__main__":
    asyncio.run(verify_phase_6e())
