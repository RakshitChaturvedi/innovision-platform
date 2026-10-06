from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from services.ingestion.src.frame_cache import FrameCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stream", tags=["streaming"])


async def _latest_stream_id(
    redis_client: aioredis.Redis,
    stream_key: str,
) -> str | None:
    messages = await redis_client.xrevrange(
        stream_key,
        max="+",
        min="-",
        count=1,
    )

    if not messages:
        return None

    message_id = messages[0][0]

    if isinstance(message_id, bytes):
        message_id = message_id.decode()

    return message_id


async def _frame_stream(
    redis_client: aioredis.Redis,
    camera_id: str,
) -> AsyncGenerator[bytes, None]:
    stream_key = f"frames:{camera_id}"

    # 1. Immediately yield the most recent published frame if available
    latest_messages = await redis_client.xrevrange(
        stream_key,
        max="+",
        min="-",
        count=1,
    )
    last_id = "0-0"
    if latest_messages:
        msg_id, fields = latest_messages[0]
        if isinstance(msg_id, bytes):
            msg_id = msg_id.decode()
        last_id = msg_id

        payload = fields.get(b"data") or fields.get("data")
        if payload:
            if isinstance(payload, bytes):
                payload = payload.decode()
            try:
                event = json.loads(payload)
                frame_reference = event.get("frame_reference")
                if frame_reference:
                    frame_bytes = await redis_client.get(frame_reference)
                    if frame_bytes:
                        yield (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n\r\n"
                            + frame_bytes
                            + b"\r\n"
                        )
            except Exception:
                pass

    # 2. Stream subsequent frames as they arrive
    while True:
        try:
            messages = await redis_client.xread(
                {stream_key: last_id},
                count=1,
                block=1000,
            )

            if not messages:
                await asyncio.sleep(0.01)
                continue

            for _, entries in messages:
                for message_id, fields in entries:
                    if isinstance(message_id, bytes):
                        message_id = message_id.decode()

                    payload = fields.get(b"data") or fields.get("data")

                    if payload is None:
                        last_id = message_id
                        continue

                    if isinstance(payload, bytes):
                        payload = payload.decode()

                    try:
                        event = json.loads(payload)
                    except Exception:
                        last_id = message_id
                        continue

                    frame_reference = event.get("frame_reference")

                    if not frame_reference:
                        last_id = message_id
                        continue

                    # frame_reference is currently the Redis cache key.
                    frame_bytes = await redis_client.get(frame_reference)

                    if frame_bytes is None:
                        logger.debug(
                            "stream_frame_cache_miss camera_id=%s reference=%s",
                            camera_id,
                            frame_reference,
                        )
                        last_id = message_id
                        continue

                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + frame_bytes
                        + b"\r\n"
                    )

                    last_id = message_id

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "camera_stream_failed camera_id=%s",
                camera_id,
            )
            await asyncio.sleep(1)


@router.get("/{camera_id}")
async def stream_camera(
    camera_id: str,
):
    # Redis is initialized by the ingestion application's lifespan.
    from services.ingestion.main import redis_client

    if redis_client is None:
        raise HTTPException(
            status_code=503,
            detail="Ingestion service is not ready",
        )

    stream_key = f"frames:{camera_id}"

    if not await redis_client.exists(stream_key):
        raise HTTPException(
            status_code=404,
            detail="Camera stream not available",
        )

    return StreamingResponse(
        _frame_stream(
            redis_client,
            camera_id,
        ),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        },
    )