import os
import uuid
import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from services.audit.src.service import AuditService, SettingsService
from services.audit.src.schemas import OrganizationUpdate
from services.camera_registry.src.schemas import OrganizationCreate
from services.camera_registry.src.service import CameraRegistryService


class DummyRedis:
    async def publish(self, channel, message):
        pass


@pytest_asyncio.fixture
async def session_factory():
    db_url = os.getenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform")
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5432")

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def camera_service(session_factory):
    yield CameraRegistryService(session_factory, DummyRedis())


@pytest_asyncio.fixture
async def settings_service(session_factory):
    yield SettingsService(session_factory)


@pytest_asyncio.fixture
async def audit_service(session_factory):
    yield AuditService(session_factory)


@pytest.mark.asyncio
async def test_superadmin_access_global_settings(camera_service, settings_service):
    org = await camera_service.create_organization(OrganizationCreate(name="Global Set Org", code=f"gset_{uuid.uuid4().hex[:6]}"))
    org_id = str(org["id"])

    superadmin = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}

    res = await settings_service.get_settings(user=superadmin, target_org_id=org_id)
    assert res.organization is not None
    assert res.organization.id == org_id
    assert res.organization.name == "Global Set Org"
    assert res.platform.platform_name is not None
    assert res.security.auth_provider is not None


@pytest.mark.asyncio
async def test_org_admin_access_own_organization_settings(camera_service, settings_service):
    org = await camera_service.create_organization(OrganizationCreate(name="Org Admin Set Org", code=f"oaset_{uuid.uuid4().hex[:6]}"))
    org_id = str(org["id"])

    org_admin = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_id}

    res = await settings_service.get_settings(user=org_admin)
    assert res.organization is not None
    assert res.organization.id == org_id
    assert res.organization.name == "Org Admin Set Org"


@pytest.mark.asyncio
async def test_org_admin_cannot_access_other_org_settings(camera_service, settings_service):
    org_a = await camera_service.create_organization(OrganizationCreate(name="Set Org A", code=f"seta_{uuid.uuid4().hex[:6]}"))
    org_b = await camera_service.create_organization(OrganizationCreate(name="Set Org B", code=f"setb_{uuid.uuid4().hex[:6]}"))

    org_a_id = str(org_a["id"])
    org_b_id = str(org_b["id"])

    org_admin_a = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_a_id}

    with pytest.raises(HTTPException) as exc_info:
        await settings_service.get_settings(user=org_admin_a, target_org_id=org_b_id)

    assert exc_info.value.status_code == 403
    assert "Cross-organization settings access forbidden" in exc_info.value.detail


@pytest.mark.asyncio
async def test_organization_settings_update_flow(camera_service, settings_service, audit_service):
    org = await camera_service.create_organization(OrganizationCreate(name="Initial Org Name", code=f"upd_{uuid.uuid4().hex[:6]}"))
    org_id = str(org["id"])

    user_id = str(uuid.uuid4())
    org_admin = {"sub": user_id, "role": "org_admin", "org_id": org_id}

    # Update name and timezone
    update_req = OrganizationUpdate(name="Updated Enterprise Org", timezone="America/New_York")
    updated_org = await settings_service.update_organization_settings(user=org_admin, update_data=update_req)

    assert updated_org.id == org_id
    assert updated_org.name == "Updated Enterprise Org"
    assert updated_org.timezone == "America/New_York"

    # Verify persistent DB state
    settings_after = await settings_service.get_settings(user=org_admin)
    assert settings_after.organization.name == "Updated Enterprise Org"
    assert settings_after.organization.timezone == "America/New_York"

    # Verify audit log entry was written
    superadmin = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}
    audit_res = await audit_service.list_audit_logs(user=superadmin, action="organization_updated", page=1, page_size=10)
    assert audit_res.total >= 1
    org_audit_entry = next((item for item in audit_res.items if item.resource_id == org_id), None)
    assert org_audit_entry is not None
    assert org_audit_entry.metadata.get("new_name") == "Updated Enterprise Org"
    assert org_audit_entry.metadata.get("new_timezone") == "America/New_York"


@pytest.mark.asyncio
async def test_org_admin_cannot_update_other_org_settings(camera_service, settings_service):
    org_a = await camera_service.create_organization(OrganizationCreate(name="Org X", code=f"orgx_{uuid.uuid4().hex[:6]}"))
    org_b = await camera_service.create_organization(OrganizationCreate(name="Org Y", code=f"orgy_{uuid.uuid4().hex[:6]}"))

    org_a_id = str(org_a["id"])
    org_b_id = str(org_b["id"])

    org_admin_a = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_a_id}

    with pytest.raises(HTTPException) as exc_info:
        await settings_service.update_organization_settings(
            user=org_admin_a,
            update_data=OrganizationUpdate(name="Hacked Name"),
            target_org_id=org_b_id
        )

    assert exc_info.value.status_code == 403
    assert "Cross-organization settings update forbidden" in exc_info.value.detail
