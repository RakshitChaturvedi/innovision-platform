import pytest
import uuid
from datetime import datetime, timezone, timedelta
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from pydantic import ValidationError

from services.camera_registry.src.schemas import (
    OrganizationCreate, SiteCreate, ZoneCreate,
    OrganizationSubscriptionCreate, OrganizationSubscriptionUpdate,
    ZonePPERuleItem, ZonePPERulesConfig
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

@pytest_asyncio.fixture
async def sample_hierarchy(service):
    # Create Org, Site, Zone
    org_code = f"org_{uuid.uuid4().hex[:8]}"
    org = await service.create_organization(OrganizationCreate(name="Zone Test Corp", code=org_code))
    org_id = str(org["id"])

    site = await service.create_site(SiteCreate(name="Test Plant", code=f"plant_{uuid.uuid4().hex[:6]}", organization_id=uuid.UUID(org_id)))
    site_id = str(site["id"])

    zone = await service.create_zone(ZoneCreate(name="Kiln Zone", code=f"kiln_{uuid.uuid4().hex[:6]}", site_id=uuid.UUID(site_id)))
    zone_id = str(zone["id"])

    return {
        "org_id": org_id,
        "site_id": site_id,
        "zone_id": zone_id
    }

@pytest.mark.asyncio
async def test_list_zone_analytics_defaults(service, sample_hierarchy):
    zone_id = sample_hierarchy["zone_id"]
    
    # By default, all catalog analytics should be listed with is_enabled=False
    policies = await service.list_zone_analytics_policies(zone_id)
    assert len(policies) >= 4
    
    codes = {p["internal_code"]: p for p in policies}
    assert "uc1" in codes
    assert "uc2" in codes
    assert "uc3" in codes
    assert "uc4" in codes

    for p in policies:
        assert p["is_enabled"] is False

@pytest.mark.asyncio
async def test_zone_policy_enable_disable_all_four_analytics(service, sample_hierarchy):
    org_id = sample_hierarchy["org_id"]
    zone_id = sample_hierarchy["zone_id"]

    catalog = await service.list_analytics_catalog()
    analytic_map = {item["internal_code"]: str(item["id"]) for item in catalog}

    # Subscribe org to all 4 analytics
    for uc_code, analytic_id in analytic_map.items():
        sub_data = OrganizationSubscriptionCreate(
            analytic_id=uuid.UUID(analytic_id),
            is_enabled=True,
            max_cameras_allowed=10
        )
        await service.create_organization_subscription(org_id, sub_data)

    # 1. Enable UC1
    res_uc1 = await service.update_zone_analytics_policy(zone_id, analytic_map["uc1"], is_enabled=True)
    assert res_uc1["internal_code"] == "uc1"
    assert res_uc1["is_enabled"] is True

    # 2. Enable UC2, UC3, UC4
    await service.update_zone_analytics_policy(zone_id, analytic_map["uc2"], is_enabled=True)
    await service.update_zone_analytics_policy(zone_id, analytic_map["uc3"], is_enabled=True)
    await service.update_zone_analytics_policy(zone_id, analytic_map["uc4"], is_enabled=True)

    policies = await service.list_zone_analytics_policies(zone_id)
    enabled_codes = [p["internal_code"] for p in policies if p["is_enabled"]]
    assert set(enabled_codes) == {"uc1", "uc2", "uc3", "uc4"}

    # 3. Disable UC1 and UC4
    await service.update_zone_analytics_policy(zone_id, analytic_map["uc1"], is_enabled=False)
    await service.update_zone_analytics_policy(zone_id, analytic_map["uc4"], is_enabled=False)

    policies = await service.list_zone_analytics_policies(zone_id)
    enabled_codes = [p["internal_code"] for p in policies if p["is_enabled"]]
    assert set(enabled_codes) == {"uc2", "uc3"}

@pytest.mark.asyncio
async def test_subscription_enforcement_on_zone_analytics(service, sample_hierarchy):
    org_id = sample_hierarchy["org_id"]
    zone_id = sample_hierarchy["zone_id"]

    catalog = await service.list_analytics_catalog()
    analytic_uc1 = [a for a in catalog if a["internal_code"] == "uc1"][0]
    analytic_uc1_id = str(analytic_uc1["id"])

    # 1. Attempt enabling UC1 without subscription -> Expect KeyError (409 Conflict)
    with pytest.raises(KeyError) as exc_info:
        await service.update_zone_analytics_policy(zone_id, analytic_uc1_id, is_enabled=True)
    assert "subscription" in str(exc_info.value).lower()

    # 2. Create disabled subscription for UC1
    sub_data = OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(analytic_uc1_id),
        is_enabled=False
    )
    await service.create_organization_subscription(org_id, sub_data)

    # Attempt enabling UC1 with disabled subscription -> Expect KeyError
    with pytest.raises(KeyError):
        await service.update_zone_analytics_policy(zone_id, analytic_uc1_id, is_enabled=True)

    # 3. Update subscription with past expiration
    past_time = datetime.now(timezone.utc) - timedelta(days=1)
    await service.update_organization_subscription(
        org_id, analytic_uc1_id,
        OrganizationSubscriptionUpdate(is_enabled=True, valid_until=past_time)
    )

    # Attempt enabling UC1 with expired subscription -> Expect KeyError
    with pytest.raises(KeyError):
        await service.update_zone_analytics_policy(zone_id, analytic_uc1_id, is_enabled=True)

    # 4. Update subscription to active
    future_time = datetime.now(timezone.utc) + timedelta(days=30)
    await service.update_organization_subscription(
        org_id, analytic_uc1_id,
        OrganizationSubscriptionUpdate(is_enabled=True, valid_until=future_time)
    )

    # Now enabling should succeed!
    updated_policy = await service.update_zone_analytics_policy(zone_id, analytic_uc1_id, is_enabled=True)
    assert updated_policy["is_enabled"] is True

@pytest.mark.asyncio
async def test_bulk_update_zone_analytics_policies(service, sample_hierarchy):
    org_id = sample_hierarchy["org_id"]
    zone_id = sample_hierarchy["zone_id"]

    catalog = await service.list_analytics_catalog()
    uc1_id = [a["id"] for a in catalog if a["internal_code"] == "uc1"][0]
    uc3_id = [a["id"] for a in catalog if a["internal_code"] == "uc3"][0]

    # Create active subscriptions for UC1 and UC3
    for aid in [uc1_id, uc3_id]:
        await service.create_organization_subscription(org_id, OrganizationSubscriptionCreate(
            analytic_id=uuid.UUID(str(aid)), is_enabled=True
        ))

    bulk_items = [
        {"analytic_id": str(uc1_id), "is_enabled": True},
        {"analytic_id": str(uc3_id), "is_enabled": True}
    ]

    res = await service.bulk_update_zone_analytics_policies(zone_id, bulk_items)
    enabled = [item for item in res if item["is_enabled"]]
    assert len(enabled) == 2

@pytest.mark.asyncio
async def test_organization_isolation_enforcement(service, sample_hierarchy):
    zone_id = sample_hierarchy["zone_id"]

    catalog = await service.list_analytics_catalog()
    uc1_id = str(catalog[0]["id"])

    # User from another organization attempting to modify zone_id
    foreign_user = {
        "sub": "user_123",
        "role": "admin",
        "org_id": str(uuid.uuid4()) # Different org
    }

    with pytest.raises(PermissionError):
        await service.update_zone_analytics_policy(
            zone_id, uc1_id, is_enabled=True, current_user=foreign_user
        )

    # User from the same organization succeeds (if subscription exists)
    same_org_user = {
        "sub": "user_456",
        "role": "admin",
        "org_id": sample_hierarchy["org_id"]
    }
    # Subscribe first
    await service.create_organization_subscription(sample_hierarchy["org_id"], OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(uc1_id), is_enabled=True
    ))

    policy = await service.update_zone_analytics_policy(
        zone_id, uc1_id, is_enabled=True, current_user=same_org_user
    )
    assert policy["is_enabled"] is True

@pytest.mark.asyncio
async def test_uc3_ppe_configuration_flow(service, sample_hierarchy):
    zone_id = sample_hierarchy["zone_id"]

    # 1. Get default PPE rules
    ppe_config = await service.get_zone_ppe_rules(zone_id)
    assert ppe_config["zone_id"] == zone_id
    assert isinstance(ppe_config["ppe_rules"], list)
    assert len(ppe_config["ppe_rules"]) > 0

    # Verify standard PPE items present
    ppe_items = {r["ppe_type"] for r in ppe_config["ppe_rules"]}
    expected_items = {"helmet", "safety-vest", "gloves", "shoes", "glasses", "mask", "face-guard", "medical-suit"}
    assert expected_items.issubset(ppe_items)

    # 2. Update PPE rules: Require Helmet, Vest, Mask
    new_rules = [
        ZonePPERuleItem(ppe_type="helmet", required=True),
        ZonePPERuleItem(ppe_type="safety-vest", required=True),
        ZonePPERuleItem(ppe_type="mask", required=True),
        ZonePPERuleItem(ppe_type="shoes", required=False),
    ]

    updated_config = await service.update_zone_ppe_rules(zone_id, new_rules, min_confidence=0.70)
    assert updated_config["min_confidence"] == 0.70

    updated_rules = {r["ppe_type"]: r for r in updated_config["ppe_rules"]}
    assert updated_rules["helmet"]["required"] is True
    assert updated_rules["safety-vest"]["required"] is True
    assert updated_rules["mask"]["required"] is True
    assert updated_rules["shoes"]["required"] is False

    # 3. Verify persistence
    persisted = await service.get_zone_ppe_rules(zone_id)
    persisted_rules = {r["ppe_type"]: r for r in persisted["ppe_rules"]}
    assert persisted_rules["helmet"]["required"] is True
    assert persisted_rules["safety-vest"]["required"] is True

@pytest.mark.asyncio
async def test_invalid_zone_or_analytic_rejection(service, sample_hierarchy):
    fake_zone_id = str(uuid.uuid4())
    fake_analytic_id = str(uuid.uuid4())
    valid_zone_id = sample_hierarchy["zone_id"]

    # Invalid zone for policy lookup
    with pytest.raises(ValueError):
        await service.list_zone_analytics_policies(fake_zone_id)

    # Invalid analytic for policy update
    with pytest.raises(ValueError):
        await service.update_zone_analytics_policy(valid_zone_id, fake_analytic_id, is_enabled=True)

    # Invalid zone for PPE rules lookup
    with pytest.raises(ValueError):
        await service.get_zone_ppe_rules(fake_zone_id)
