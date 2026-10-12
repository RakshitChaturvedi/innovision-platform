from enum import Enum
from fastapi import Header, HTTPException, Depends
from .jwt import decode_access_token
from .config import settings

class Role(str, Enum):
    SUPERADMIN = "superadmin"
    ORG_ADMIN = "org_admin"
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"

ROLE_RANK = {
    Role.VIEWER: 0,
    Role.OPERATOR: 1,
    Role.ADMIN: 2,
    Role.ORG_ADMIN: 2,
    Role.SUPERADMIN: 3
}

async def get_current_user(authorization: str | None = Header(None)) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication credentials required")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header: expected 'Bearer <token>'")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Invalid authorization header: missing token")
    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload

def require_role(minimum: Role):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        raw_role = user.get("role", "viewer")
        user_role = Role(raw_role) if raw_role in Role._value2member_map_ else Role.VIEWER
        if ROLE_RANK[user_role] < ROLE_RANK[minimum]:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker

def require_organization_access(target_org_id: str | None = None):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role")
        if user_role == Role.SUPERADMIN:
            return user
        
        user_org = user.get("org_id") or user.get("organization_id")
        if not user_org or (target_org_id and str(user_org) != str(target_org_id)):
            raise HTTPException(status_code=403, detail="Cross-organization access forbidden")
        return user
    return checker

def require_camera_access(camera_id: str):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        user_role = user.get("role")
        if user_role in (Role.SUPERADMIN, Role.ADMIN, Role.ORG_ADMIN):
            return user
        camera_ids = user.get("camera_ids", [])
        if camera_id not in camera_ids:
            raise HTTPException(status_code=403, detail="No access to this camera")
        return user 
    return checker

def verify_resource_org(resource_org_id: str | None, user: dict) -> None:
    if user.get("role") == Role.SUPERADMIN:
        return
    user_org = user.get("org_id") or user.get("organization_id")
    if not user_org or not resource_org_id or str(resource_org_id) != str(user_org):
        raise HTTPException(status_code=403, detail="Cross-organization access forbidden")