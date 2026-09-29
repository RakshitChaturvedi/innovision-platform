from enum import Enum
from fastapi import Header, HTTPException, Depends
from .jwt import decode_access_token
from .config import settings

class Role(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN ="admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

ROLE_RANK = {Role.VIEWER: 0, Role.OPERATOR: 1, Role.ADMIN: 2, Role.SUPERADMIN: 3}

async def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.removeprefix("Bearer ")
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

async def get_current_user_optional(authorization: str | None = Header(default=None)) -> dict | None:
    """Same as get_current_user but returns None instead of raising — for
    endpoints that accept EITHER a user token OR an internal service token."""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        return decode_access_token(token)
    except Exception:
        return None

def require_role(minimum: Role):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = Role(user["role"])
        if ROLE_RANK[user_role] < ROLE_RANK[minimum]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker

def require_camera_access(camera_id: str):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if Role(user["role"]) in (Role.SUPERADMIN, Role.ADMIN):
            return user
        if camera_id not in user["camera_ids"]:
            raise HTTPException(status_code=403, detail="No access to this camera")
        return user 
    return checker

async def require_internal_service(x_service_token: str | None = Header(default=None)) -> bool:
    """For pure service-to-service calls (no human user at all)."""
    if not x_service_token or x_service_token != settings.internal_service_token:
        raise HTTPException(status_code=401, detail="Missing or invalid service token")
    return True


def require_role_or_internal_service(minimum: Role):
    """Accepts either a valid service token (ingestion, other backend
    services) OR a user JWT meeting the role minimum (dashboard/admin)."""
    async def checker(
        x_service_token: str | None = Header(default=None),
        user: dict | None = Depends(get_current_user_optional),
    ):
        if x_service_token and x_service_token == settings.internal_service_token:
            return True
        if user is not None:
            user_role = Role(user["role"])
            if ROLE_RANK[user_role] >= ROLE_RANK[minimum]:
                return user
        raise HTTPException(status_code=401, detail="Unauthorized")
    return checker