import hmac
import logging
from fastapi import APIRouter, Depends, HTTPException, Header

from services.camera_registry.src.config import settings
from services.camera_registry.src.schemas import CameraCreate, CameraConfigUpdate, CameraResponse, CameraStatusUpdate
from services.camera_registry.src.service import CameraRegistryService
from services.auth.src.rbac import require_role, Role, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cameras", tags=["camera-registry"])

_warned_empty_key = False

if not settings.internal_service_key and not _warned_empty_key:
    logger.warning("INTERNAL_SERVICE_KEY is empty; internal service key authentication is disabled.")
    _warned_empty_key = True


def is_valid_internal_key(x_internal_key: str | None) -> bool:
    if not settings.internal_service_key or not x_internal_key:
        return False
    return hmac.compare_digest(x_internal_key, settings.internal_service_key)


def get_service() -> CameraRegistryService:
    raise RuntimeError("Camera Registry service dependency not configured")


async def get_optional_user(authorization: str | None = Header(None)) -> dict | None:
    if not authorization:
        return None
    try:
        return await get_current_user(authorization=authorization)
    except Exception:
        return None


def is_privileged_request(
    user: dict | None,
    x_internal_key: str | None,
) -> bool:
    if user is not None and user.get("role") in ("superadmin", "admin"):
        return True
    return is_valid_internal_key(x_internal_key)


async def require_admin_or_internal_key(
    authorization: str | None = Header(None),
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
):
    if is_valid_internal_key(x_internal_key):
        return True
    if authorization:
        user = await get_current_user(authorization=authorization)
        if user.get("role") in ("superadmin", "admin"):
            return True
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    raise HTTPException(status_code=401, detail="Authentication required")


@router.post("", status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_camera(
    body: CameraCreate,
    service: CameraRegistryService = Depends(get_service),
):
    return await service.create_camera(body)


@router.get("")
async def list_cameras(
    user: dict | None = Depends(get_optional_user),
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    service: CameraRegistryService = Depends(get_service),
):
    cameras = await service.get_active_cameras()
    if not is_privileged_request(user, x_internal_key):
        cameras = [{k: v for k, v in c.items() if k != "rtsp_url"} for c in cameras]
    return cameras


@router.get("/by-uc/{uc_id}")
async def cameras_for_uc(
    uc_id: str,
    service: CameraRegistryService = Depends(get_service),
):
    # Internal endpoint — UC analytics services call on startup
    camera_ids = await service.get_cameras_for_uc(uc_id)
    return {"uc_id": uc_id, "camera_ids": camera_ids}


@router.get("/{camera_id}")
async def get_camera(
    camera_id: str,
    user: dict | None = Depends(get_optional_user),
    x_internal_key: str | None = Header(None, alias="X-Internal-Key"),
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    if not is_privileged_request(user, x_internal_key):
        camera = {k: v for k, v in camera.items() if k != "rtsp_url"}
    return camera


@router.put("/{camera_id}/config", dependencies=[Depends(require_role(Role.ADMIN))])
async def update_config(
    camera_id: str,
    body: CameraConfigUpdate,
    service: CameraRegistryService = Depends(get_service),
):
    await service.update_config(camera_id, body)
    return {"status": "updated"}


@router.get("/{camera_id}/status")
async def get_status(
    camera_id: str,
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id)
    if not camera:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {
        "camera_id": camera_id,
        "status": camera["status"],
        "use_cases": camera["use_cases"],
    }


@router.patch("/{camera_id}/status", dependencies=[Depends(require_admin_or_internal_key)])
async def update_status(
    camera_id: str,
    body: CameraStatusUpdate,
    service: CameraRegistryService = Depends(get_service),
):
    await service.update_status(camera_id, body.status)
    return {"camera_id": camera_id, "status": body.status}


@router.delete("/{camera_id}", status_code=204, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def delete_camera(
    camera_id: str,
    service: CameraRegistryService = Depends(get_service),
):
    await service.delete_camera(camera_id)
