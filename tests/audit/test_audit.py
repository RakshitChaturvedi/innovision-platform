import os
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from services.audit.src.service import AuditService
from services.audit.src.writer import write_audit_entry
from services.camera_registry.src.schemas import OrganizationCreate
from services.camera_registry.src.service import CameraRegistryService


class DummyRedis:
    async def publish(self, channel, message):
        pass


@pytest_asyncio.fixture
async def session_factory():
    db_url = os.getenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform")
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5433")

    engine = create_async_engine(db_url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def camera_service(session_factory):
    yield CameraRegistryService(session_factory, DummyRedis())


@pytest_asyncio.fixture
async def audit_service(session_factory):
    yield AuditService(session_factory)


@pytest.mark.asyncio
async def test_superadmin_view_global_audit(session_factory, audit_service, camera_service):
    # Setup test orgs and audit entries
    org_a = await camera_service.create_organization(OrganizationCreate(name="Audit Test Org A", code=f"aud_a_{uuid.uuid4().hex[:6]}"))
    org_b = await camera_service.create_organization(OrganizationCreate(name="Audit Test Org B", code=f"aud_b_{uuid.uuid4().hex[:6]}"))

    org_a_id = str(org_a["id"])
    org_b_id = str(org_b["id"])

    # Write audit log entries for both orgs
    await write_audit_entry(
        session_factory=session_factory,
        service="auth",
        action="user_login",
        entity_type="user",
        entity_id=str(uuid.uuid4()),
        metadata={"organization_id": org_a_id}
    )
    await write_audit_entry(
        session_factory=session_factory,
        service="camera_registry",
        action="camera_created",
        entity_type="camera",
        entity_id=str(uuid.uuid4()),
        metadata={"organization_id": org_b_id}
    )

    superadmin_user = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}

    # Global view
    response = await audit_service.list_audit_logs(user=superadmin_user, page=1, page_size=50)
    assert response.total >= 2
    assert len(response.items) >= 2


@pytest.mark.asyncio
async def test_superadmin_filter_by_organization(session_factory, audit_service, camera_service):
    org_c = await camera_service.create_organization(OrganizationCreate(name="Audit Test Org C", code=f"aud_c_{uuid.uuid4().hex[:6]}"))
    org_c_id = str(org_c["id"])

    unique_cam_id = str(uuid.uuid4())
    await write_audit_entry(
        session_factory=session_factory,
        service="camera_registry",
        action="camera_updated",
        entity_type="camera",
        entity_id=unique_cam_id,
        metadata={"organization_id": org_c_id, "test_marker": "org_c_marker"}
    )

    superadmin_user = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}

    # Filter by org C
    response = await audit_service.list_audit_logs(user=superadmin_user, organization_id=org_c_id, page=1, page_size=50)
    assert response.total >= 1
    org_c_item_ids = [item.resource_id for item in response.items]
    assert unique_cam_id in org_c_item_ids


@pytest.mark.asyncio
async def test_org_admin_view_own_organization_audit(session_factory, audit_service, camera_service):
    org_d = await camera_service.create_organization(OrganizationCreate(name="Audit Test Org D", code=f"aud_d_{uuid.uuid4().hex[:6]}"))
    org_d_id = str(org_d["id"])

    user_id = str(uuid.uuid4())
    # Create user in org D
    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("""
                INSERT INTO users (id, name, email, password_hash, role, organization_id, is_active, created_at, updated_at)
                VALUES (:id, 'Org Admin D', :email, 'hash', 'org_admin', :org_id, true, now(), now())
            """), {
                "id": user_id,
                "email": f"orgd_{uuid.uuid4().hex[:6]}@test.com",
                "org_id": org_d_id
            })

    unique_action = f"zone_created_{uuid.uuid4().hex[:6]}"
    await write_audit_entry(
        session_factory=session_factory,
        service="camera_registry",
        action=unique_action,
        entity_type="zone",
        entity_id=str(uuid.uuid4()),
        user_id=user_id,
        metadata={"organization_id": org_d_id}
    )

    org_admin_d = {"sub": user_id, "role": "org_admin", "org_id": org_d_id}

    response = await audit_service.list_audit_logs(user=org_admin_d, page=1, page_size=50)
    actions = [item.action for item in response.items]
    assert unique_action in actions


@pytest.mark.asyncio
async def test_org_admin_cannot_access_other_organization_audit(session_factory, audit_service, camera_service):
    org_e = await camera_service.create_organization(OrganizationCreate(name="Audit Test Org E", code=f"aud_e_{uuid.uuid4().hex[:6]}"))
    org_f = await camera_service.create_organization(OrganizationCreate(name="Audit Test Org F", code=f"aud_f_{uuid.uuid4().hex[:6]}"))

    org_e_id = str(org_e["id"])
    org_f_id = str(org_f["id"])

    org_admin_e = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_e_id}

    # Attempting to explicitly query Org F audit logs when authenticated as Org E admin
    with pytest.raises(HTTPException) as exc_info:
        await audit_service.list_audit_logs(user=org_admin_e, organization_id=org_f_id, page=1, page_size=20)

    assert exc_info.value.status_code == 403
    assert "Cross-organization audit access forbidden" in exc_info.value.detail


@pytest.mark.asyncio
async def test_audit_pagination_and_filtering(session_factory, audit_service):
    unique_tag = f"page_test_{uuid.uuid4().hex[:6]}"
    for i in range(5):
        await write_audit_entry(
            session_factory=session_factory,
            service="test_service",
            action=f"action_{unique_tag}",
            entity_type="test_resource",
            entity_id=f"id_{unique_tag}_{i}",
            metadata={"index": i}
        )

    superadmin = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}

    # Page 1 with page_size=2
    res_p1 = await audit_service.list_audit_logs(user=superadmin, action=f"action_{unique_tag}", page=1, page_size=2)
    assert res_p1.total == 5
    assert len(res_p1.items) == 2
    assert res_p1.total_pages == 3
    assert res_p1.page == 1

    # Search filter
    res_search = await audit_service.list_audit_logs(user=superadmin, search=unique_tag, page=1, page_size=10)
    assert res_search.total == 5


@pytest.mark.asyncio
async def test_audit_detail_fetch(session_factory, audit_service):
    entry_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("""
                INSERT INTO audit_log (id, service, action, entity_type, entity_id, user_id, source_uc, metadata, timestamp)
                VALUES (:id, 'incident_management', 'incident_created', 'incident', 'inc-101', NULL, NULL, :meta, now())
            """), {
                "id": entry_id,
                "meta": f'{{"organization_id": "{org_id}", "severity": "high"}}'
            })

    superadmin = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}

    detail = await audit_service.get_audit_log(entry_id=entry_id, user=superadmin)
    assert detail.id == entry_id
    assert detail.service == "incident_management"
    assert detail.action == "incident_created"
    assert detail.resource_type == "incident"
    assert detail.resource_id == "inc-101"
    assert detail.metadata.get("severity") == "high"
