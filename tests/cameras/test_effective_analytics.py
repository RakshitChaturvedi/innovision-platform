import pytest
import uuid
from datetime import datetime, timezone, timedelta
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from services.camera_registry.src.schemas import (
    OrganizationCreate, SiteCreate, ZoneCreate, CameraCreate,
    OrganizationSubscriptionCreate, OrganizationSubscriptionUpdate,
    CameraAssignZone
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
async def setup_env(service):
    org = await service.create_organization(OrganizationCreate(name="Effective Corp", code=f"eff_{uuid.uuid4().hex[:8]}"))
    org_id = str(org["id"])

    site = await service.create_site(SiteCreate(name="Effective Plant", code=f"plant_{uuid.uuid4().hex[:6]}", organization_id=uuid.UUID(org_id)))
    site_id = str(site["id"])

    zone_a = await service.create_zone(ZoneCreate(name="Zone Alpha", code=f"za_{uuid.uuid4().hex[:6]}", site_id=uuid.UUID(site_id)))
    zone_a_id = str(zone_a["id"])

    zone_b = await service.create_zone(ZoneCreate(name="Zone Beta", code=f"zb_{uuid.uuid4().hex[:6]}", site_id=uuid.UUID(site_id)))
    zone_b_id = str(zone_b["id"])

    cam1 = await service.create_camera(CameraCreate(
        name="Cam 1", rtsp_url="rtsp://cam1", organization_id=uuid.UUID(org_id), site_id=uuid.UUID(site_id), zone_id=uuid.UUID(zone_a_id)
    ))
    cam1_id = str(cam1["id"])

    cam2 = await service.create_camera(CameraCreate(
        name="Cam 2", rtsp_url="rtsp://cam2", organization_id=uuid.UUID(org_id), site_id=uuid.UUID(site_id), zone_id=uuid.UUID(zone_a_id)
    ))
    cam2_id = str(cam2["id"])

    catalog = await service.list_analytics_catalog()
    analytic_map = {item["internal_code"]: str(item["id"]) for item in catalog}

    return {
        "org_id": org_id,
        "site_id": site_id,
        "zone_a_id": zone_a_id,
        "zone_b_id": zone_b_id,
        "cam1_id": cam1_id,
        "cam2_id": cam2_id,
        "analytic_map": analytic_map
    }

@pytest.mark.asyncio
async def test_effective_analytics_precedence_rules(service, setup_env):
    org_id = setup_env["org_id"]
    zone_id = setup_env["zone_a_id"]
    cam_id = setup_env["cam1_id"]
    amap = setup_env["analytic_map"]
    uc1_id = amap["uc1"]

    # 1. No subscription -> INACTIVE
    eff = await service.get_camera_effective_analytics(cam_id)
    uc1_eff = next(item for item in eff if item["analytic_id"] == uc1_id)
    assert uc1_eff["is_active"] is False

    # 2. Add active subscription, Zone Policy still disabled -> INACTIVE
    await service.create_organization_subscription(org_id, OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(uc1_id), is_enabled=True, max_cameras_allowed=10
    ))
    eff = await service.get_camera_effective_analytics(cam_id)
    uc1_eff = next(item for item in eff if item["analytic_id"] == uc1_id)
    assert uc1_eff["is_active"] is False

    # 3. Enable Zone Policy -> ACTIVE (source="zone")
    await service.update_zone_analytics_policy(zone_id, uc1_id, is_enabled=True)
    eff = await service.get_camera_effective_analytics(cam_id)
    uc1_eff = next(item for item in eff if item["analytic_id"] == uc1_id)
    assert uc1_eff["is_active"] is True
    assert uc1_eff["source"] == "zone"

    # 4. Add Camera Override = False -> INACTIVE (source="camera_override")
    await service.set_camera_analytics_override(cam_id, uc1_id, is_enabled=False)
    eff = await service.get_camera_effective_analytics(cam_id)
    uc1_eff = next(item for item in eff if item["analytic_id"] == uc1_id)
    assert uc1_eff["is_active"] is False
    assert uc1_eff["source"] == "camera_override"

    # 5. Remove Camera Override -> Reverts to Zone Policy (ACTIVE)
    await service.delete_camera_analytics_override(cam_id, uc1_id)
    eff = await service.get_camera_effective_analytics(cam_id)
    uc1_eff = next(item for item in eff if item["analytic_id"] == uc1_id)
    assert uc1_eff["is_active"] is True
    assert uc1_eff["source"] == "zone"

@pytest.mark.asyncio
async def test_override_cannot_bypass_subscription(service, setup_env):
    org_id = setup_env["org_id"]
    cam_id = setup_env["cam1_id"]
    uc2_id = setup_env["analytic_map"]["uc2"]

    # 1. Create disabled subscription for UC2
    await service.create_organization_subscription(org_id, OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(uc2_id), is_enabled=False
    ))

    # 2. Attempt camera override enabled = True
    await service.set_camera_analytics_override(cam_id, uc2_id, is_enabled=True)

    # Effective state MUST remain INACTIVE because subscription is disabled (Rule 1)
    eff = await service.get_camera_effective_analytics(cam_id)
    uc2_eff = next(item for item in eff if item["analytic_id"] == uc2_id)
    assert uc2_eff["is_active"] is False
    assert uc2_eff["override_enabled"] is True
    assert uc2_eff["subscription_active"] is False

@pytest.mark.asyncio
async def test_all_four_analytics_generic_resolution(service, setup_env):
    org_id = setup_env["org_id"]
    zone_id = setup_env["zone_a_id"]
    cam_id = setup_env["cam1_id"]
    amap = setup_env["analytic_map"]

    # Subscribe org to all 4 analytics
    for code, aid in amap.items():
        await service.create_organization_subscription(org_id, OrganizationSubscriptionCreate(
            analytic_id=uuid.UUID(aid), is_enabled=True
        ))

    # Enable all 4 analytics on zone_a
    for code, aid in amap.items():
        await service.update_zone_analytics_policy(zone_id, aid, is_enabled=True)

    eff = await service.get_camera_effective_analytics(cam_id)
    active_codes = {item["internal_code"] for item in eff if item["is_active"]}
    assert active_codes == {"uc1", "uc2", "uc3", "uc4"}

@pytest.mark.asyncio
async def test_zone_reassignment_recalculates_effective_analytics(service, setup_env):
    org_id = setup_env["org_id"]
    zone_a_id = setup_env["zone_a_id"]
    zone_b_id = setup_env["zone_b_id"]
    cam_id = setup_env["cam1_id"]
    uc1_id = setup_env["analytic_map"]["uc1"]

    await service.create_organization_subscription(org_id, OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(uc1_id), is_enabled=True
    ))

    # Zone A has UC1 enabled; Zone B has UC1 disabled
    await service.update_zone_analytics_policy(zone_a_id, uc1_id, is_enabled=True)
    await service.update_zone_analytics_policy(zone_b_id, uc1_id, is_enabled=False)

    # In Zone A -> ACTIVE
    eff = await service.get_camera_effective_analytics(cam_id)
    assert next(item for item in eff if item["analytic_id"] == uc1_id)["is_active"] is True

    # Reassign to Zone B -> INACTIVE
    await service.assign_camera_zone(cam_id, zone_id=zone_b_id)
    eff = await service.get_camera_effective_analytics(cam_id)
    assert next(item for item in eff if item["analytic_id"] == uc1_id)["is_active"] is False

@pytest.mark.asyncio
async def test_subscription_camera_limit_enforcement(service, setup_env):
    org_id = setup_env["org_id"]
    zone_id = setup_env["zone_a_id"]
    cam1_id = setup_env["cam1_id"]
    cam2_id = setup_env["cam2_id"]
    uc1_id = setup_env["analytic_map"]["uc1"]

    # 1. Create subscription with max_cameras_allowed = 1
    await service.create_organization_subscription(org_id, OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(uc1_id), is_enabled=True, max_cameras_allowed=1
    ))

    # 2. Override cam1 enabled -> succeeds (usage = 1 / limit = 1)
    await service.set_camera_analytics_override(cam1_id, uc1_id, is_enabled=True)
    eff1 = await service.get_camera_effective_analytics(cam1_id)
    assert next(item for item in eff1 if item["analytic_id"] == uc1_id)["is_active"] is True

    # 3. Attempting override cam2 enabled -> rejected with KeyError (ANALYTIC_CAMERA_LIMIT_EXCEEDED)
    with pytest.raises(KeyError) as exc_info:
        await service.set_camera_analytics_override(cam2_id, uc1_id, is_enabled=True)
    assert "LIMIT_EXCEEDED" in str(exc_info.value)

    # 4. Cam1 remains active
    eff1 = await service.get_camera_effective_analytics(cam1_id)
    assert next(item for item in eff1 if item["analytic_id"] == uc1_id)["is_active"] is True

@pytest.mark.asyncio
async def test_organization_isolation_overrides(service, setup_env):
    cam_id = setup_env["cam1_id"]
    uc1_id = setup_env["analytic_map"]["uc1"]

    foreign_user = {
        "sub": "user_other",
        "role": "admin",
        "org_id": str(uuid.uuid4())
    }

    with pytest.raises(PermissionError):
        await service.set_camera_analytics_override(cam_id, uc1_id, is_enabled=True, current_user=foreign_user)

    with pytest.raises(PermissionError):
        await service.delete_camera_analytics_override(cam_id, uc1_id, current_user=foreign_user)

@pytest.mark.asyncio
async def test_uc_discovery_endpoint_uses_effective_analytics(service, setup_env):
    org_id = setup_env["org_id"]
    zone_id = setup_env["zone_a_id"]
    cam_id = setup_env["cam1_id"]
    uc3_id = setup_env["analytic_map"]["uc3"]

    # Subscribe & enable UC3
    await service.create_organization_subscription(org_id, OrganizationSubscriptionCreate(
        analytic_id=uuid.UUID(uc3_id), is_enabled=True
    ))
    await service.update_zone_analytics_policy(zone_id, uc3_id, is_enabled=True)

    # Query discovery endpoint
    cams = await service.get_cameras_for_uc("uc3")
    assert cam_id in cams
