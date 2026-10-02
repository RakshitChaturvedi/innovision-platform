import asyncio, logging, os, sys
import redis.asyncio as aioredis

from datetime import datetime, timezone
from uuid import uuid4, UUID

sys.path.insert(0, "/app")
from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
TEST_CAMERA_ID = UUID(os.environ.get(
    "TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000005"
))
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDS", "15"))

UC5_SCENARIOS = [
    {
        "alert_type": "hazardous_spill",
        "severity": AlertSeverity.CRITICAL,
        "title": "[STUB] chemical spill detected — sector c",
        "description": "[STUB] UC5 stub: liquid chemical spill detected in Sector C chemical handling bay.",
        "metadata": {
            "zone": "Sector C",
            "spill_area_sqm": 4.5,
            "substance_classification": "hazardous_corrosive",
            "containment_required": True,
        }
    },
    {
        "alert_type": "zone_intrusion",
        "severity": AlertSeverity.HIGH,
        "title": "[STUB] unauthorized perimeter intrusion — high voltage bay",
        "description": "[STUB] UC5 stub: personnel entered restricted high-voltage perimeter without clearance.",
        "metadata": {
            "zone": "Substation Perimeter",
            "clearance_level_required": "level_3",
            "intruder_count": 1,
        }
    },
]

async def main():
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    publisher = AlertPublisher(redis_client)
    i = 0
    logger.info(f"UC5 Stub running for camera {TEST_CAMERA_ID}, interval {ALERT_INTERVAL}s")
    while True:
        s = UC5_SCENARIOS[i % len(UC5_SCENARIOS)]
        i += 1
        alert = AlertEvent(
            camera_id=TEST_CAMERA_ID,
            timestamp=datetime.now(timezone.utc),
            severity=s["severity"],
            alert_type=s["alert_type"],
            source_uc=SourceUC.UC5,
            title=s["title"],
            description=s["description"],
            metadata=s["metadata"],
        )
        try:
            msg_id = await publisher.publish(alert)
            logger.info(f"[UC5 STUB] Published alert: {alert.title} (msg_id: {msg_id})")
        except Exception as e:
            logger.error(f"[UC5 STUB] Failed to publish alert: {e}")
        await asyncio.sleep(ALERT_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())
