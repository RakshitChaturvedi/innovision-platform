from __future__ import annotations

from pydantic import BaseModel, Field, model_validator, ConfigDict
from uuid import UUID, uuid4
from datetime import datetime, timezone
from typing import Any, Optional

from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC


def _sanitize_for_json(val: Any) -> Any:
    """Recursively converts non-standard types (e.g. NumPy scalars/arrays, sets, UUIDs) to JSON-safe primitives."""
    if val is None or isinstance(val, (str, int, float, bool)):
        # Still check if it's a numpy scalar inheriting from int/float/bool
        if hasattr(val, "item") and callable(val.item):
            return val.item()
        return val
    if hasattr(val, "item") and callable(val.item):
        if hasattr(val, "ndim") and val.ndim > 0 and hasattr(val, "tolist") and callable(val.tolist):
            return [_sanitize_for_json(x) for x in val.tolist()]
        return val.item()
    if hasattr(val, "tolist") and callable(val.tolist):  # NumPy array
        return [_sanitize_for_json(x) for x in val.tolist()]
    if isinstance(val, UUID):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, dict):
        return {str(k): _sanitize_for_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple, set)):
        return [_sanitize_for_json(x) for x in val]
    return str(val)


class AlertEvent(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    alert_id: UUID = Field(default_factory=uuid4)
    camera_id: UUID
    timestamp: datetime
    severity: AlertSeverity
    alert_type: str

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    source_event_id: UUID
    source_uc: SourceUC
    frame_reference: Optional[str] = None
    frame_provider: Optional[FrameProvider] = None
    status: AlertStatus = AlertStatus.PENDING
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def sanitize_and_coerce_inputs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            # Coerce string UUIDs if passed as str
            for uuid_field in ("alert_id", "camera_id", "source_event_id"):
                if uuid_field in data and isinstance(data[uuid_field], str):
                    try:
                        data[uuid_field] = UUID(data[uuid_field])
                    except (ValueError, TypeError):
                        pass

            # Sanitize metadata to convert numpy scalars and arrays
            if "metadata" in data and isinstance(data["metadata"], dict):
                data["metadata"] = _sanitize_for_json(data["metadata"])

        return data

    @model_validator(mode="after")
    def validate_frame_reference_consistency(self) -> AlertEvent:
        # frame_reference and frame_provider must either both exist or both omitted.
        has_ref = self.frame_reference is not None
        has_provider = self.frame_provider is not None

        if has_ref != has_provider:
            raise ValueError(
                "frame_reference and frame_provider must both be set or both omitted: "
                f"Got frame_reference={self.frame_reference!r}, "
                f"frame_provider={self.frame_provider!r}"
            )
        return self


class AlertEventValidator:
    @staticmethod
    def validate(event: AlertEvent, known_cam_ids: set[Any]) -> list[str]:
        errors = []

        if known_cam_ids:
            # Match against set of UUIDs or set of strings
            cam_str_set = {str(c) for c in known_cam_ids}
            if str(event.camera_id) not in cam_str_set and event.camera_id not in known_cam_ids:
                errors.append(f"camera_id {event.camera_id} not registered in Camera Registry")

        if not event.title or not event.title.strip():
            errors.append("title cant be whitespace only")
        if not event.description or not event.description.strip():
            errors.append("description cant be whitespace only")

        return errors