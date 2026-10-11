import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException

from services.auth.src.rbac import (
    Role,
    ROLE_RANK,
    get_current_user,
    require_role,
    require_organization_access,
    verify_resource_org,
)
from services.auth.src.jwt import create_access_token, decode_access_token
from services.incident_management.src.service import IncidentService
from services.incident_management.src.workflow import VALID_TRANSITIONS


# ============================================================================
# 1. AUTHENTICATION & TOKEN VALIDATION TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_unauthenticated_request_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(authorization="Basic dXNlcjpwYXNz")
    assert exc_info.value.status_code == 401
    assert "Invalid authorization header" in exc_info.value.detail


@pytest.mark.asyncio
async def test_invalid_jwt_token_rejected():
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(authorization="Bearer invalid.token.payload")
    assert exc_info.value.status_code == 401
    assert "Invalid or expired token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_authenticated_token_payload_resolved():
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    token = create_access_token(user_id, Role.OPERATOR, ["cam-1", "cam-2"], org_id=org_id)
    
    payload = await get_current_user(authorization=f"Bearer {token}")
    assert payload["sub"] == user_id
    assert payload["role"] == Role.OPERATOR
    assert payload["org_id"] == org_id
    assert "cam-1" in payload["camera_ids"]


# ============================================================================
# 2. ROLE AUTHORIZATION & HIERARCHY TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_viewer_denied_operator_endpoints():
    viewer_user = {"sub": str(uuid.uuid4()), "role": "viewer", "org_id": str(uuid.uuid4())}
    checker = require_role(Role.OPERATOR)
    
    with pytest.raises(HTTPException) as exc_info:
        await checker(user=viewer_user)
    assert exc_info.value.status_code == 403
    assert "Insufficient permissions" in exc_info.value.detail


@pytest.mark.asyncio
async def test_operator_permitted_operator_endpoints():
    operator_user = {"sub": str(uuid.uuid4()), "role": "operator", "org_id": str(uuid.uuid4())}
    checker = require_role(Role.OPERATOR)
    
    res = await checker(user=operator_user)
    assert res == operator_user


@pytest.mark.asyncio
async def test_operator_denied_admin_endpoints():
    operator_user = {"sub": str(uuid.uuid4()), "role": "operator", "org_id": str(uuid.uuid4())}
    checker = require_role(Role.ADMIN)
    
    with pytest.raises(HTTPException) as exc_info:
        await checker(user=operator_user)
    assert exc_info.value.status_code == 403
    assert "Insufficient permissions" in exc_info.value.detail


@pytest.mark.asyncio
async def test_org_admin_and_admin_permitted_admin_endpoints():
    checker = require_role(Role.ADMIN)
    
    admin_user = {"sub": str(uuid.uuid4()), "role": "admin", "org_id": str(uuid.uuid4())}
    org_admin_user = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": str(uuid.uuid4())}
    
    assert await checker(user=admin_user) == admin_user
    assert await checker(user=org_admin_user) == org_admin_user


@pytest.mark.asyncio
async def test_admin_denied_superadmin_endpoints():
    admin_user = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": str(uuid.uuid4())}
    checker = require_role(Role.SUPERADMIN)
    
    with pytest.raises(HTTPException) as exc_info:
        await checker(user=admin_user)
    assert exc_info.value.status_code == 403
    assert "Insufficient permissions" in exc_info.value.detail


@pytest.mark.asyncio
async def test_superadmin_permitted_all_endpoints():
    superadmin_user = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}
    
    assert await require_role(Role.VIEWER)(user=superadmin_user) == superadmin_user
    assert await require_role(Role.OPERATOR)(user=superadmin_user) == superadmin_user
    assert await require_role(Role.ADMIN)(user=superadmin_user) == superadmin_user
    assert await require_role(Role.SUPERADMIN)(user=superadmin_user) == superadmin_user


# ============================================================================
# 3. TENANT ISOLATION TESTS
# ============================================================================

def test_cross_tenant_resource_access_rejected_by_verify_resource_org():
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    user_in_org_a = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_a}
    
    with pytest.raises(HTTPException) as exc_info:
        verify_resource_org(resource_org_id=org_b, user=user_in_org_a)
    assert exc_info.value.status_code == 403
    assert "Cross-organization access forbidden" in exc_info.value.detail


def test_same_tenant_resource_access_permitted_by_verify_resource_org():
    org_a = str(uuid.uuid4())
    user_in_org_a = {"sub": str(uuid.uuid4()), "role": "org_admin", "org_id": org_a}
    
    verify_resource_org(resource_org_id=org_a, user=user_in_org_a)


def test_superadmin_cross_tenant_access_permitted():
    org_b = str(uuid.uuid4())
    superadmin_user = {"sub": str(uuid.uuid4()), "role": "superadmin", "org_id": None}
    
    verify_resource_org(resource_org_id=org_b, user=superadmin_user)


# ============================================================================
# 4. INCIDENT LIFECYCLE & ROLE-BASED TRANSITION RESTRICTIONS
# ============================================================================

def test_incident_lifecycle_valid_transitions():
    assert "acknowledged" in VALID_TRANSITIONS["open"]
    assert "investigating" in VALID_TRANSITIONS["open"]
    assert "resolved" in VALID_TRANSITIONS["acknowledged"]
    assert "resolved" in VALID_TRANSITIONS["investigating"]
    assert "closed" in VALID_TRANSITIONS["resolved"]
    assert len(VALID_TRANSITIONS["closed"]) == 0


class MockAsyncContext:
    def __init__(self, value=None):
        self.value = value
    async def __aenter__(self):
        return self.value
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

def create_mock_session_factory(mock_session):
    mock_session.begin = MagicMock(return_value=MockAsyncContext())
    factory = MagicMock()
    factory.return_value = MockAsyncContext(mock_session)
    return factory


@pytest.mark.asyncio
async def test_operator_cannot_close_incident():
    org_id = str(uuid.uuid4())
    inc_id = str(uuid.uuid4())
    
    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.id = inc_id
    mock_row.status = "resolved"
    mock_row.organization_id = org_id
    
    execute_result = MagicMock()
    execute_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = execute_result
    
    session_factory = create_mock_session_factory(mock_session)
    service = IncidentService(session_factory)
    operator_user = {"sub": "op-1", "role": "operator", "org_id": org_id}
    
    with pytest.raises(HTTPException) as exc_info:
        await service.update_status(
            incident_id=inc_id,
            new_status="closed",
            user=operator_user,
        )
    assert exc_info.value.status_code == 403
    assert "Only organization administrators and superadmins can close incidents" in exc_info.value.detail


@pytest.mark.asyncio
async def test_invalid_status_transition_rejected():
    org_id = str(uuid.uuid4())
    inc_id = str(uuid.uuid4())
    
    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.id = inc_id
    mock_row.status = "open"
    mock_row.organization_id = org_id
    
    execute_result = MagicMock()
    execute_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = execute_result
    
    session_factory = create_mock_session_factory(mock_session)
    service = IncidentService(session_factory)
    admin_user = {"sub": "admin-1", "role": "admin", "org_id": org_id}
    
    with pytest.raises(HTTPException) as exc_info:
        await service.update_status(
            incident_id=inc_id,
            new_status="closed",
            user=admin_user,
        )
    assert exc_info.value.status_code == 400
    assert "Cannot transition from 'open' to 'closed'" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cross_tenant_incident_status_update_rejected():
    org_a = str(uuid.uuid4())
    org_b = str(uuid.uuid4())
    inc_id = str(uuid.uuid4())
    
    mock_session = AsyncMock()
    mock_row = MagicMock()
    mock_row.id = inc_id
    mock_row.status = "open"
    mock_row.organization_id = org_a
    
    execute_result = MagicMock()
    execute_result.fetchone.return_value = mock_row
    mock_session.execute.return_value = execute_result
    
    session_factory = create_mock_session_factory(mock_session)
    service = IncidentService(session_factory)
    user_b = {"sub": "op-b", "role": "operator", "org_id": org_b}
    
    with pytest.raises(HTTPException) as exc_info:
        await service.update_status(
            incident_id=inc_id,
            new_status="acknowledged",
            user=user_b,
        )
    assert exc_info.value.status_code == 403
    assert "Cross-organization access forbidden" in exc_info.value.detail
