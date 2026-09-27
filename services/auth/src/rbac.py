from enum import Enum
from fastapi import Header, HTTPException, Depends
from .jwt import decode_access_token

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