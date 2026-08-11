from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime

from shared.contracts.enums import CameraStatus

class CameraCreate(BaseModel):
    name: str
    location: Optional[str] = None
    rtsp_url: str
    use_cases: list[str] = Field(default_factory=list)
    fps: int = Field(default=15, ge=1, le=60)

class CameraConfigUpdate(BaseModel):
    use_cases: Optional[list[str]] = None
    fps: Optional[int] = None

class CameraResponse(BaseModel):
    id: UUID
    name: str
    location: Optional[str]
    status: CameraStatus
    use_cases: list[str]
    fps: int
    created_at: datetime
