import pytest
import uuid
from datetime import datetime, timezone, timedelta
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from pydantic import ValidationError

from services.camera_registry.src.schemas import (
    OrganizationCreate, OrganizationSubscriptionCreate, OrganizationSubscriptionUpdate
)
from services.camera_registry.src.service import CameraRegistryService

class DummyRedis:
    async def publish(self, channel, message):
        pass

@pytest_asyncio.fixture
async def service():
    import os
    db_url = os.getenv("DATABASE_URL_LOCAL", "postgresql+asyncpg://innovision:changeme@localhost:5433/innovision_platform")
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5433")
    
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = DummyRedis()
    registry_service = CameraRegistryService(session_factory, redis_client)
    yield registry_service
    await engine.dispose()

@pytest.mark.asyncio
async def test_analytics_catalog_four_analytics_seeded(service):
    catalog = await service.list_analytics_catalog()
    assert len(catalog) >= 4

    internal_codes = {item["internal_code"]: item for item in catalog}
    assert "uc1" in internal_codes
    assert "uc2" in internal_codes
    assert "uc3" in internal_codes
    assert "uc4" in internal_codes

    # Verify UC3 mapping specifically to ppe_detection
    uc3_item = internal_codes["uc3"]
    assert uc3_item["code"] == "ppe_detection"
    assert uc3_item["display_name"] == "PPE Detection"

    # Verify all IDs and internal codes are unique
    ids = [str(item["id"]) for item in catalog]
    assert len(ids) == len(set(ids))
    codes = [item["code"] for item in catalog]
    assert len(codes) == len(set(codes))

@pytest.mark.asyncio
async def test_organization_subscriptions_flow(service):
    # 1. Create Organization
    org_code = f"org_{uuid.uuid4().hex[:8]}"
    org = await service.create_organization(OrganizationCreate(name="Subscription Corp", code=org_code))
    org_id = str(org["id"])

    # 2. Get PPE Detection Analytic
    analytic_uc3 = await service.get_analytic("uc3")
    assert analytic_uc3 is not None
    analytic_id = str(analytic_uc3["id"])

    # 3. Create Subscription
    sub_create = OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(analytic_id),
        is_enabled=True,
        max_cameras_allowed=25
    )
    sub = await service.create_organization_subscription(org_id, sub_create)
    assert sub["organization_id"] == org_id
    assert sub["analytic_id"] == analytic_id
    assert sub["max_cameras_allowed"] == 25
    assert sub["status"] == "enabled"

    # 4. List Subscriptions
    subs = await service.list_organization_subscriptions(org_id)
    assert len(subs) == 1
    assert subs[0]["analytic_code"] == "ppe_detection"

    # 5. Duplicate Subscription Rejection
    with pytest.raises(KeyError):
        await service.create_organization_subscription(org_id, sub_create)

    # 6. Update Subscription (Disable & update camera limit)
    sub_update = OrganizationSubscriptionUpdate(is_enabled=False, max_cameras_allowed=50)
    updated_sub = await service.update_organization_subscription(org_id, analytic_id, sub_update)
    assert updated_sub["is_enabled"] is False
    assert updated_sub["max_cameras_allowed"] == 50
    assert updated_sub["status"] == "disabled"

    # 7. Expiry Handling
    past_time = datetime.now(timezone.utc) - timedelta(days=1)
    expiry_update = OrganizationSubscriptionUpdate(is_enabled=True, valid_until=past_time)
    expired_sub = await service.update_organization_subscription(org_id, analytic_id, expiry_update)
    assert expired_sub["is_enabled"] is True
    assert expired_sub["status"] == "expired"

    # 8. Delete Subscription
    await service.delete_organization_subscription(org_id, analytic_id)
    remaining = await service.list_organization_subscriptions(org_id)
    assert len(remaining) == 0

@pytest.mark.asyncio
async def test_subscription_validation_rejections(service):
    # Invalid Organization Rejection
    fake_org_id = str(uuid.uuid4())
    analytic_uc1 = await service.get_analytic("uc1")
    sub_data = OrganizationSubscriptionCreate(analytic_id=uuid.UUID(str(analytic_uc1["id"])))
    
    with pytest.raises(ValueError):
        await service.create_organization_subscription(fake_org_id, sub_data)

    # Invalid Analytic Rejection
    org = await service.create_organization(OrganizationCreate(name="Valid Org", code=f"org_{uuid.uuid4().hex[:8]}"))
    invalid_sub_data = OrganizationSubscriptionCreate(analytic_id=uuid.uuid4())
    with pytest.raises(ValueError):
        await service.create_organization_subscription(str(org["id"]), invalid_sub_data)

    # Negative Camera Limit Rejection (Pydantic ValidationError)
    with pytest.raises(ValidationError):
        OrganizationSubscriptionCreate(analytic_id=uuid.uuid4(), max_cameras_allowed=-5)
