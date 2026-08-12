from __future__ import annotations

import asyncio, logging
from typing import Any
import redis.asyncio as aioredis
import numpy as np

from services.ingestion.src.config import settings
from services.ingestion.src.frame_cache import FrameCache
from services.ingestion.src.frame_sampler import FrameSampler
from services.ingestion.src.frame_store import FrameStore
from services.ingestion.src.heartbeat import heartbeat_loop
from services.ingestion.src.jpeg_encoder import JpegEncoder
from services.ingestion.src.publisher import FramePublisher
from services.ingestion.src.stream_decoder import StreamDecoder

logger = logging.getLogger(__name__)

class CameraIngestionTask:
    def __init__(
            self,
            camera_id: str,
            rtsp_url: str,
            fps: float,
            redis_client: aioredis.Redis,
            publisher: FramePublisher,
            frame_cache: FrameCache,
            frame_store: FrameStore
    ) -> None:
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.fps = fps
        self._redis = redis_client
        self._publisher = publisher
        self._frame_cache = frame_cache
        self._frame_store = frame_store
        self._stopped = False
        self._reconnect_attempt = 0
        self._frame_seq = 0
        self._decoder: StreamDecoder | None = None

    async def run(self) -> None:
        heartbeat_task = asyncio.create_task(
            heartbeat_loop(
                redis_client=self._redis,
                camera_id=self.camera_id,
                interval_s=settings.heartbeat_interval_s
            )
        )
        try:
            while not self._stopped:
                try:
                    await self._ingest_once()
                    self._reconnect_attempt = 0
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error("camera_ingestion_error camera_id=%s error=%s", self.camera_id, e)
                if self._stopped:
                    break
                delay = self._backoff_delay()

                logger.warning("camera_reconnecting camera_id=%s attempt=%d delay=%.1fs",
                               self.camera_id, self._reconnect_attempt+1, delay)
                await asyncio.sleep(delay)
                self._reconnect_attempt += 1
        finally:
            heartbeat_task.cancel()

            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            await self._stop_decoder()
            logger.info("camera_task_stopped camera_id=%s", self.camera_id)

    async def _ingest_once(self) -> None:
        # connect to cam and process frames

        decoder = StreamDecoder(source=self.rtsp_url)
        encoder= JpegEncoder(quality=settings.jpeg_quality)
        self._decoder = decoder
        sampler = FrameSampler(target_fps=self.fps)

        try:
            await decoder.start()
            logger.info("camera_stream_connected camera_id=%s fps=%.1f",self.camera_id, self.fps)

            while not self._stopped:
                try:
                    frame = await decoder.read_frame()
                except Exception as e:
                    raise ConnectionError(f"Stream dropped for camera {self.camera_id}") from e

                if not sampler.should_sample():
                    continue

                self._frame_seq = sampler.frame_seq
                await self._process_frame(frame=frame,frame_seq=self._frame_seq, encoder=JpegEncoder(quality=settings.jpeg_quality))
        finally:
            await decoder.stop()
            self._decoder = None

    async def _process_frame(self, frame: np.ndarray, frame_seq: int, encoder=JpegEncoder) -> None:
        # encode, cache, persist and publish 1 sampled frame

        # 1. Encodeg
        try:
            jpeg_bytes = encoder.encode(frame)
        except Exception as e:
            logger.error("frame_encode_failed camera_id=%s frame_seq=%d error=%s", 
                         self.camera_id, frame_seq, e)
            return
        object_key = encoder.object_key(camera_id=self.camera_id, frame_seq=frame_seq)

        # 2. Redis Cache
        try:
            cache_key = await self._frame_cache.put(
                camera_id=self.camera_id,
                frame_seq=frame_seq,
                jpeg_bytes=jpeg_bytes
            )
        except Exception as e:
            logger.error(
                "frame_cache_failed camera_id=%s frame_seq=%d error=%s",
                self.camera_id, frame_seq, e)
            return

        # 3. minio
        try:
            await self._frame_store.upload(object_key, jpeg_bytes)
        except Exception as e:
            logger.error("frame_store_failed camera_id=%s frame_seq=%d error=%s", 
                         self.camera_id, frame_seq, e)
            return

        # 4. publish frame event
        try:
            await self._publisher.publish(
                camera_id=self.camera_id, frame_seq=frame_seq, frame_reference=cache_key,
                frame_shape=(frame.shape[0], frame.shape[1])
            )
        except Exception as e:
            logger.error("frame_publish_failed camera_id=%s frame_seq=%s error=%s",
                         self.camera_id, frame_seq, e)

    def _backoff_delay(self) -> float:
        # calc exponential reconnect delay, base=1s, max=30s
        delay = settings.reconnect_base_delay_s*(2**self._reconnect_attempt)
        return min(delay, settings.reconnect_max_delay_s)

    async def _stop_decoder(self) -> None:
        if self._decoder is None:
            return
        try:
            await self._decoder.stop()
        except Exception as e:
            logger.error("decoder_stop_failed camera_id=%s error=%s", self.camera_id, e)
        self._decoder = None

    def stop(self) -> None:
        # req graceful shutdown
        self._stopped = True
        logger.info("camera_task_stop_requested camera_id=%s", self.camera_id)