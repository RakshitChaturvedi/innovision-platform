"""
UC3 Event Persistence, MinIO Snapshot Storage & Canonical Alert Publisher
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import os
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

import cv2
import numpy as np
import redis.asyncio as aioredis
from minio import Minio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher
from services.uc3.src.ppe_config import CONF_THRESHOLD

logger = logging.getLogger("uc3_publisher")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.environ.get("MINIO_SECURE", "false").lower() in ("true", "1", "yes")
MINIO_SNAPSHOTS_BUCKET = os.environ.get("MINIO_SNAPSHOTS_BUCKET", "innovision-snapshots")

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://innovision:changeme@postgres:5432/innovision_platform",
)

class UC3EventPublisher:
    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._alert_publisher = AlertPublisher(redis_client)
        self._engine = create_async_engine(DATABASE_URL, pool_size=5, max_overflow=10)
        self._sessionmaker = async_sessionmaker(self._engine, expire_on_commit=False)

        self._minio_client = Minio(
            endpoint=MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        self._ensure_snapshot_bucket()

    def _ensure_snapshot_bucket(self) -> None:
        try:
            if not self._minio_client.bucket_exists(MINIO_SNAPSHOTS_BUCKET):
                self._minio_client.make_bucket(MINIO_SNAPSHOTS_BUCKET)
                logger.info("created_minio_snapshots_bucket name=%s", MINIO_SNAPSHOTS_BUCKET)
        except Exception as e:
            logger.warning("minio_snapshots_bucket_warning name=%s error=%s", MINIO_SNAPSHOTS_BUCKET, e)

    async def get_camera_zone_and_rules(
        self, camera_id: str
    ) -> tuple[Optional[UUID], Optional[frozenset[str]], str, float]:
        """
        Runtime zone determination:
        1. Look up camera in cameras table (id, organization_id, zone_id, metadata).
        2. Prefer native cameras.zone_id column.
        3. Fall back to metadata['zone_id'] only if safe UUID.
        4. Validate resolved zone exists, is active, and matches camera tenant/org.
        5. Fetch PPE rules from uc3_zone_ppe_rules or fallback to zones.required_ppe.
        6. Determine zone-specific min_confidence (or CONF_THRESHOLD).
        7. Fail-safe on invalid/missing/cross-tenant assignments without silent default rule assumption.
        """
        default_conf = CONF_THRESHOLD
        try:
            async with self._sessionmaker() as session:
                cam_res = await session.execute(
                    text("SELECT id, organization_id, zone_id, metadata FROM cameras WHERE id = :id"),
                    {"id": camera_id},
                )
                cam_row = cam_res.fetchone()
                if not cam_row:
                    logger.warning("camera_not_found camera_id=%s", camera_id)
                    return None, None, "Unknown Camera", default_conf

                cam_org_id = str(cam_row.organization_id) if cam_row.organization_id else None

                # 1. Prefer native cameras.zone_id column
                zone_val = cam_row.zone_id
                is_from_metadata = False

                # 2. Fallback to metadata['zone_id'] only if native zone_id is unset
                if not zone_val and cam_row.metadata and isinstance(cam_row.metadata, dict):
                    meta_zone = cam_row.metadata.get("zone_id")
                    if meta_zone:
                        zone_val = meta_zone
                        is_from_metadata = True

                # If camera is genuinely unassigned, return intended default policy
                if not zone_val:
                    logger.debug("camera_unassigned camera_id=%s", camera_id)
                    return None, None, "Unassigned Camera", default_conf

                # Validate UUID format
                try:
                    zone_uuid = UUID(str(zone_val))
                except (ValueError, TypeError, AttributeError) as e:
                    logger.error(
                        "camera_zone_resolution_invalid_uuid camera_id=%s zone_val=%s from_metadata=%s error=%s",
                        camera_id, zone_val, is_from_metadata, e
                    )
                    # Fail-safe: do not silently apply arbitrary default rules to invalid zone
                    return None, frozenset(), "Invalid Zone UUID", default_conf

                # 3. Query zone from authoritative platform hierarchy (zones + sites) and uc3_zones
                z_res = await session.execute(
                    text("""
                        SELECT z.id, z.name, z.active, s.organization_id, z.required_ppe
                        FROM zones z
                        LEFT JOIN sites s ON z.site_id = s.id
                        WHERE z.id = :id
                    """),
                    {"id": str(zone_uuid)},
                )
                z_row = z_res.fetchone()

                uz_res = await session.execute(
                    text("""
                        SELECT id, name, organization_id, is_active
                        FROM uc3_zones
                        WHERE id = :id
                    """),
                    {"id": str(zone_uuid)},
                )
                uz_row = uz_res.fetchone()

                # Check existence
                if not z_row and not uz_row:
                    logger.error(
                        "camera_assigned_zone_not_found camera_id=%s zone_id=%s",
                        camera_id, zone_uuid
                    )
                    # Fail-safe: explicitly assigned zone that cannot be resolved
                    return None, frozenset(), f"Zone Not Found ({zone_uuid})", default_conf

                zone_name = (z_row.name if z_row and z_row.name else (uz_row.name if uz_row and uz_row.name else "Named Zone"))

                # Check active status
                is_active = True
                if z_row is not None and z_row.active is not None:
                    is_active = bool(z_row.active)
                elif uz_row is not None and uz_row.is_active is not None:
                    is_active = bool(uz_row.is_active)

                if not is_active:
                    logger.warning(
                        "camera_assigned_zone_inactive camera_id=%s zone_id=%s zone_name=%s",
                        camera_id, zone_uuid, zone_name
                    )
                    # Fail-safe: inactive zone does not enforce arbitrary rules
                    return None, frozenset(), f"Inactive Zone ({zone_name})", default_conf

                # Check organization / tenant isolation
                zone_org_id = None
                if z_row and z_row.organization_id:
                    zone_org_id = str(z_row.organization_id)
                elif uz_row and uz_row.organization_id:
                    zone_org_id = str(uz_row.organization_id)

                if cam_org_id and zone_org_id and cam_org_id != zone_org_id:
                    logger.error(
                        "cross_tenant_zone_violation camera_id=%s cam_org=%s zone_org=%s zone_id=%s",
                        camera_id, cam_org_id, zone_org_id, zone_uuid
                    )
                    # Fail-safe: deny cross-tenant zone
                    return None, frozenset(), "Cross-Tenant Zone Denied", default_conf

                # 4. Resolve min_confidence
                zone_min_conf = default_conf
                async def _safe_query_conf(sql: str):
                    if hasattr(session, "begin_nested"):
                        try:
                            async with session.begin_nested():
                                r = await session.execute(text(sql), {"id": str(zone_uuid)})
                                row = r.fetchone()
                                if row is not None:
                                    val = getattr(row, "min_confidence", None)
                                    if val is None:
                                        try:
                                            val = row[0]
                                        except Exception:
                                            pass
                                    if val is not None:
                                        return float(val)
                        except Exception:
                            pass
                    else:
                        try:
                            r = await session.execute(text(sql), {"id": str(zone_uuid)})
                            row = r.fetchone()
                            if row is not None:
                                val = getattr(row, "min_confidence", None)
                                if val is None:
                                    try:
                                        val = row[0]
                                    except Exception:
                                        pass
                                if val is not None:
                                    return float(val)
                        except Exception:
                            pass
                    return None

                uz_conf = await _safe_query_conf("SELECT min_confidence FROM uc3_zones WHERE id = :id")
                if uz_conf is not None:
                    zone_min_conf = uz_conf
                else:
                    z_conf = await _safe_query_conf("SELECT min_confidence FROM zones WHERE id = :id")
                    if z_conf is not None:
                        zone_min_conf = z_conf

                # 5. Query PPE rules belonging to that resolved zone
                rules_res = await session.execute(
                    text("SELECT ppe_type FROM uc3_zone_ppe_rules WHERE zone_id = :id AND required = true"),
                    {"id": str(zone_uuid)},
                )
                rule_rows = rules_res.fetchall()
                if rule_rows:
                    required_set = frozenset(r.ppe_type.lower() for r in rule_rows)
                elif z_row and z_row.required_ppe:
                    required_set = frozenset(p.lower() for p in z_row.required_ppe)
                else:
                    # Validly assigned zone has 0 required PPE rules configured
                    required_set = frozenset()

                return zone_uuid, required_set, zone_name, zone_min_conf
        except Exception as e:
            logger.error("get_camera_zone_and_rules_error camera_id=%s error=%s", camera_id, e)
            return None, frozenset(), "Resolution Error", default_conf

    async def is_camera_uc3_enabled(self, camera_id: str) -> bool:
        """
        Check whether UC3 is enabled for the camera under effective analytics configuration.
        Inspects camera_effective_analytics joined with analytics_catalog.
        Falls back to cameras.use_cases if effective analytics table has no entry.
        """
        try:
            async with self._sessionmaker() as session:
                # 1. Authoritative check in camera_effective_analytics
                eff_res = await session.execute(
                    text("""
                        SELECT e.is_active
                        FROM camera_effective_analytics e
                        JOIN analytics_catalog a ON e.analytic_id = a.id
                        WHERE e.camera_id = :id
                          AND (LOWER(a.internal_code) = 'uc3' OR LOWER(a.code) = 'uc3' OR LOWER(a.code) LIKE '%ppe%')
                    """),
                    {"id": camera_id},
                )
                eff_row = eff_res.fetchone()
                if eff_row is not None:
                    return bool(eff_row.is_active)

                # 2. Fallback to cameras table use_cases / metadata
                cam_res = await session.execute(
                    text("SELECT use_cases, metadata FROM cameras WHERE id = :id"),
                    {"id": camera_id},
                )
                cam_row = cam_res.fetchone()
                if cam_row is not None:
                    use_cases = cam_row.use_cases or []
                    norm_ucs = [str(u).strip().lower() for u in use_cases]
                    if any(u in norm_ucs for u in ("uc3", "ppe", "ppe_detection", "uc3_ppe_detection")):
                        return True
                    meta = cam_row.metadata if isinstance(cam_row.metadata, dict) else {}
                    if meta.get("uc3_enabled") is False or meta.get("disabled_uc", {}).get("uc3"):
                        return False

                return True
        except Exception as e:
            logger.debug("is_camera_uc3_enabled_error camera_id=%s error=%s", camera_id, e)
            return True

    async def persist_uc3_event(
        self,
        camera_id: UUID,
        event_type: str,
        track_id: Optional[int],
        missing_ppe: List[str],
        present_ppe: List[str],
        compliance_score: float,
        timestamp: datetime,
        frame_reference: Optional[str] = None,
        frame_provider: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        organization_id: Optional[UUID] = None,
        zone_id: Optional[UUID] = None,
    ) -> UUID:
        uc3_event_id = uuid4()
        try:
            async with self._sessionmaker() as session:
                async with session.begin():
                    await session.execute(
                        text("""
                            INSERT INTO uc3_events (
                                id, organization_id, camera_id, zone_id, track_id,
                                event_type, missing_ppe, present_ppe, compliance_score,
                                timestamp, frame_reference, frame_provider, metadata
                            )
                            VALUES (
                                :id, :organization_id, :camera_id, :zone_id, :track_id,
                                :event_type, :missing_ppe, :present_ppe, :compliance_score,
                                :timestamp, :frame_reference, :frame_provider, :metadata
                            )
                        """),
                        {
                            "id": uc3_event_id,
                            "organization_id": organization_id,
                            "camera_id": camera_id,
                            "zone_id": zone_id,
                            "track_id": track_id,
                            "event_type": event_type,
                            "missing_ppe": missing_ppe,
                            "present_ppe": present_ppe,
                            "compliance_score": compliance_score,
                            "timestamp": timestamp,
                            "frame_reference": frame_reference,
                            "frame_provider": frame_provider,
                            "metadata": json.dumps(metadata or {}),
                        },
                    )
            logger.info("persisted_uc3_event event_id=%s camera_id=%s", uc3_event_id, camera_id)
        except Exception as e:
            logger.error("persist_uc3_event_failed event_id=%s error=%s", uc3_event_id, e)
        return uc3_event_id

    def _upload_snapshot_sync(self, object_key: str, jpeg_bytes: bytes) -> None:
        self._minio_client.put_object(
            bucket_name=MINIO_SNAPSHOTS_BUCKET,
            object_name=object_key,
            data=io.BytesIO(jpeg_bytes),
            length=len(jpeg_bytes),
            content_type="image/jpeg",
        )

    async def upload_snapshot(self, alert_id: UUID, jpeg_bytes: bytes, date_str: str) -> str:
        object_key = f"uc3/alerts/{date_str}/{alert_id}.jpg"
        try:
            await asyncio.to_thread(self._upload_snapshot_sync, object_key, jpeg_bytes)
            return object_key
        except Exception as e:
            logger.warning("snapshot_upload_failed alert_id=%s error=%s", alert_id, e)
            return ""

    async def publish_violation_alert(
        self,
        camera_id: UUID,
        worker_violation: Dict[str, Any],
        raw_frame: Optional[np.ndarray],
        detections: List[Dict[str, Any]],
        timestamp: datetime,
        organization_id: Optional[UUID] = None,
        zone_id: Optional[UUID] = None,
        uc3_event_id: Optional[UUID] = None,
        source_frame_reference: Optional[str] = None,
        source_frame_provider: Optional[str] = None,
    ) -> bool:
        alert_id = uuid4()
        date_str = timestamp.strftime("%Y-%m-%d")

        # Draw annotated snapshot if frame provided
        snapshot_key = ""
        if raw_frame is not None:
            annotated = raw_frame.copy()
            h, w = annotated.shape[:2]
            for d in detections:
                box = d.get("bbox") or d.get("box")
                if not box:
                    continue
                if isinstance(box, dict):
                    bx1, by1, bx2, by2 = int(box["x1"] * w), int(box["y1"] * h), int(box["x2"] * w), int(box["y2"] * h)
                elif isinstance(box, (list, tuple)):
                    bx1, by1, bx2, by2 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
                else:
                    continue
                col = (0, 0, 255) if not d.get("compliant", True) else (0, 255, 0)
                cv2.rectangle(annotated, (bx1, by1), (bx2, by2), col, 2)
                lbl = d.get("label", "obj")
                cv2.putText(annotated, lbl, (bx1, max(15, by1 - 5)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)

            success, encoded_img = cv2.imencode(".jpg", annotated)
            if success:
                snapshot_key = await self.upload_snapshot(alert_id, encoded_img.tobytes(), date_str)

        ppe_type = worker_violation.get("ppe_type", "ppe")
        track_id = worker_violation.get("worker_id", -1)
        missing_ppe = [ppe_type]

        if not uc3_event_id:
            uc3_event_id = await self.persist_uc3_event(
                camera_id=camera_id,
                event_type="ppe_violation",
                track_id=track_id if track_id != -1 else None,
                missing_ppe=missing_ppe,
                present_ppe=[],
                compliance_score=0.0,
                timestamp=timestamp,
                frame_reference=source_frame_reference,
                frame_provider=source_frame_provider,
                metadata={
                    "violation": worker_violation.get("violation"),
                    "confidence": worker_violation.get("confidence"),
                },
                organization_id=organization_id,
                zone_id=zone_id,
            )

        # 2. Build AlertEvent with real source_event_id
        alert_event = AlertEvent(
            alert_id=alert_id,
            camera_id=camera_id,
            timestamp=timestamp,
            severity=AlertSeverity.HIGH,
            alert_type="ppe_violation",
            title=f"PPE Violation — Missing {ppe_type.replace('_', ' ').title()}",
            description=f"Worker {track_id if track_id != -1 else 'untracked'} detected missing required {ppe_type.replace('_', ' ')}.",
            source_event_id=uc3_event_id,
            source_uc=SourceUC.UC3,
            frame_reference=snapshot_key if snapshot_key else None,
            frame_provider=FrameProvider.MINIO if snapshot_key else None,
            status=AlertStatus.PENDING,
            metadata={
                "track_id": track_id,
                "ppe_type": ppe_type,
                "missing_ppe": missing_ppe,
                "zone_id": str(zone_id) if zone_id else None,
            },
        )

        # 3. Publish via canonical AlertPublisher
        published = await self._alert_publisher.publish(alert_event)
        logger.info(
            "published_uc3_alert alert_id=%s source_event_id=%s camera_id=%s ppe_type=%s success=%s",
            alert_id, uc3_event_id, camera_id, ppe_type, published
        )
        return published

    async def close(self) -> None:
        await self._engine.dispose()
