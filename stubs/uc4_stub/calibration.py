"""
calibration.py — UC4-owned camera calibration lookup.

FIX #7: Reads from uc4_camera_calibration table (UC4-owned, not platform schema).
Provides calibration data to the cv_engine SpeedEstimator.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

logger = logging.getLogger("uc4.calibration")

# ── Configuration ─────────────────────────────────────────────────

UC4_DATABASE_URL = os.getenv(
    "UC4_DATABASE_URL",
    os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://innovision:changeme@postgres:5432/innovision_platform",
    ),
)


@dataclass(frozen=True)
class CameraCalibration:
    """Calibration data for a single camera's speed estimation zone."""
    camera_id: UUID
    speed_polygon_normalized: list[dict]
    distance_between_lines_meters: float
    entry_line: Optional[dict] = None
    exit_line: Optional[dict] = None


# ── Engine / Session ──────────────────────────────────────────────

_engine = None
_session_factory = None


def _get_session_factory():
    global _engine, _session_factory
    if _session_factory is None:
        _engine = create_async_engine(
            UC4_DATABASE_URL,
            pool_size=3,
            max_overflow=2,
            pool_pre_ping=True,
        )
        _session_factory = async_sessionmaker(
            _engine,
            expire_on_commit=False,
        )
    return _session_factory


async def get_calibration(camera_id: UUID) -> Optional[CameraCalibration]:
    """
    Look up calibration for a camera from uc4_camera_calibration.
    Returns None if no calibration row exists (caller should skip speed estimation).
    """
    factory = _get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                text("""
                    SELECT camera_id, speed_polygon_normalized,
                           distance_between_lines_meters, entry_line, exit_line
                    FROM uc4_camera_calibration
                    WHERE camera_id = :camera_id
                """),
                {"camera_id": str(camera_id)},
            )
            row = result.fetchone()
            if row is None:
                logger.warning(
                    "no_calibration_found camera_id=%s — speed estimation will be skipped",
                    camera_id,
                )
                return None

            mapping = row._mapping
            return CameraCalibration(
                camera_id=UUID(str(mapping["camera_id"])),
                speed_polygon_normalized=mapping["speed_polygon_normalized"],
                distance_between_lines_meters=float(
                    mapping["distance_between_lines_meters"]
                ),
                entry_line=mapping.get("entry_line"),
                exit_line=mapping.get("exit_line"),
            )
    except Exception as exc:
        logger.error(
            "calibration_lookup_failed camera_id=%s error=%s",
            camera_id,
            exc,
        )
        return None


async def close_engine() -> None:
    """Dispose of the calibration DB engine on shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
