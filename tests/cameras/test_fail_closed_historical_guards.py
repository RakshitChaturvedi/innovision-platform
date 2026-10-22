"""
Unit tests for Stage 2: Fail-Closed Historical Reference Checks.
Verifies that:
1. delete_zone blocks when compliance_events, person_daily_compliance, incidents, or uc3_events reference the zone.
2. delete_site blocks when incidents reference the site.
3. Unexpected database errors during dependency checks FAIL CLOSED (re-raising RuntimeError, never silently proceeding).
4. Missing uc3_events table fails closed unless explicitly permitted by INNOVISION_ALLOW_OPTIONAL_UC3_TABLES=1 policy.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from services.camera_registry.src.service import CameraRegistryService


class MockAsyncContextManager:
    def __init__(self, obj):
        self.obj = obj

    async def __aenter__(self):
        return self.obj

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


def create_mock_service(mock_execute_fn):
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=mock_execute_fn)
    mock_session.begin = MagicMock(return_value=MockAsyncContextManager(mock_session))

    session_factory = MagicMock(return_value=MockAsyncContextManager(mock_session))
    dummy_redis = MagicMock()
    service = CameraRegistryService(session_factory=session_factory, redis_client=dummy_redis)
    return service, mock_session


@pytest.mark.asyncio
async def test_delete_zone_blocks_when_compliance_events_exist():
    """Zone with compliance_events records must be rejected with ValueError."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM cameras WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM compliance_events WHERE zone_id" in q_str:
            res.scalar.return_value = 5  # 5 compliance events exist
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(ValueError, match="Cannot delete zone: historical compliance event records reference this zone"):
        await service.delete_zone("zone-123")


@pytest.mark.asyncio
async def test_delete_zone_blocks_when_person_daily_compliance_exist():
    """Zone with person_daily_compliance records must be rejected with ValueError."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM cameras WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM compliance_events WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM person_daily_compliance WHERE zone_id" in q_str:
            res.scalar.return_value = 2  # Daily compliance records exist
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(ValueError, match="Cannot delete zone: daily person compliance records reference this zone"):
        await service.delete_zone("zone-123")


@pytest.mark.asyncio
async def test_delete_zone_blocks_when_incidents_exist():
    """Zone with incidents records must be rejected with ValueError."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM cameras WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM compliance_events WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM person_daily_compliance WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM incidents WHERE zone_id" in q_str:
            res.scalar.return_value = 1  # 1 incident exists
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(ValueError, match="Cannot delete zone: historical incident records reference this zone"):
        await service.delete_zone("zone-123")


@pytest.mark.asyncio
async def test_delete_zone_blocks_when_uc3_events_exist():
    """Zone with uc3_events records must be rejected with ValueError."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM cameras WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM compliance_events WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM person_daily_compliance WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM incidents WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "to_regclass" in q_str:
            res.scalar.return_value = "public.uc3_events"
            return res
        if "FROM uc3_events WHERE zone_id" in q_str:
            res.scalar.return_value = 10  # 10 safety events exist
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(ValueError, match="Cannot delete zone: historical safety event records \\(uc3_events\\) reference this zone"):
        await service.delete_zone("zone-123")


@pytest.mark.asyncio
async def test_delete_zone_fails_closed_on_unexpected_database_error():
    """Unexpected DB error during dependency check MUST fail closed and raise RuntimeError."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM cameras WHERE zone_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM compliance_events" in q_str:
            # Simulate unexpected database operational failure / lock timeout
            raise RuntimeError("Database connection reset by peer during safety check")
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(RuntimeError, match="Database error during safety dependency check.*Zone deletion aborted"):
        await service.delete_zone("zone-123")


@pytest.mark.asyncio
async def test_delete_zone_missing_uc3_table_default_fails_closed(monkeypatch):
    """Missing uc3_events table by default is treated as missing required schema and aborts deletion."""
    monkeypatch.delenv("INNOVISION_ALLOW_OPTIONAL_UC3_TABLES", raising=False)

    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "to_regclass" in q_str:
            res.scalar.return_value = None  # Table does not exist
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(RuntimeError, match="Required safety table 'uc3_events' is missing from the database.*Zone deletion aborted"):
        await service.delete_zone("zone-123")


@pytest.mark.asyncio
async def test_delete_zone_missing_uc3_table_with_explicit_policy_allowed(monkeypatch):
    """Missing uc3_events table is allowed ONLY when INNOVISION_ALLOW_OPTIONAL_UC3_TABLES=1 is set."""
    monkeypatch.setenv("INNOVISION_ALLOW_OPTIONAL_UC3_TABLES", "1")

    deleted_tables = []
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "to_regclass" in q_str:
            res.scalar.return_value = None  # Table does not exist
            return res
        if "DELETE FROM" in q_str:
            deleted_tables.append(q_str)
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    await service.delete_zone("zone-123")
    # Confirms zone was deleted after documented policy bypass
    assert any("DELETE FROM zones" in q for q in deleted_tables)


@pytest.mark.asyncio
async def test_delete_site_blocks_when_incidents_exist():
    """Site with historical incidents must be rejected with ValueError."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM zones WHERE site_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM cameras WHERE site_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM incidents WHERE site_id" in q_str:
            res.scalar.return_value = 3  # 3 historical incidents exist
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(ValueError, match="Cannot delete site: historical incidents reference this site"):
        await service.delete_site("site-123")


@pytest.mark.asyncio
async def test_delete_site_fails_closed_on_unexpected_database_error():
    """Unexpected DB error in delete_site MUST fail closed and raise RuntimeError."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM zones WHERE site_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM cameras WHERE site_id" in q_str:
            res.scalar.return_value = 0
            return res
        if "FROM incidents WHERE site_id" in q_str:
            raise RuntimeError("Database connection dropped during incident check")
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(RuntimeError, match="Database error during site historical dependency check.*Site deletion aborted"):
        await service.delete_site("site-123")


@pytest.mark.asyncio
async def test_delete_site_blocks_when_child_zones_exist_accurate_message():
    """Confirms DEF-05: Site with child zones gives accurate child zones error message."""
    async def mock_exec(query, params=None):
        q_str = str(query)
        res = MagicMock()
        if "FROM zones WHERE site_id" in q_str:
            res.scalar.return_value = 1  # 1 child zone exists
            return res
        res.scalar.return_value = 0
        return res

    service, session = create_mock_service(mock_exec)
    with pytest.raises(ValueError, match="Cannot delete site: child zones are associated with this site. Remove or reassign zones first."):
        await service.delete_site("site-123")


@pytest.mark.asyncio
async def test_api_sanitizes_zone_deletion_error():
    """Confirms DEF-04: API endpoint returns generic sanitized error, hiding raw DB internals."""
    import httpx
    import uuid
    from fastapi import FastAPI
    from services.camera_registry.src import router as router_module
    from services.auth.src.jwt import create_access_token

    mock_service = MagicMock()
    mock_service.get_zone = AsyncMock(return_value={"id": "zone-1", "organization_id": None, "name": "Zone A"})
    mock_service.delete_zone = AsyncMock(side_effect=RuntimeError("INTERNAL_POSTGRES_SYNTAX_ERROR on column confidential_schema"))

    app = FastAPI()
    app.include_router(router_module.router)
    app.include_router(router_module.zones_router)
    app.dependency_overrides[router_module.get_service] = lambda: mock_service

    token = create_access_token(user_id=str(uuid.uuid4()), role="superadmin", camera_ids=[])
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/cameras/zones/zone-1", headers=headers)
        assert resp.status_code == 500
        # Generic message returned
        assert resp.json()["detail"] == "Administrative deletion aborted: database safety dependency check failed. Consult server logs."
        # Raw internal database exception is NOT exposed to client
        assert "INTERNAL_POSTGRES_SYNTAX_ERROR" not in resp.text
        assert "confidential_schema" not in resp.text


@pytest.mark.asyncio
async def test_api_sanitizes_site_deletion_error():
    """Confirms DEF-04: Site deletion API returns generic sanitized error, hiding raw DB internals."""
    import httpx
    import uuid
    from fastapi import FastAPI
    from services.camera_registry.src import router as router_module
    from services.auth.src.jwt import create_access_token

    mock_service = MagicMock()
    mock_service.get_site = AsyncMock(return_value={"id": "site-1", "organization_id": None, "name": "Site A"})
    mock_service.delete_site = AsyncMock(side_effect=RuntimeError("INTERNAL_POSTGRES_CONNECTION_DROP credentials leak"))

    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[router_module.get_service] = lambda: mock_service

    token = create_access_token(user_id=str(uuid.uuid4()), role="superadmin", camera_ids=[])
    headers = {"Authorization": f"Bearer {token}"}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.delete("/cameras/sites/site-1", headers=headers)
        assert resp.status_code == 500
        assert resp.json()["detail"] == "Administrative deletion aborted: database safety dependency check failed. Consult server logs."
        assert "INTERNAL_POSTGRES_CONNECTION_DROP" not in resp.text
        assert "credentials leak" not in resp.text
