from __future__ import annotations

from pydantic import BaseModel,Field
from uuid import UUID, uuid4
from datetime import datetime

from enums import FrameProvider

class FrameEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    camera_id: UUID
    frame_seq: int
    timestamp: datetime
    frame_provider: FrameProvider
    frame_reference: str
    frame_shape: tuple[int, int]

    class Config:
        frozen = True #contracts shouldnt 

class FrameEventSchema:
    # validation helpers, ucs call these to verify if the events are constructed correctly.
    REQUIRED_FIELDS = {
        "event_id", "camera_id", "frame_seq", "timestamp", "frame_provider",
        "frame_reference", "frame_shape"
    }

    @staticmethod
    def validated_reference_format(event: FrameEvent) -> list[str]:
        errors = []

        if not event.frame_reference:
            errors.append("frame_reference cant be empty")
        if event.frame_provider == FrameProvider.MINIO:
            if not event.frame_reference.startswith("frames/"):
                errors.append(
                    f"MinIO frame_reference must start with 'frames/',"
                    f"got: {event.frame_reference}"
                )
        if event.frame_shape[0] <= 0 or event.frame_shape[1] <= 0:
            errors.append(f"frame_shape must be positive, got: {event.frame_shape}")
        return errors
