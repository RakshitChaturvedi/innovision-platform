"""
AlertEvent Pydantic contract published by UCs to alerts:live and consumed by Alert Management.
Fully compatible with both Platform base and UC2 analytics services.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC


class AlertEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    alert_id: UUID = Field(default_factory=uuid4)
    camera_id: Union[UUID, str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: AlertSeverity
    alert_type: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    source_event_id: Optional[Union[UUID, str]] = None
    source_uc: SourceUC
    frame_reference: Optional[str] = None
    frame_provider: Optional[FrameProvider] = None
    status: AlertStatus = AlertStatus.PENDING
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_frame_reference_consistency(self) -> AlertEvent:
        has_ref = self.frame_reference is not None
        has_provider = self.frame_provider is not None
        if has_ref != has_provider:
            raise ValueError(
                "frame_reference and frame_provider must both be set or both omitted: "
                f"Got frame_reference={self.frame_reference!r}, frame_provider={self.frame_provider!r}"
            )
        return self


class AlertEventValidator:
    @staticmethod
    def validate(
        event: AlertEvent,
        known_cam_ids: Optional[Union[Set[Any], List[Any]]] = None,
    ) -> List[str]:
        errors: List[str] = []
        if not event.title or not event.title.strip():
            errors.append("Title cannot be empty: title cant be whitespace only")
        if not event.description or not event.description.strip():
            errors.append("Description cannot be empty: description cant be whitespace only")

        if known_cam_ids is not None:
            cam_set = {str(k) for k in known_cam_ids}
            if str(event.camera_id) not in cam_set:
                errors.append(f"Camera ID / camera_id {event.camera_id} is not registered in Camera Registry")

        return errors

