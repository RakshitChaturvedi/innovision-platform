"""
CameraWorker — Autonomous Per-Camera Processing Worker for UC2.

Consumes FrameEvents, runs the 6-stage DetectionPipeline, uploads evidence snapshots
to MinIO, publishes AlertEvents to alerts:live, maintains MJPEG preview frames, and
instruments Prometheus metrics.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

import cv2
import numpy as np
import redis.asyncio as aioredis

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, FrameProvider, SourceUC
from shared.contracts.frame_event import FrameEvent
from shared.platform_client.alert_publisher import AlertPublisher
from services.uc2_fire_smoke.src.config import settings
from services.uc2_fire_smoke.src.detection.pipeline import ConfirmedDetection, DetectionPipeline, DetectionResult
from services.uc2_fire_smoke.src.metrics.prometheus import (
    ALERTS_GENERATED,
    CAMERA_FPS,
    DROPPED_FRAMES,
    E2E_LATENCY,
    FALSE_ALARMS,
    FIRE_DETECTIONS,
    FRAMES_PROCESSED,
    INFERENCE_LATENCY,
    SMOKE_DETECTIONS,
    VERIFICATION_LATENCY,
)
from services.uc2_fire_smoke.src.redis.frame_consumer import RedisFrameConsumer
from services.uc2_fire_smoke.src.storage.minio_client import MinIOClient
from services.uc2_fire_smoke.src.storage.evidence_db import record_detection_backup

logger = logging.getLogger("innovision.uc2.camera_worker")


from collections import deque
from enum import Enum


class CameraHealthState(str, Enum):
    """Production health state of a camera stream."""
    ONLINE = "online"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"
    ERROR = "error"


class CameraWorker:
    """
    Independent worker instance for a single camera feed with
    resilient state machine, evidence buffer, and metric telemetry.
    """

    def __init__(
        self,
        camera_id: str,
        camera_name: str,
        camera_location: str,
        redis_client: aioredis.Redis,
        detection_pipeline: DetectionPipeline,
        alert_publisher: AlertPublisher,
        minio_client: Optional[MinIOClient] = None,
    ) -> None:
        self.camera_id = camera_id
        self.camera_name = camera_name
        self.camera_location = camera_location
        self.redis = redis_client
        self.pipeline = detection_pipeline
        self.publisher = alert_publisher
        self.minio = minio_client or MinIOClient()

        self.consumer = RedisFrameConsumer(
            redis_client=self.redis,
            camera_id=self.camera_id,
            minio_client=self.minio,
        )

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._prev_frame: Optional[np.ndarray] = None
        self._latest_annotated_jpeg: Optional[bytes] = None
        self._last_alert_time: Dict[str, float] = {}  # key -> timestamp
        self._fps_counter = 0
        self._fps_timer = time.time()
        self.current_fps = 0.0
        self.last_seen_timestamp = time.time()
        self.last_successful_frame_ts = time.time()

        # Production health & telemetry counters
        self.state = CameraHealthState.ONLINE
        self.received_frames = 0
        self.processed_frames = 0
        self.skipped_frames = 0
        self.dropped_frames = 0
        self.reconnect_count = 0
        self.is_paused = False
        self.last_error_message = ""

        self.current_frame_age_ms = 0.0
        self.active_hazards: List[str] = []
        self._frame_buffer: deque = deque(maxlen=settings.evidence_buffer_size)

    def pause(self) -> None:
        """Pause worker processing on camera disconnect/maintenance."""
        self.is_paused = True
        self.state = CameraHealthState.RECONNECTING

    def resume(self) -> None:
        """Resume worker processing after reconnect."""
        self.is_paused = False
        self.state = CameraHealthState.ONLINE

    def get_health_state(self) -> CameraHealthState:
        """Determine real-time camera health state based on elapsed heartbeat."""
        if not self._running:
            return CameraHealthState.OFFLINE
        if self.is_paused:
            return CameraHealthState.RECONNECTING
        if self.last_error_message:
            return CameraHealthState.ERROR
        elapsed = time.time() - self.last_seen_timestamp
        if elapsed > settings.camera_stale_threshold_s:
            return CameraHealthState.OFFLINE
        if elapsed > settings.camera_degraded_threshold_s:
            return CameraHealthState.DEGRADED
        return CameraHealthState.ONLINE


    def get_diagnostics(self) -> dict:
        """Export comprehensive diagnostic metrics for dashboard and monitoring."""
        now = time.time()
        health = self.get_health_state()
        return {
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "camera_location": self.camera_location,
            "status": health.value,
            "fps": self.current_fps,
            "received_frames": self.received_frames,
            "processed_frames": self.processed_frames,
            "skipped_frames": self.skipped_frames,
            "dropped_frames": self.dropped_frames,
            "reconnect_count": self.reconnect_count,
            "frame_age_ms": round(self.current_frame_age_ms, 2),
            "last_seen_s_ago": round(now - self.last_seen_timestamp, 1),
            "active_hazards": list(self.active_hazards),
            "last_error": self.last_error_message,
        }

    def get_latest_preview_jpeg(self) -> Optional[bytes]:
        """Return the most recent annotated JPEG frame for MJPEG streaming."""
        return self._latest_annotated_jpeg

    async def start(self) -> None:
        """Start the worker processing loop in the background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(f"CameraWorker started for camera {self.camera_id} ({self.camera_name})")

    async def stop(self) -> None:
        """Gracefully terminate worker."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"CameraWorker stopped for camera {self.camera_id}")

    async def _run_loop(self) -> None:
        logger.info(f"Entering frame consumption loop for camera {self.camera_id}")

        while self._running:
            try:
                # Read frames in non-blocking batches
                async for msg_id, frame_event, frame_img in self.consumer.read_frames(
                    batch_size=settings.stream_batch_size,
                    block_ms=settings.stream_block_ms,
                ):
                    if not self._running:
                        break

                    t_event_start = time.perf_counter()
                    now_ts = time.time()
                    self.last_seen_timestamp = now_ts
                    self.received_frames += 1
                    self.skipped_frames = getattr(self.consumer, "skipped_frames", 0)
                    self.last_error_message = None

                    # Compute real-time frame age
                    if getattr(frame_event, "timestamp", None):
                        try:
                            ts_sec = frame_event.timestamp.timestamp()
                            self.current_frame_age_ms = max(0.0, (now_ts - ts_sec) * 1000.0)
                        except Exception:
                            self.current_frame_age_ms = 0.0

                    if frame_img is None:
                        self.dropped_frames += 1
                        DROPPED_FRAMES.labels(camera_id=self.camera_id).inc()
                        await self.consumer.ack(msg_id)
                        continue

                    # Maintain rolling frame buffer for pre-event evidence
                    self._frame_buffer.append((frame_event.frame_seq, frame_img.copy()))

                    # Update FPS calculation
                    self._update_fps()

                    # Execute 6-stage detection pipeline
                    result: DetectionResult = self.pipeline.process_frame(
                        camera_id=self.camera_id,
                        frame_seq=frame_event.frame_seq,
                        frame_bgr=frame_img,
                        prev_frame_bgr=self._prev_frame,
                    )
                    self._prev_frame = frame_img.copy()
                    self.processed_frames += 1

                    # Update active hazards for real-time camera status
                    self.active_hazards = {det.detection_type for det in result.confirmed_detections}

                    # Record Prometheus metrics
                    FRAMES_PROCESSED.labels(camera_id=self.camera_id).inc()
                    INFERENCE_LATENCY.labels(camera_id=self.camera_id).observe(
                        result.inference_latency_ms / 1000.0
                    )
                    VERIFICATION_LATENCY.labels(camera_id=self.camera_id).observe(
                        result.verification_latency_ms / 1000.0
                    )

                    for supp in result.suppressed_detections:
                        FALSE_ALARMS.labels(
                            camera_id=self.camera_id,
                            reason=supp.get("reason", "unknown"),
                            detection_type=supp.get("detection_type", "unknown"),
                        ).inc()

                    # Annotate frame for live preview
                    annotated_frame = self._annotate_frame(frame_img, result)
                    _, encoded = cv2.imencode(".jpg", annotated_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
                    self._latest_annotated_jpeg = encoded.tobytes()

                    # Process confirmed detections
                    if result.has_detections:
                        await self._handle_confirmed_detections(
                            result=result,
                            frame_event=frame_event,
                            annotated_image=annotated_frame,
                            t_start=t_event_start,
                        )

                    # Acknowledge frame event
                    await self.consumer.ack(msg_id)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                self.last_error_message = str(exc)
                logger.error(f"Error in CameraWorker loop for {self.camera_id}: {exc}", exc_info=True)
                await asyncio.sleep(1.0)

    def _update_fps(self) -> None:
        self._fps_counter += 1
        elapsed = time.time() - self._fps_timer
        if elapsed >= 1.0:
            self.current_fps = round(self._fps_counter / elapsed, 2)
            CAMERA_FPS.labels(camera_id=self.camera_id).set(self.current_fps)
            self._fps_counter = 0
            self._fps_timer = time.time()

    def _annotate_frame(self, frame: np.ndarray, result: DetectionResult) -> np.ndarray:
        """Render bounding boxes and metadata badges onto preview frame."""
        vis = frame.copy()
        h, w = vis.shape[:2]

        # Draw confirmed detections
        colors = {
            "fire": (0, 30, 255),
            "smoke": (0, 140, 255),
            "sparks": (0, 215, 255),
            "spark": (0, 215, 255),
        }
        for det in result.confirmed_detections:
            color = colors.get(det.detection_type, (0, 255, 255))
            bx = det.bbox
            x1, y1, x2, y2 = bx["x1"], bx["y1"], bx["x2"], bx["y2"]
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)

            label = f"{det.detection_type.upper()} {det.final_confidence:.2f} [{det.zone.zone_name}]"
            cv2.putText(
                vis, label, (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA,
            )

        # Draw HUD bar at top
        hud_text = f"UC2 FIRE & SMOKE | Cam: {self.camera_name} | FPS: {self.current_fps} | Seq: {result.frame_seq}"
        cv2.putText(vis, hud_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

        return vis

    async def _handle_confirmed_detections(
        self,
        result: DetectionResult,
        frame_event: FrameEvent,
        annotated_image: np.ndarray,
        t_start: float,
    ) -> None:
        """Evaluate cooldown, upload evidence with retry resilience, and publish AlertEvent."""
        now = time.time()

        for det in result.confirmed_detections:
            if det.detection_type == "fire":
                FIRE_DETECTIONS.labels(camera_id=self.camera_id, zone_id=det.zone.zone_id).inc()
            elif det.detection_type == "smoke":
                SMOKE_DETECTIONS.labels(camera_id=self.camera_id, zone_id=det.zone.zone_id).inc()

            cooldown_key = f"{det.detection_type}:{det.zone.zone_id}"
            last_alert = self._last_alert_time.get(cooldown_key, 0.0)

            if (now - last_alert) < settings.alert_cooldown_s:
                # Cooldown active, skip duplicate alert publication
                continue

            self._last_alert_time[cooldown_key] = now

            # Generate unique alert UUID
            alert_uuid = uuid4()

            # Upload evidence snapshot to MinIO with bounded retry resilience
            evidence_key = None
            evidence_error = None
            for attempt in range(3):
                try:
                    evidence_key = await self.minio.upload_evidence(
                        camera_id=self.camera_id,
                        alert_id=str(alert_uuid),
                        image_bgr=annotated_image,
                        jpeg_quality=settings.jpeg_quality,
                    )
                    if evidence_key:
                        break
                except Exception as exc:
                    evidence_error = str(exc)
                    if attempt < 2:
                        await asyncio.sleep(0.05 * (attempt + 1))

            if not evidence_key:
                logger.warning(
                    f"MinIO evidence storage unavailable ({evidence_error}); falling back to source frame reference for alert {alert_uuid}"
                )

            # Build enriched metadata dictionary
            metadata: Dict[str, Any] = {
                "confidence": det.final_confidence,
                "fire_confidence": det.yolo_confidence if det.detection_type == "fire" else 0.0,
                "smoke_confidence": det.yolo_confidence if det.detection_type == "smoke" else 0.0,
                "verification_score": det.verification_score,
                "zone_id": det.zone.zone_id,
                "zone_name": det.zone.zone_name,
                "zone_priority": det.zone.zone_priority,
                "camera_name": self.camera_name,
                "camera_location": self.camera_location,
                "bounding_boxes": [det.bbox],
                "latency_ms": round(result.total_pipeline_latency_ms, 2),
                "fps": self.current_fps,
                "model_version": settings.model_version,
                "pipeline_version": settings.pipeline_version,
                "verification_details": det.verification_details,
                "false_alarm_reason": None,
                "frame_seq": result.frame_seq,
                "evidence_status": "stored" if evidence_key else "fallback",
            }

            # Title & description
            title = f"{det.detection_type.capitalize()} Detected in {det.zone.zone_name}"
            description = (
                f"{det.detection_type.capitalize()} detected with confidence "
                f"{det.final_confidence:.2f} at {self.camera_name} ({self.camera_location}). "
                f"Verification score: {det.verification_score:.2f}."
            )

            # Build canonical AlertEvent
            alert_event = AlertEvent(
                alert_id=alert_uuid,
                camera_id=self.camera_id,
                severity=det.severity,
                alert_type=f"{det.detection_type}_detected",
                title=title,
                description=description,
                source_event_id=str(frame_event.event_id),
                source_uc=SourceUC.uc2,
                frame_reference=evidence_key or frame_event.frame_reference,
                frame_provider=FrameProvider.minio if evidence_key else frame_event.frame_provider,
                metadata=metadata,
            )

            # Publish AlertEvent via shared AlertPublisher
            success = await self.publisher.publish(alert_event)
            if success:
                ALERTS_GENERATED.labels(
                    camera_id=self.camera_id,
                    severity=det.severity.value,
                    alert_type=alert_event.alert_type,
                ).inc()

            # Record in isolated UC2 evidence backup table (fail-safe non-blocking)
            asyncio.create_task(
                record_detection_backup(
                    camera_id=self.camera_id,
                    alert_id=str(alert_uuid),
                    detection_type=det.detection_type,
                    confidence=det.final_confidence,
                    verification_score=det.verification_score,
                    bbox=det.bbox,
                    source_type="rtsp",
                    frame_seq=result.frame_seq,
                    evidence_key=evidence_key,
                    metadata=metadata,
                )
            )

            e2e_lat = time.perf_counter() - t_start
            E2E_LATENCY.labels(camera_id=self.camera_id).observe(e2e_lat)

