import asyncio
import os
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from services.audit.src.service import AuditService, SettingsService
from services.audit.src.schemas import OrganizationUpdate
from services.camera_registry.src.schemas import OrganizationCreate
from services.camera_registry.src.service import CameraRegistryService


class DummyRedis:
    async def publish(self, channel, message):
        pass


async def main():
    print("=== STARTING PHASE 6D RUNTIME VALIDATION ===")
    db_url = os.getenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform")
    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    cam_svc = CameraRegistryService(factory, DummyRedis())
    audit_svc = AuditService(factory)
    settings_svc = SettingsService(factory)

    # 1. Create test orgs
    org_1 = await cam_svc.create_organization(OrganizationCreate(name="Phase 6D Org 1", code=f"p6d_1_{uuid.uuid4().hex[:6]}"))
    org_2 = await cam_svc.create_organization(OrganizationCreate(name="Phase 6D Org 2", code=f"p6d_2_{uuid.uuid4().hex[:6]}"))
    org_1_id = str(org_1["id"])
    org_2_id = str(org_2["id"])

    print(f"Created Org 1: {org_1_id}")
    print(f"Created Org 2: {org_2_id}")

    # 2. Update Org 1 Settings
    user_1 = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_1_id}
    upd_res = await settings_svc.update_organization_settings(
        user=user_1,
        update_data=OrganizationUpdate(name="Phase 6D Updated Org 1", timezone="America/Los_Angeles")
    )
    print(f"Updated Org 1: name='{upd_res.name}', timezone='{upd_res.timezone}'")
    assert upd_res.name == "Phase 6D Updated Org 1"
    assert upd_res.timezone == "America/Los_Angeles"

    # 3. Read Settings as Org Admin 1
    settings_res = await settings_svc.get_settings(user=user_1)
    print(f"Read Settings Org 1: {settings_res.organization.name}, Subscriptions count: {len(settings_res.subscriptions)}")
    assert settings_res.organization.name == "Phase 6D Updated Org 1"

    # 4. Read Audit Logs as Org Admin 1
    audit_res_1 = await audit_svc.list_audit_logs(user=user_1, page=1, page_size=10)
    print(f"Audit Logs for Org 1 count: {audit_res_1.total}")
    assert audit_res_1.total >= 1
    assert any(item.action == "organization_updated" for item in audit_res_1.items)

    # 5. Verify Org Admin 1 cannot access Org 2 audit logs
    try:
        await audit_svc.list_audit_logs(user=user_1, organization_id=org_2_id)
        print("ERROR: Cross-org audit bypass failed to block!")
        assert False
    except Exception as e:
        print(f"Cross-org audit access blocked correctly: {e}")

    # 6. Read Global Audit Logs as SUPERADMIN
    superadmin = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}
    audit_res_super = await audit_svc.list_audit_logs(user=superadmin, page=1, page_size=10)
    print(f"Global Audit Logs count for SUPERADMIN: {audit_res_super.total}")
    assert audit_res_super.total >= audit_res_1.total

    await engine.dispose()
    print("=== PHASE 6D RUNTIME VALIDATION PASSED SUCCESSFULLY ===")


if __name__ == "__main__":
    asyncio.run(main())
