import pytest
import uuid
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from services.camera_registry.src.schemas import (
    OrganizationCreate, SiteCreate, ZoneCreate
)
from services.camera_registry.src.service import CameraRegistryService
from services.auth.src.rbac import require_organization_access, Role
from services.auth.src.jwt import create_access_token, decode_access_token, hash_password, verify_password

class DummyRedis:
    async def publish(self, channel, message):
        pass

@pytest_asyncio.fixture
async def session_factory():
    from conftest import get_safe_test_db_url
    db_url = get_safe_test_db_url()
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5433")
    
    engine = create_async_engine(db_url, echo=False, connect_args={"ssl": False})
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()

@pytest_asyncio.fixture
async def service(session_factory):
    redis_client = DummyRedis()
    yield CameraRegistryService(session_factory, redis_client)

@pytest.mark.asyncio
async def test_jwt_token_includes_organization_id():
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    token = create_access_token(user_id, "org_admin", ["cam1"], org_id=org_id)
    decoded = decode_access_token(token)
    
    assert decoded["sub"] == user_id
    assert decoded["role"] == "org_admin"
    assert decoded["org_id"] == org_id

@pytest.mark.asyncio
async def test_superadmin_global_access_bypasses_org_restriction():
    superadmin_user = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}
    org_b_id = str(uuid.uuid4())
    
    checker = require_organization_access(target_org_id=org_b_id)
    res = await checker(user=superadmin_user)
    assert res == superadmin_user

@pytest.mark.asyncio
async def test_org_admin_cross_organization_access_rejected():
    org_a_id = str(uuid.uuid4())
    org_b_id = str(uuid.uuid4())
    
    org_admin_user = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_a_id}
    
    checker = require_organization_access(target_org_id=org_b_id)
    with pytest.raises(HTTPException) as exc_info:
        await checker(user=org_admin_user)
    
    assert exc_info.value.status_code == 403
    assert "Cross-organization access forbidden" in exc_info.value.detail

@pytest.mark.asyncio
async def test_org_admin_same_organization_access_allowed():
    org_a_id = str(uuid.uuid4())
    org_admin_user = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_a_id}
    
    checker = require_organization_access(target_org_id=org_a_id)
    res = await checker(user=org_admin_user)
    assert res == org_admin_user

@pytest.mark.asyncio
async def test_organization_isolation_in_service_policy_updates(service):
    # Setup Org A and Org B
    org_a = await service.create_organization(OrganizationCreate(name="Org Alpha", code=f"alpha_{uuid.uuid4().hex[:6]}"))
    org_b = await service.create_organization(OrganizationCreate(name="Org Beta", code=f"beta_{uuid.uuid4().hex[:6]}"))
    
    org_a_id = str(org_a["id"])
    org_b_id = str(org_b["id"])
    
    site_a = await service.create_site(SiteCreate(name="Site A", code=f"sa_{uuid.uuid4().hex[:6]}", organization_id=uuid.UUID(org_a_id)))
    zone_a = await service.create_zone(ZoneCreate(name="Zone A", zone_type="kiln", site_id=uuid.UUID(str(site_a["id"]))))
    zone_a_id = str(zone_a["id"])

    # Org Admin B attempts to modify Zone A (in Org A)
    user_b = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_b_id}
    
    catalog = await service.list_analytics_catalog()
    analytic_id = catalog[0]["id"]
    
    with pytest.raises(PermissionError) as exc_info:
        await service.update_zone_analytics_policy(
            zone_id=zone_a_id,
            analytic_id=analytic_id,
            is_enabled=True,
            current_user=user_b,
            user_org_id=org_b_id
        )
    
    assert "does not match zone organization" in str(exc_info.value)

@pytest.mark.asyncio
async def test_user_creation_and_deactivation_flow(service, session_factory):
    # Create Organization first
    org = await service.create_organization(OrganizationCreate(name="Org User Test", code=f"org_ut_{uuid.uuid4().hex[:6]}"))
    org_id = str(org["id"])

    user_id = str(uuid.uuid4())
    email = f"user_{uuid.uuid4().hex[:8]}@example.com"
    pw_hash = hash_password("Password123!")

    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("""
                INSERT INTO users (id, name, email, password_hash, role, organization_id, is_active, created_at, updated_at)
                VALUES (:id, :name, :email, :pw_hash, 'org_admin', :org_id, true, now(), now())
            """), {
                "id": user_id,
                "name": "Test Org Admin",
                "email": email,
                "pw_hash": pw_hash,
                "org_id": org_id
            })

    async with session_factory() as session:
        row = await session.execute(text("SELECT email, password_hash, is_active, role FROM users WHERE id = :id"), {"id": user_id})
        res = row.fetchone()
        assert res.email == email
        assert verify_password("Password123!", res.password_hash)
        assert res.is_active is True
        assert res.role == "org_admin"

    # Deactivate user
    async with session_factory() as session:
        async with session.begin():
            await session.execute(text("UPDATE users SET is_active = false WHERE id = :id"), {"id": user_id})

    async with session_factory() as session:
        row = await session.execute(text("SELECT is_active FROM users WHERE id = :id"), {"id": user_id})
        res = row.fetchone()
        assert res.is_active is False
