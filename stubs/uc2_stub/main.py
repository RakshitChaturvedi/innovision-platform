"""
UC2 Fire & Smoke Detection — Platform Integration Worker.

Integrates the real UC2 Fire & Smoke Detection pipeline with the Innovision Platform:
- Consumes FrameEvents from Redis Stream frames:{TEST_CAMERA_ID}
- Runs the 6-stage detection pipeline (YOLOv8 + Deterministic HSV + Texture + Temporal + False Alarm Suppression + Confidence Fusion)
- Generates canonical platform AlertEvents with SourceUC.UC2
- Publishes AlertEvents to alerts:live using the platform AlertPublisher
- Preserves mock scenarios for fallback / standalone stub testing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Any, Dict, Optional

import redis.asyncio as aioredis

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, FrameProvider, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("innovision.uc2_integration")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
TEST_CAMERA_ID = UUID(os.environ.get("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000002"))
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDS", "15"))
USE_MOCK_STUB = os.environ.get("USE_MOCK_STUB", "false").lower() in ("true", "1")
FALLBACK_TO_MOCK = os.environ.get("FALLBACK_TO_MOCK", "false").lower() in ("true", "1")
ALERT_COOLDOWN_S = float(os.environ.get("UC2_ALERT_COOLDOWN_S", "30.0"))

UC2_SCENARIOS = [
    {
        "alert_type": "fire_detected",
        "severity": AlertSeverity.CRITICAL,
        "title": "[STUB] fire detected — warehouse B",
        "description": "[STUB] UC2 stub: fire detected in Warehouse B with 94% confidence.",
        "metadata": {
            "confidence": 0.94,
            "zone": "Warehouse B",
            "flame_area_px": 2400,
        },
    },
    {
        "alert_type": "smoke_detected",
        "severity": AlertSeverity.HIGH,
        "title": "[STUB] Smoke Detected — Server Room",
        "description": "[STUB] UC2 stub: smoke detected in server room. Early warning.",
        "metadata": {
            "confidence": 0.87,
            "zone": "Server Room",
            "smoke_density": "medium",
        },
    },
]


async def run_mock_loop(publisher: AlertPublisher):
    """Fallback / Mock Scenario Generator preserving original stub behavior."""
    logger.info("Running UC2 in mock scenario mode...")
    i = 0
    while True:
        s = UC2_SCENARIOS[i % len(UC2_SCENARIOS)]
        i += 1
        alert = AlertEvent(
            camera_id=TEST_CAMERA_ID,
            timestamp=datetime.now(timezone.utc),
            severity=s["severity"],
            alert_type=s["alert_type"],
            title=s["title"],
            description=s["description"],
            source_event_id=uuid4(),
            source_uc=SourceUC.UC2,
            metadata=s["metadata"],
        )
        await publisher.publish(alert)
        await asyncio.sleep(ALERT_INTERVAL)


async def run_real_detection_loop(redis_client: aioredis.Redis, publisher: AlertPublisher):
    """
    Real UC2 Fire & Smoke Detection pipeline loop.
    Consumes live FrameEvents from Redis, processes frames through the 6-stage detector,
    and publishes verified AlertEvents to alerts:live.
    """
    from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline
    from services.uc2_fire_smoke.src.redis.frame_consumer import RedisFrameConsumer

    logger.info(f"Initializing Real UC2 Detection Pipeline for camera {TEST_CAMERA_ID}...")
    pipeline = DetectionPipeline()
    consumer = RedisFrameConsumer(
        redis_client=redis_client,
        camera_id=TEST_CAMERA_ID,
    )

    prev_frame = None
    last_alert_time: Dict[str, float] = {}
    last_frame_time = time.time()
    mock_idx = 0

    logger.info(f"UC2 real detection worker listening on stream frames:{TEST_CAMERA_ID}")

    while True:
        try:
            frames_processed = 0
            async for msg_id, frame_event, frame_img in consumer.read_frames(batch_size=5, block_ms=2000):
                frames_processed += 1
                last_frame_time = time.time()

                if frame_img is None:
                    await consumer.ack(msg_id)
                    continue

                # Run 6-stage detection pipeline
                result = pipeline.process_frame(
                    camera_id=TEST_CAMERA_ID,
                    frame_seq=frame_event.frame_seq,
                    frame_bgr=frame_img,
                    prev_frame_bgr=prev_frame,
                )
                prev_frame = frame_img.copy()

                # Process confirmed detections
                if result.has_detections:
                    now = time.time()
                    for det in result.confirmed_detections:
                        cooldown_key = f"{det.detection_type}:{det.zone.zone_id}"
                        if (now - last_alert_time.get(cooldown_key, 0.0)) < ALERT_COOLDOWN_S:
                            continue
                        last_alert_time[cooldown_key] = now

                        alert_uuid = uuid4()
                        title = f"{det.detection_type.capitalize()} Detected in {det.zone.zone_name}"
                        description = (
                            f"{det.detection_type.capitalize()} detected with confidence "
                            f"{det.final_confidence:.2f} at Camera {TEST_CAMERA_ID}. "
                            f"Verification score: {det.verification_score:.2f}."
                        )

                        metadata: Dict[str, Any] = {
                            "confidence": det.final_confidence,
                            "fire_confidence": det.yolo_confidence if det.detection_type == "fire" else 0.0,
                            "smoke_confidence": det.yolo_confidence if det.detection_type == "smoke" else 0.0,
                            "verification_score": det.verification_score,
                            "zone_id": det.zone.zone_id,
                            "zone_name": det.zone.zone_name,
                            "bounding_boxes": [det.bbox],
                            "latency_ms": round(result.total_pipeline_latency_ms, 2),
                            "verification_details": det.verification_details,
                            "frame_seq": result.frame_seq,
                        }

                        alert_event = AlertEvent(
                            alert_id=alert_uuid,
                            camera_id=TEST_CAMERA_ID,
                            severity=det.severity,
                            alert_type=f"{det.detection_type}_detected",
                            title=title,
                            description=description,
                            source_event_id=frame_event.event_id,
                            timestamp=datetime.now(timezone.utc),
                            status=AlertStatus.PENDING,
                            source_uc=SourceUC.UC2,
                            frame_reference=frame_event.frame_reference,
                            frame_provider=frame_event.frame_provider,
                            metadata=metadata,
                        )

                        await publisher.publish(alert_event)
                        logger.info(
                            f"Published REAL {det.detection_type.upper()} Alert {alert_uuid} "
                            f"(severity={det.severity.value}, conf={det.final_confidence:.2f})"
                        )

                await consumer.ack(msg_id)

            # If no frames arrived in this batch interval
            if frames_processed == 0:
                elapsed = time.time() - last_frame_time
                if FALLBACK_TO_MOCK and elapsed >= ALERT_INTERVAL:
                    # Emit one mock alert while waiting for frames if configured
                    s = UC2_SCENARIOS[mock_idx % len(UC2_SCENARIOS)]
                    mock_idx += 1
                    alert = AlertEvent(
                        camera_id=TEST_CAMERA_ID,
                        timestamp=datetime.now(timezone.utc),
                        severity=s["severity"],
                        alert_type=s["alert_type"],
                        title=s["title"],
                        description=s["description"],
                        source_event_id=uuid4(),
                        source_uc=SourceUC.UC2,
                        metadata=s["metadata"],
                    )
                    await publisher.publish(alert)
                    last_frame_time = time.time()
                await asyncio.sleep(0.5)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"Error in UC2 real detection loop: {exc}", exc_info=True)
            await asyncio.sleep(2.0)


async def main():
    logger.info(f"Starting UC2 Fire & Smoke Integration (Redis={REDIS_HOST}:{REDIS_PORT}, Camera={TEST_CAMERA_ID})...")
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    publisher = AlertPublisher(redis_client)

    if USE_MOCK_STUB:
        await run_mock_loop(publisher)
    else:
        try:
            await run_real_detection_loop(redis_client, publisher)
        except Exception as exc:
            logger.error(f"Failed to run real detection loop ({exc}), falling back to mock loop: {exc}")
            await run_mock_loop(publisher)


if __name__ == "__main__":
    asyncio.run(main())