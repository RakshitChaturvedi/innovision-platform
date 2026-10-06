"""
alert_builder.py — Maps UC2 fire/smoke detections to contract-compliant AlertEvent objects.

FIX #3: AlertEvent schema compliance for UC2.

alert_type values:
  - "fire_detected"   (fires including sparks)
  - "smoke_detected"  (smoke-only detections)

severity mapping:
  - fire_detected:  CRITICAL (conf ≥ 0.80), HIGH (≥ 0.60), MEDIUM (≥ 0.40), LOW
  - smoke_detected: HIGH (conf ≥ 0.85), MEDIUM (≥ 0.50), LOW
  These come from the CV engine's ConfidenceFusion.determine_severity(), not hardcoded.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, FrameProvider, SourceUC

logger = logging.getLogger("uc2.alert_builder")


def build_fire_detected_alert(
    *,
    camera_id: UUID,
    source_event_id: UUID,
    detection_type: str,
    severity: AlertSeverity,
    final_confidence: float,
    bbox: Dict[str, int],
    zone_name: str,
    zone_id: str,
    verification_score: float,
    persistence_count: int,
    verification_details: Dict[str, Any],
    detection_metadata: Dict[str, Any],
    frame_reference: Optional[str] = None,
    frame_provider: Optional[FrameProvider] = None,
    evidence_key: Optional[str] = None,
    evidence_bucket: Optional[str] = None,
) -> AlertEvent:
    """
    Build a 'fire_detected' AlertEvent.
    alert_type: EXACTLY "fire_detected".
    """
    bbox_area = max(1, (bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"]))

    resolved_evidence_key = (
        evidence_key
        or detection_metadata.get("evidence_key")
        or frame_reference
    )
    resolved_evidence_bucket = (
        evidence_bucket
        or detection_metadata.get("evidence_bucket")
        or ("innovision-frames" if resolved_evidence_key else None)
    )

    return AlertEvent(
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        alert_type="fire_detected",
        title=f"Fire Detected: {zone_name}",
        description=(
            f"Flame detected in zone with {final_confidence * 100:.0f}% confidence"
        ),
        source_event_id=source_event_id,
        source_uc=SourceUC.UC2,
        frame_reference=frame_reference,
        frame_provider=frame_provider,
        metadata={
            "detection_type": detection_type,
            "confidence": round(float(final_confidence), 4),
            "verification_score": round(float(verification_score), 4),
            "flame_area_px": bbox_area,
            "bbox": bbox,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "persistence_count": persistence_count,
            "evidence_key": resolved_evidence_key,
            "evidence_bucket": resolved_evidence_bucket,
            "hsv_score": verification_details.get("hsv_score", 0.0),
            "texture_score": verification_details.get("texture_score", 0.0),
            "temporal_score": verification_details.get("temporal_score", 0.0),
            **{
                k: v
                for k, v in detection_metadata.items()
                if k not in ("frame_seq", "evidence_key", "evidence_bucket")
            },
        },
    )


def build_smoke_detected_alert(
    *,
    camera_id: UUID,
    source_event_id: UUID,
    severity: AlertSeverity,
    final_confidence: float,
    bbox: Dict[str, int],
    zone_name: str,
    zone_id: str,
    verification_score: float,
    persistence_count: int,
    verification_details: Dict[str, Any],
    detection_metadata: Dict[str, Any],
    frame_reference: Optional[str] = None,
    frame_provider: Optional[FrameProvider] = None,
    evidence_key: Optional[str] = None,
    evidence_bucket: Optional[str] = None,
) -> AlertEvent:
    """
    Build a 'smoke_detected' AlertEvent.
    alert_type: EXACTLY "smoke_detected".
    """
    bbox_area = max(1, (bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"]))

    # Estimate smoke density from texture/verification details
    texture_score = verification_details.get("texture_score", 0.0)
    smoke_density = round(texture_score, 4)

    resolved_evidence_key = (
        evidence_key
        or detection_metadata.get("evidence_key")
        or frame_reference
    )
    resolved_evidence_bucket = (
        evidence_bucket
        or detection_metadata.get("evidence_bucket")
        or ("innovision-frames" if resolved_evidence_key else None)
    )

    return AlertEvent(
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        alert_type="smoke_detected",
        title=f"Smoke Detected: {zone_name}",
        description=(
            f"Smoke detected in zone with {final_confidence * 100:.0f}% confidence"
        ),
        source_event_id=source_event_id,
        source_uc=SourceUC.UC2,
        frame_reference=frame_reference,
        frame_provider=frame_provider,
        metadata={
            "detection_type": "smoke",
            "confidence": round(float(final_confidence), 4),
            "verification_score": round(float(verification_score), 4),
            "smoke_density": smoke_density,
            "smoke_area_px": bbox_area,
            "bbox": bbox,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "persistence_count": persistence_count,
            "evidence_key": resolved_evidence_key,
            "evidence_bucket": resolved_evidence_bucket,
            "hsv_score": verification_details.get("hsv_score", 0.0),
            "texture_score": verification_details.get("texture_score", 0.0),
            "temporal_score": verification_details.get("temporal_score", 0.0),
            **{
                k: v
                for k, v in detection_metadata.items()
                if k not in ("frame_seq", "evidence_key", "evidence_bucket")
            },
        },
    )


def build_sparks_detected_alert(
    *,
    camera_id: UUID,
    source_event_id: UUID,
    severity: AlertSeverity,
    final_confidence: float,
    bbox: Dict[str, int],
    zone_name: str,
    zone_id: str,
    verification_score: float,
    persistence_count: int,
    verification_details: Dict[str, Any],
    detection_metadata: Dict[str, Any],
    frame_reference: Optional[str] = None,
    frame_provider: Optional[FrameProvider] = None,
    evidence_key: Optional[str] = None,
    evidence_bucket: Optional[str] = None,
) -> AlertEvent:
    """
    Build a 'sparks_detected' AlertEvent.
    alert_type: EXACTLY "sparks_detected".
    """
    bbox_area = max(1, (bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"]))

    resolved_evidence_key = (
        evidence_key
        or detection_metadata.get("evidence_key")
        or frame_reference
    )
    resolved_evidence_bucket = (
        evidence_bucket
        or detection_metadata.get("evidence_bucket")
        or ("innovision-frames" if resolved_evidence_key else None)
    )

    return AlertEvent(
        camera_id=camera_id,
        timestamp=datetime.now(timezone.utc),
        severity=severity,
        alert_type="sparks_detected",
        title=f"Sparks Detected: {zone_name}",
        description=(
            f"Sparks/arc flash detected in zone with {final_confidence * 100:.0f}% confidence"
        ),
        source_event_id=source_event_id,
        source_uc=SourceUC.UC2,
        frame_reference=frame_reference,
        frame_provider=frame_provider,
        metadata={
            "detection_type": "sparks",
            "confidence": round(float(final_confidence), 4),
            "verification_score": round(float(verification_score), 4),
            "sparks_area_px": bbox_area,
            "bbox": bbox,
            "zone_id": zone_id,
            "zone_name": zone_name,
            "persistence_count": persistence_count,
            "evidence_key": resolved_evidence_key,
            "evidence_bucket": resolved_evidence_bucket,
            "hsv_score": verification_details.get("hsv_score", 0.0),
            "texture_score": verification_details.get("texture_score", 0.0),
            "temporal_score": verification_details.get("temporal_score", 0.0),
            **{
                k: v
                for k, v in detection_metadata.items()
                if k not in ("frame_seq", "evidence_key", "evidence_bucket")
            },
        },
    )


def build_alert_from_detection(
    *,
    camera_id: UUID,
    source_event_id: UUID,
    detection_type: str,
    severity: AlertSeverity,
    final_confidence: float,
    bbox: Dict[str, int],
    zone_name: str,
    zone_id: str,
    verification_score: float,
    persistence_count: int,
    verification_details: Dict[str, Any],
    detection_metadata: Dict[str, Any],
    frame_reference: Optional[str] = None,
    frame_provider: Optional[FrameProvider] = None,
    evidence_key: Optional[str] = None,
    evidence_bucket: Optional[str] = None,
) -> AlertEvent:
    """
    Dispatch to the correct alert builder based on detection_type.

    detection_type "fire"   → alert_type "fire_detected"
    detection_type "sparks" → alert_type "sparks_detected"
    detection_type "smoke"  → alert_type "smoke_detected"
    """
    if detection_type == "fire":
        return build_fire_detected_alert(
            camera_id=camera_id,
            source_event_id=source_event_id,
            detection_type=detection_type,
            severity=severity,
            final_confidence=final_confidence,
            bbox=bbox,
            zone_name=zone_name,
            zone_id=zone_id,
            verification_score=verification_score,
            persistence_count=persistence_count,
            verification_details=verification_details,
            detection_metadata=detection_metadata,
            frame_reference=frame_reference,
            frame_provider=frame_provider,
            evidence_key=evidence_key,
            evidence_bucket=evidence_bucket,
        )
    elif detection_type in ("sparks", "spark"):
        return build_sparks_detected_alert(
            camera_id=camera_id,
            source_event_id=source_event_id,
            severity=severity,
            final_confidence=final_confidence,
            bbox=bbox,
            zone_name=zone_name,
            zone_id=zone_id,
            verification_score=verification_score,
            persistence_count=persistence_count,
            verification_details=verification_details,
            detection_metadata=detection_metadata,
            frame_reference=frame_reference,
            frame_provider=frame_provider,
            evidence_key=evidence_key,
            evidence_bucket=evidence_bucket,
        )
    else:
        return build_smoke_detected_alert(
            camera_id=camera_id,
            source_event_id=source_event_id,
            severity=severity,
            final_confidence=final_confidence,
            bbox=bbox,
            zone_name=zone_name,
            zone_id=zone_id,
            verification_score=verification_score,
            persistence_count=persistence_count,
            verification_details=verification_details,
            detection_metadata=detection_metadata,
            frame_reference=frame_reference,
            frame_provider=frame_provider,
            evidence_key=evidence_key,
            evidence_bucket=evidence_bucket,
        )
