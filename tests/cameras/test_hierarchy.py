import pytest
import uuid
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from services.camera_registry.src.schemas import (
    OrganizationCreate, SiteCreate, ZoneCreate, CameraCreate, CameraAssignZone
)
from services.camera_registry.src.service import CameraRegistryService

class DummyRedis:
    async def publish(self, channel, message):
        pass

@pytest_asyncio.fixture
async def service():
    from conftest import get_safe_test_db_url
    db_url = get_safe_test_db_url()
    if "@postgres:5432" in db_url:
        db_url = db_url.replace("@postgres:5432", "@localhost:5433")
    
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis_client = DummyRedis()
    registry_service = CameraRegistryService(session_factory, redis_client)
    yield registry_service
    await engine.dispose()

@pytest.mark.asyncio
async def test_organization_site_zone_camera_hierarchy(service):
    # 1. Create Organization
    org_code = f"org_{uuid.uuid4().hex[:8]}"
    org_data = OrganizationCreate(name="Test Enterprise Corp", code=org_code, tier="enterprise")
    org = await service.create_organization(org_data)
    assert org["id"] is not None
    assert org["name"] == "Test Enterprise Corp"
    assert org["code"] == org_code

    # 2. Create Site under Organization
    site_code = f"site_{uuid.uuid4().hex[:8]}"
    site_data = SiteCreate(organization_id=uuid.UUID(str(org["id"])), name="Plant 01", code=site_code, timezone="UTC")
    site = await service.create_site(site_data)
    assert site["id"] is not None
    assert str(site["organization_id"]) == str(org["id"])

    # 3. Create Zone under Site
    zone_data = ZoneCreate(site_id=uuid.UUID(str(site["id"])), name="Loading Dock A", zone_type="industrial", risk_level="high")
    zone = await service.create_zone(zone_data)
    assert zone["id"] is not None
    assert str(zone["site_id"]) == str(site["id"])
    assert str(zone["organization_id"]) == str(org["id"])

    # 4. Create Unassigned Camera
    cam_data = CameraCreate(
        name="Cam Dock 01",
        rtsp_url="rtsp://localhost:8554/live/dock1",
        use_cases=["uc3"],
        lifecycle_state="unassigned"
    )
    cam = await service.create_camera(cam_data)
    assert cam["id"] is not None
    assert cam["lifecycle_state"] == "unassigned"
    assert cam.get("zone_id") is None

    # 5. Assign Camera to Zone
    updated_cam = await service.assign_camera_zone(
        camera_id=cam["id"],
        zone_id=str(zone["id"]),
        lifecycle_state="active"
    )
    assert updated_cam is not None
    assert updated_cam["zone_id"] == str(zone["id"])
    assert updated_cam["site_id"] == str(site["id"])
    assert updated_cam["organization_id"] == str(org["id"])
    assert updated_cam["lifecycle_state"] == "active"
    assert updated_cam["organization"]["code"] == org_code
    assert updated_cam["site"]["code"] == site_code
    assert updated_cam["zone"]["name"] == "Loading Dock A"
