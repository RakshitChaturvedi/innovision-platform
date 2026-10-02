"""
PipelineManager — Multi-Camera Lifecycle Orchestrator for UC2.

Coordinates CameraRegistry discovery, PubSub updates, per-camera CameraWorkers,
YOLO model warmup, and graceful shutdown.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

import redis.asyncio as aioredis

from shared.platform_client.alert_publisher import AlertPublisher
from services.uc2_fire_smoke.src.config import settings
from services.uc2_fire_smoke.src.detection.engine import YOLOEngine
from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline
from services.uc2_fire_smoke.src.detection.zone_engine import ZoneDefinition, ZoneEngine
from services.uc2_fire_smoke.src.metrics.prometheus import ACTIVE_WORKERS, HEALTH_STATUS, OFFLINE_CAMERAS
from services.uc2_fire_smoke.src.redis.pubsub_listener import CameraPubSubListener
from services.uc2_fire_smoke.src.storage.minio_client import MinIOClient
from services.uc2_fire_smoke.src.workers.camera_registry_client import CameraRegistryClient
from services.uc2_fire_smoke.src.workers.camera_worker import CameraWorker

logger = logging.getLogger("innovision.uc2.pipeline_manager")


class PipelineManager:
    """
    Manages all camera workers and lifecycle events across the UC2 service.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        minio_client: Optional[MinIOClient] = None,
    ) -> None:
        self.redis = redis_client
        self.minio = minio_client or MinIOClient()
        self.registry_client = CameraRegistryClient()
        self.alert_publisher = AlertPublisher(redis_client=self.redis)

        # Core engines
        self.yolo_engine = YOLOEngine()
        self.zone_engine = ZoneEngine()
        self.pipeline = DetectionPipeline(
            yolo_engine=self.yolo_engine,
            zone_engine=self.zone_engine,
        )

        # Worker map: camera_id -> CameraWorker
        self._workers: Dict[str, CameraWorker] = {}
        self._pubsub_listener: Optional[CameraPubSubListener] = None
        self._reconcile_task: Optional[asyncio.Task] = None
        self._running = False
        self.start_time = time.time()

    async def start(self) -> None:
        """Start manager, discover cameras, and launch worker tasks."""
        if self._running:
            return
        self._running = True
        HEALTH_STATUS.set(1)

        # 1. Start PubSub listener
        self._pubsub_listener = CameraPubSubListener(
            redis_client=self.redis,
            on_camera_added=self.on_camera_added,
            on_camera_updated=self.on_camera_updated,
            on_camera_removed=self.on_camera_removed,
        )
        await self._pubsub_listener.start()

        # 2. Initial camera discovery
        await self.reconcile_cameras()

        # 3. Start periodic reconciliation loop
        self._reconcile_task = asyncio.create_task(self._periodic_reconcile())
        logger.info("UC2 PipelineManager initialized and running")

    async def stop(self) -> None:
        """Stop all workers, pubsub listener, and close HTTP clients."""
        self._running = False
        HEALTH_STATUS.set(0)

        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()
            try:
                await self._reconcile_task
            except asyncio.CancelledError:
                pass

        if self._pubsub_listener:
            await self._pubsub_listener.stop()

        # Stop all camera workers concurrently
        stop_tasks = [worker.stop() for worker in self._workers.values()]
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        self._workers.clear()
        ACTIVE_WORKERS.set(0)

        await self.registry_client.close()
        logger.info("UC2 PipelineManager shutdown complete")

    async def reconcile_cameras(self) -> None:
        """Fetch camera list from registry and sync active worker instances."""
        try:
            cameras = await self.registry_client.get_active_cameras(uc_id="uc2")
            active_ids = set()

            for cam in cameras:
                cam_id = str(cam.get("id"))
                active_ids.add(cam_id)
                name = cam.get("name", f"Camera-{cam_id[:8]}")
                location = cam.get("location", "Unknown Location")

                # Parse zones from metadata if present
                meta = cam.get("metadata") or {}
                raw_zones = meta.get("zones") or []
                if raw_zones and isinstance(raw_zones, list):
                    parsed_zones = []
                    for z in raw_zones:
                        try:
                            parsed_zones.append(
                                ZoneDefinition(
                                    zone_id=str(z.get("zone_id", f"zone-{len(parsed_zones)}")),
                                    zone_name=str(z.get("zone_name", "ROI")),
                                    priority=str(z.get("priority", "HIGH")),
                                    polygon=z.get("polygon", []),
                                    alert_on_fire=z.get("alert_on_fire", True),
                                    alert_on_smoke=z.get("alert_on_smoke", True),
                                )
                            )
                        except Exception as z_err:
                            logger.warning(f"Failed to parse zone: {z_err}")
                    if parsed_zones:
                        self.zone_engine.set_camera_zones(cam_id, parsed_zones)

                if cam_id not in self._workers:
                    await self._start_worker_for_camera(cam_id, name, location)

            # Terminate workers for removed cameras
            for existing_id in list(self._workers.keys()):
                if existing_id not in active_ids:
                    await self._stop_worker_for_camera(existing_id)

            ACTIVE_WORKERS.set(len(self._workers))
        except Exception as exc:
            logger.error(f"Error during camera reconciliation: {exc}")

    async def _start_worker_for_camera(self, camera_id: str, name: str, location: str) -> None:
        if camera_id in self._workers:
            return
        worker = CameraWorker(
            camera_id=camera_id,
            camera_name=name,
            camera_location=location,
            redis_client=self.redis,
            detection_pipeline=self.pipeline,
            alert_publisher=self.alert_publisher,
            minio_client=self.minio,
        )
        self._workers[camera_id] = worker
        await worker.start()
        ACTIVE_WORKERS.set(len(self._workers))
        logger.info(f"Spawned worker for camera {camera_id}")

    async def _stop_worker_for_camera(self, camera_id: str) -> None:
        worker = self._workers.pop(camera_id, None)
        if worker:
            await worker.stop()
            ACTIVE_WORKERS.set(len(self._workers))
            OFFLINE_CAMERAS.labels(camera_id=camera_id).inc()
            logger.info(f"Stopped worker for camera {camera_id}")

    async def on_camera_added(self, camera_id: str) -> None:
        cam_data = await self.registry_client.get_camera(camera_id)
        name = cam_data.get("name", f"Camera-{camera_id[:8]}") if cam_data else f"Camera-{camera_id[:8]}"
        location = cam_data.get("location", "Unknown") if cam_data else "Unknown"
        await self._start_worker_for_camera(camera_id, name, location)

    async def on_camera_updated(self, camera_id: str) -> None:
        await self._stop_worker_for_camera(camera_id)
        await self.on_camera_added(camera_id)

    async def on_camera_removed(self, camera_id: str) -> None:
        await self._stop_worker_for_camera(camera_id)

    async def _periodic_reconcile(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(settings.camera_refresh_interval_s)
                if self._running:
                    await self.reconcile_cameras()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in periodic reconcile task: {exc}")

    def get_preview_jpeg(self, camera_id: str) -> Optional[bytes]:
        """Fetch current annotated JPEG preview for camera."""
        worker = self._workers.get(camera_id)
        if worker:
            return worker.get_latest_preview_jpeg()
        return None

    def get_pipeline_status(self) -> dict:
        """Return operational overview of pipeline, model diagnostics, and all camera workers."""
        now = time.time()
        worker_statuses = []
        online_count = 0
        degraded_count = 0
        offline_count = 0
        error_count = 0

        for cam_id, worker in self._workers.items():
            diag = worker.get_diagnostics()
            diag["zones_count"] = len(self.zone_engine.get_camera_zones(cam_id))
            status_val = diag.get("status")
            if status_val == "online":
                online_count += 1
            elif status_val == "degraded":
                degraded_count += 1
            elif status_val == "offline":
                offline_count += 1
            elif status_val == "error":
                error_count += 1
            worker_statuses.append(diag)

        model_info = self.yolo_engine.get_model_info()

        return {
            "status": "healthy" if self._running else "stopped",
            "uptime_seconds": round(now - self.start_time, 1),
            "active_camera_count": len(self._workers),
            "online_cameras": online_count,
            "degraded_cameras": degraded_count,
            "offline_cameras": offline_count,
            "error_cameras": error_count,
            "detection_mode": settings.detection_mode,
            "model_info": model_info,
            "pipeline_version": settings.pipeline_version,
            "workers": worker_statuses,
        }

