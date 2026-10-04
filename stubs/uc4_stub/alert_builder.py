"""
alert_builder.py — Maps CV detections to contract-compliant AlertEvent objects.

FIX #3: AlertEvent schema compliance.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, FrameProvider, SourceUC

logger = logging.getLogger("uc4.alert_builder")

# ── Severity mapping (internal uppercase → enum lowercase) ────────

_SEVERITY_MAP = {
    "CRITICAL": AlertSeverity.CRITICAL,
    "HIGH": AlertSeverity.HIGH,
    "MEDIUM": AlertSeverity.MEDIUM,
    "LOW": AlertSeverity.LOW,
    # Already-lowercase pass-through
    "critical": AlertSeverity.CRITICAL,
    "high": AlertSeverity.HIGH,
    "medium": AlertSeverity.MEDIUM,
    "low": AlertSeverity.LOW,
}


def _map_severity(raw: str) -> AlertSeverity:
    """Map internal uppercase/mixed severity strings to enum values."""
    mapped = _SEVERITY_MAP.get(raw)
    if mapped is None:
        logger.warning("unknown_severity raw=%s defaulting=medium", raw)
        return AlertSeverity.MEDIUM
    return mapped


def build_speed_violation_alert(
    *,
    camera_id: UUID,
    source_event_id: UUID,
    tracker_id: int,
    plate: str,
    speed_kmh: float,
    speed_limit_kmh: float,
    vehicle_type: str = "Car",
    frame_reference: Optional[str] = None,
    frame_provider: Optional[FrameProvider] = None,
) -> AlertEvent:
    """
    Build a 'speed_violation' AlertEvent.
    alert_type: EXACTLY "speed_violation".
    """
    s_kmh = float(speed_kmh)
    sl_kmh = float(speed_limit_kmh)
    severity = (
        AlertSeverity.CRITICAL if s_kmh > sl_kmh + 30
        else AlertSeverity.HIGH if s_kmh > sl_kmh + 15
        else AlertSeverity.MEDIUM
    )

    plate_display = str(plate) if plate and plate != "UNKNOWN" else "Unknown Plate"

    return AlertEvent(
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        alert_type="speed_violation",
        title=f"Speeding Violation: Plate {plate_display}",
        description=(
            f"Vehicle exceeded zone speed limit "
            f"({s_kmh:.1f} km/h in {sl_kmh:.0f} km/h zone)"
        ),
        source_event_id=source_event_id,
        source_uc=SourceUC.UC4,
        frame_reference=frame_reference,
        frame_provider=frame_provider,
        metadata={
            "tracker_id": int(tracker_id),
            "speed": float(round(s_kmh, 1)),
            "speed_limit_kmh": float(round(sl_kmh, 1)),
            "plate_number": str(plate),
            "vehicle_type": str(vehicle_type),
        },
    )


def build_unauthorized_vehicle_alert(
    *,
    camera_id: UUID,
    source_event_id: UUID,
    tracker_id: int,
    plate: str,
    vehicle_type: str = "Car",
    frame_reference: Optional[str] = None,
    frame_provider: Optional[FrameProvider] = None,
) -> AlertEvent:
    """
    Build an 'unauthorized_vehicle' AlertEvent for blacklisted plates.
    alert_type: EXACTLY "unauthorized_vehicle".
    """
    return AlertEvent(
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.CRITICAL,
        alert_type="unauthorized_vehicle",
        title=f"Unauthorized Vehicle: Plate {plate}",
        description=(
            f"Blacklisted vehicle with plate {plate} detected in monitored zone"
        ),
        source_event_id=source_event_id,
        source_uc=SourceUC.UC4,
        frame_reference=frame_reference,
        frame_provider=frame_provider,
        metadata={
            "tracker_id": int(tracker_id),
            "plate_number": str(plate),
            "vehicle_type": str(vehicle_type),
            "blacklisted": True,
        },
    )


def build_anpr_read_alert(
    *,
    camera_id: UUID,
    source_event_id: UUID,
    tracker_id: int,
    plate: str,
    confidence: float,
    vehicle_type: str = "Car",
    speed_kmh: float = 0.0,
    frame_reference: Optional[str] = None,
    frame_provider: Optional[FrameProvider] = None,
) -> AlertEvent:
    """
    Build an 'anpr_read' AlertEvent for plain plate reads.
    alert_type: EXACTLY "anpr_read".
    """
    conf = float(confidence)
    s_kmh = float(speed_kmh)
    return AlertEvent(
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=AlertSeverity.LOW,
        alert_type="anpr_read",
        title=f"ANPR Read: Plate {plate}",
        description=(
            f"License plate {plate} read with {conf:.0f}% confidence"
        ),
        source_event_id=source_event_id,
        source_uc=SourceUC.UC4,
        frame_reference=frame_reference,
        frame_provider=frame_provider,
        metadata={
            "tracker_id": int(tracker_id),
            "plate_number": str(plate),
            "plate_confidence": float(round(conf, 1)),
            "vehicle_type": str(vehicle_type),
            "speed": float(round(s_kmh, 1)),
        },
    )
