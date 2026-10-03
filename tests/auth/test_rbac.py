import pytest
from fastapi import HTTPException

from services.auth.src.rbac import get_current_user
from services.auth.src.jwt import create_access_token


@pytest.mark.asyncio
async def test_get_current_user_missing_header():
    """Missing authorization header raises 401."""
    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization=None)
    assert exc.value.status_code == 401
    assert "Missing authorization header" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_malformed_header():
    """Malformed authorization header raises 401."""
    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization="Basic dXNlcjpwYXNz")
    assert exc.value.status_code == 401
    assert "Invalid authorization header" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_invalid_token():
    """Invalid token raises 401."""
    with pytest.raises(HTTPException) as exc:
        await get_current_user(authorization="Bearer invalid.jwt.token")
    assert exc.value.status_code == 401
    assert "Invalid or expired token" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_valid_token():
    """Valid token returns payload."""
    token = create_access_token("user-1", "operator", ["cam-1"])
    payload = await get_current_user(authorization=f"Bearer {token}")
    assert payload["sub"] == "user-1"
    assert payload["role"] == "operator"
    assert payload["camera_ids"] == ["cam-1"]
