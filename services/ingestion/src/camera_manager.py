from __future__ import annotations

import asyncio
import logging
from typing import Any

import redis.asyncio as aioredis

from services.ingestion.src.camera_registry_client import CameraRegistryClient
from services.ingestion.src.camera_task import CameraIngestionTask
from services.ingestion.src.config import settings
from services.ingestion.src.frame_cache import FrameCache
from services.ingestion.src.frame_store import FrameStore
from services.ingestion.src.publisher import FramePublisher

logger = logging.getLogger(__name__)

class CameraManager:
    # orchestrates ingestion for all active cameras.
    def __init__(
        self,
        registry_client: CameraRegistryClient,
        redis_client: aioredis.Redis,
        publisher: FramePublisher,
        frame_cache: FrameCache,
        frame_store: FrameStore,
    ) -> None:
        self._registry_client = registry_client
        self._redis = redis_client
        self._publisher = publisher
        self._frame_cache = frame_cache
        self._frame_store = frame_store

        # camera_id -> CameraIngestionTask
        self._camera_tasks: dict[str, CameraIngestionTask] = {}

        # camera_id -> asyncio.Task running CameraIngestionTask.run()
        self._asyncio_tasks: dict[str, asyncio.Task] = {}
        self._manager_tasks: list[asyncio.Task] = []
        self._stopped = False

    # 1. Startup
    async def start(self) -> None:
        # load active cams and start their ingestion tasks, pub/sub listener and periodic reconciliation.
        
        self._stopped = False
        cameras = await self._registry_client.get_active_cameras()
        for camera in cameras:
            await self._start_camera(camera)

        self._manager_tasks.append(
            asyncio.create_task(self._listen_camera_signals(), name="camera-manager-pubsub")
        )
        self._manager_tasks.append(
            asyncio.create_task(self._periodic_refresh(),name="camera-manager-refresh")
        )

        logger.info("camera_manager_started active_cameras=%d",len(self._camera_tasks))

    # 2. Cam lifecycle
    async def _start_camera(self, camera: dict[str, Any]) -> None:
        # start ingestion for 1 camera
        
        camera_id = str(camera["id"])
        if camera_id in self._camera_tasks:
            logger.debug("camera_already_running camera_id=%s",camera_id)
            return

        rtsp_url = camera.get("rtsp_url")
        if not rtsp_url:
            logger.warning("camera_missing_rtsp_url camera_id=%s",camera_id)
            return

        fps = camera.get("fps") or settings.default_fps
        camera_task = CameraIngestionTask(
            camera_id=camera_id,
            rtsp_url=rtsp_url,
            fps=fps,
            redis_client=self._redis,
            publisher=self._publisher,
            frame_cache=self._frame_cache,
            frame_store=self._frame_store,
        )
        asyncio_task = asyncio.create_task(
            camera_task.run(), name=f"camera-ingestion-{camera_id}"
        )

        self._camera_tasks[camera_id] = camera_task
        self._asyncio_tasks[camera_id] = asyncio_task

        logger.info(
            "camera_ingestion_started camera_id=%s name=%s fps=%.1f",
            camera_id, camera.get("name"), fps
        )

    async def _stop_camera(self, camera_id: str) -> None:
        # stop and remove cam ingestion task
        camera_id = str(camera_id)
        camera_task = self._camera_tasks.pop(camera_id, None)
        asyncio_task = self._asyncio_tasks.pop(camera_id, None)

        if camera_task is None:
            return
        camera_task.stop()

        if asyncio_task is not None:
            asyncio_task.cancel()
            try:
                await asyncio_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("camera_task_shutdown_failed camera_id=%s error=%s",
                             camera_id, e)
        logger.info("camera_ingestion_stopped camera_id=%s", camera_id)

    # 3. Registry pub-sub
    async def _listen_camera_signals(self) -> None:
        # listen cam registry change notifs. (camera:added, camera:updated, camera:removed)

        pubsub = self._redis.pubsub()
        try:
            await pubsub.psubscribe(
                "camera:added:*",
                "camera:removed:*",
                "camera:updated:*"
            )
            logger.info("camera_registry_signal_listener_started")

            async for message in pubsub.listen():
                if self._stopped:
                    break
                if message["type"] != "pmessage":
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel=channel.decode()
                camera_id = channel.rsplit(":", 1)[-1]

                try:
                    if channel.startswith("camera:added:"):
                        await self._handle_camera_added(camera_id)

                    elif channel.startswith("camera:updated:"):
                        await self._handle_camera_updated(camera_id)

                    elif channel.startswith("camera:removed:"):
                        await self._handle_camera_removed(camera_id)
                except Exception as e:
                    logger.error("camera_registry_signal_failed channel=%s camera_id=%s error=%s",
                                 channel, camera_id, e)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("camera_registry_signal_listener_failed error=%s", e)
        finally:
            try:
                await pubsub.punsubscribe(
                    "camera:added:*",
                    "camera:updated:*",
                    "camera:removed:*",
                )
            except Exception:
                pass

            await pubsub.aclose()
            logger.info("camera_registry_signal_listener_stopped")

    async def _handle_camera_added(self, camera_id: str) -> None:
        camera = await self._registry_client.get_camera(camera_id)

        if camera is None:
            logger.warning("camera_added_but_not_found camera_id=%s", camera_id)
            return
        await self._start_camera(camera)

    async def _handle_camera_updated(self, camera_id: str) -> None:
        # restart cam task with latest configs.
        camera = await self._registry_client.get_camera(camera_id)

        if camera is None:
            # cam may have been disabled/deleted.
            await self._stop_camera(camera_id)
            return

        await self._stop_camera(camera_id)
        await self._start_camera(camera)

    async def _handle_camera_removed(self, camera_id: str) -> None:
        await self._stop_camera(camera_id)

    # 4. Periodic Reconciliation
    async def _periodic_refresh(self) -> None:
        # protects against missed redis pub-sub notifs.
        try:
            while not self._stopped:
                await asyncio.sleep(settings.camera_refresh_interval_s)
                if self._stopped:
                    break
                try:
                    cameras = await self._registry_client.get_active_cameras()
                    active_cameras = {str(camera["id"]): camera for camera in cameras}
                    active_ids= set(active_cameras)
                    running_ids = set(self._camera_tasks)

                    # cams that should be running but arent
                    for camera_id in active_ids - running_ids:
                        logger.warning("camera_missing_from_manager camera_id=%s", camera_id)
                        await self._start_camera(active_cameras[camera_id])

                    # cams that are running but no longer active
                    for camera_id in running_ids - active_ids:
                        logger.warning("camera_no_longer_active camera_id=%s", camera_id)
                        await self._stop_camera(camera_id)

                except Exception as e:
                    logger.error("camera_periodic_refresh_failed error=%s", e)
        except asyncio.CancelledError:
            raise

    # 5. shutdown
    async def stop(self) -> None:
        # stop all cam ingestion and manager bg tasks
        if self._stopped:
            return
        self._stopped = True
        logger.info("camera_manager_stopping")

        for task in self._manager_tasks:
            task.cancel()
        for task in self._manager_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error("camera_manager_background_task_failed error=%s", e)
        self._manager_tasks.clear()

        camera_ids = list(self._camera_tasks)
        for camera_id in camera_ids:
            await self._stop_camera(camera_id)
        logger.info("camera_manager_stopped")

    # 6. Introspection
    @property
    def active_camera_ids(self) -> list[str]:
        return list(self._camera_tasks)

    @property
    def active_camera_count(self) -> int:
        return len(self._camera_tasks)


