from fastapi import APIRouter, Depends, HTTPException

from services.camera_registry.src.schemas import CameraCreate, CameraConfigUpdate, CameraResponse, CameraStatusUpdate
from services.camera_registry.src.service import CameraRegistryService
from services.auth.src.rbac import require_role, Role

router = APIRouter(prefix="/cameras", tags=["camera-registry"])

def get_service() -> CameraRegistryService:
    raise RuntimeError("Camera Registry service dependency not configured")

@router.post("", status_code=201, dependencies=[Depends(require_role(Role.ADMIN))])
async def create_camera(body: CameraCreate, service: CameraRegistryService = Depends(get_service)):
    return await service.create_camera(body)

@router.get("")
async def list_cameras(service: CameraRegistryService = Depends(get_service)):
    return await service.get_active_cameras()

@router.put("/{camera_id}/config", dependencies=[Depends(require_role(Role.ADMIN))])
async def update_config(
    camera_id: str,
    body: CameraConfigUpdate,
    service: CameraRegistryService = Depends(get_service),
):
    await service.update_config(camera_id, body)
    return {"status": "updated"}

@router.delete("/{camera_id}", status_code=204, dependencies=[Depends(require_role(Role.SUPERADMIN))])
async def delete_camera(
    camera_id: str,
    service: CameraRegistryService = Depends(get_service),
): 
    await service.delete_camera(camera_id)

@router.get("/by-uc/{uc_id}")
async def cameras_for_uc(uc_id: str, service: CameraRegistryService = Depends(get_service)):
    # internal endpoint. uc analytics services call on startup
    camera_ids = await service.get_cameras_for_uc(uc_id)
    return {"uc_id": uc_id, "camera_ids": camera_ids}

@router.get("/{camera_id}/status")
async def get_status(
    camera_id: str,
    service: CameraRegistryService = Depends(get_service),
):
    camera = await service.get_camera(camera_id)

    if not camera:
        raise HTTPException(status_code=404)

    return {
        "camera_id": camera_id,
        "status": camera["status"],
        "use_cases": camera["use_cases"],
    }

@router.patch("/{camera_id}/status")
async def update_status(
    camera_id: str,
    body: CameraStatusUpdate,
    service: CameraRegistryService = Depends(get_service),
):
    await service.update_status(camera_id, body.status)

    return {
        "camera_id": camera_id,
        "status": body.status,
    }