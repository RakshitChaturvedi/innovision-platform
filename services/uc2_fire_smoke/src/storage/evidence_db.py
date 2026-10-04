"""
EvidenceDB — Isolated Database Persistence Backup for UC2.

Stores detection events, evidence keys, bounding boxes, and verification
telemetry in the dedicated `uc2_detection_events` PostgreSQL table as a backup.
Operates asynchronously with fail-safe error isolation.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import text
from services.uc2_fire_smoke.src.config import settings

logger = logging.getLogger("innovision.uc2.evidence_db")

_engine = None


def get_db_engine():
    global _engine
    if _engine is None:
        db_url = settings.database_url
        if not db_url:
            return None
        # In case the URL is sync postgresql://, adapt for asyncpg or sync fallback
        from sqlalchemy.ext.asyncio import create_async_engine
        try:
            if "postgresql+asyncpg://" in db_url:
                async_url = db_url
            elif "postgresql://" in db_url:
                async_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
            else:
                async_url = db_url
            _engine = create_async_engine(async_url, pool_size=5, max_overflow=5, pool_pre_ping=True)
        except Exception as exc:
            logger.warning(f"Could not initialize async DB engine for UC2 backup: {exc}")
            _engine = None
    return _engine


async def record_detection_backup(
    camera_id: Optional[str],
    alert_id: Optional[str],
    detection_type: str,
    confidence: float,
    verification_score: Optional[float] = None,
    bbox: Optional[Dict[str, int]] = None,
    area: Optional[int] = None,
    area_percentage: Optional[float] = None,
    source_type: str = "rtsp",
    frame_seq: Optional[int] = None,
    evidence_key: Optional[str] = None,
    evidence_bucket: str = "innovision-evidence",
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Safely persist a detection event and evidence record to uc2_detection_events.
    Fails soft without raising exceptions if database is unreachable.
    """
    engine = get_db_engine()
    if engine is None:
        return False

    x1 = bbox.get("x1") if bbox else None
    y1 = bbox.get("y1") if bbox else None
    x2 = bbox.get("x2") if bbox else None
    y2 = bbox.get("y2") if bbox else None

    # Calculate dimensions if not directly passed
    if area is None and x1 is not None and x2 is not None and y1 is not None and y2 is not None:
        area = max(0, x2 - x1) * max(0, y2 - y1)

    insert_sql = text("""
        INSERT INTO uc2_detection_events (
            id, alert_id, camera_id, detection_type, confidence,
            verification_score, bbox_x1, bbox_y1, bbox_x2, bbox_y2,
            area, area_percentage, source_type, frame_seq,
            evidence_key, evidence_bucket, metadata
        ) VALUES (
            :id, :alert_id, :camera_id, :detection_type, :confidence,
            :verification_score, :bbox_x1, :bbox_y1, :bbox_x2, :bbox_y2,
            :area, :area_percentage, :source_type, :frame_seq,
            :evidence_key, :evidence_bucket, :metadata
        )
    """)

    params = {
        "id": str(uuid4()),
        "alert_id": alert_id,
        "camera_id": camera_id,
        "detection_type": detection_type,
        "confidence": float(confidence),
        "verification_score": float(verification_score) if verification_score is not None else None,
        "bbox_x1": x1,
        "bbox_y1": y1,
        "bbox_x2": x2,
        "bbox_y2": y2,
        "area": area,
        "area_percentage": float(area_percentage) if area_percentage is not None else None,
        "source_type": source_type,
        "frame_seq": frame_seq,
        "evidence_key": evidence_key,
        "evidence_bucket": evidence_bucket,
        "metadata": json.dumps(metadata or {}),
    }

    try:
        async with engine.begin() as conn:
            await conn.execute(insert_sql, params)
        logger.debug(f"Recorded UC2 evidence backup for alert {alert_id} ({detection_type})")
        return True
    except Exception as exc:
        logger.warning(f"UC2 evidence backup write failed (non-blocking fallback): {exc}")
        return False
