"""
UC3 Pipeline Manager — Discovers active cameras and coordinates workers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional
from uuid import UUID

import httpx
import redis.asyncio as aioredis
from redis.exceptions import ResponseError

from shared.platform_client.alert_publisher import AlertPublisher

from services.uc3_ppe_detection.src import config
from services.uc3_ppe_detection.src.storage.minio_client import MinIOClient
from services.uc3_ppe_detection.src.workers.camera_worker import CameraWorker

logger = logging.getLogger(__name__)


class PipelineManager:
    def __init__(
        self,
        redis_client: Optional[Any] = None,
        minio_client: Optional[MinIOClient] = None,
    ) -> None:
        self.redis = redis_client
        self.minio = minio_client or MinIOClient()
        self.workers: Dict[UUID, CameraWorker] = {}
        self.running = False
        self._loop_task: Optional[asyncio.Task] = None

    async def discover_cameras() -> List[dict]:
        cameras = []
        try:
            async with httpx.AsyncClient(timeout=5.0) as http:
                resp = await http.get(f"{config.CAMERA_REGISTRY_URL}/cameras")
                if resp.status_code == 200:
                    data = resp.json()
                    cams = data.get("cameras", data) if isinstance(data, dict) else data
                    for c in cams:
                        uc = str(c.get("use_case", "")).lower()
                        if "uc3" in uc or "ppe" in uc or uc == "all" or not uc:
                            cameras.append({
                                "camera_id": UUID(str(c["id"] if "id" in c else c["camera_id"])),
                                "name": c.get("name", "UC3 Camera"),
                            })
        except Exception as exc:
            logger.warning("Camera registry discovery failed: %s; using test camera ID", exc)

        if not cameras:
            cameras.append({
                "camera_id": UUID(config.TEST_CAMERA_ID),
                "name": "UC3 Test Camera",
            })
        return cameras

    async def start(self) -> None:
        if self.running:
            return
        self.running = True

        if not self.redis:
            self.redis = aioredis.from_url(config.REDIS_URL, decode_responses=False)

        publisher = AlertPublisher(self.redis)

        cameras = await self.discover_cameras()
        for c in cameras:
            cid = c["camera_id"]
            name = c["name"]
            worker = CameraWorker(
                camera_id=cid,
                camera_name=name,
                redis_client=self.redis,
                publisher=publisher,
                minio_client=self.minio,
            )
            self.workers[cid] = worker

        self._loop_task = asyncio.create_task(self._run_loop(), name="uc3-pipeline-loop")
        logger.info("UC3 Pipeline Manager started with %d workers", len(self.workers))

    async def _run_loop(self) -> None:
        stream_names = [f"frames:{cid}" for cid in self.workers.keys()]

        for s_name in stream_names:
            try:
                await self.redis.xgroup_create(
                    name=s_name,
                    groupname=config.REDIS_CONSUMER_GROUP,
                    id="$",
                    mkstream=True,
                )
            except ResponseError as exc:
                if "BUSYGROUP" not in str(exc):
                    logger.warning("xgroup_create_warning stream=%s error=%s", s_name, exc)

        while self.running:
            try:
                stream_dict = {s_name: ">" for s_name in stream_names}
                response = await self.redis.xreadgroup(
                    groupname=config.REDIS_CONSUMER_GROUP,
                    consumername=config.REDIS_CONSUMER_NAME,
                    streams=stream_dict,
                    count=5,
                    block=1000,
                )

                if not response:
                    await asyncio.sleep(0.01)
                    continue

                for stream_b, messages in response:
                    if not messages:
                        continue
                    stream_name = stream_b.decode("utf-8") if isinstance(stream_b, bytes) else str(stream_b)
                    cid_str = stream_name.replace("frames:", "")
                    try:
                        cid = UUID(cid_str)
                    except ValueError:
                        continue

                    worker = self.workers.get(cid)
                    if not worker:
                        continue

                    for msg_id, fields in messages:
                        data_dict = {}
                        for k, v in fields.items():
                            key_str = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                            val_str = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                            data_dict[key_str] = val_str

                        if "data" in data_dict and data_dict["data"].startswith("{"):
                            try:
                                payload = json.loads(data_dict["data"])
                                data_dict.update(payload)
                            except Exception:
                                pass

                        await worker.process_frame(data_dict, msg_id, stream_name)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("UC3 Pipeline loop error: %s", exc)
                await asyncio.sleep(1.0)

    async def stop(self) -> None:
        self.running = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        logger.info("UC3 Pipeline Manager stopped")
