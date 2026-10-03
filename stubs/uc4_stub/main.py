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
    "TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000004"
))
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDS", "30"))

UC4_SCENARIOS = [
    {
        "alert_type": "speed_violation",
        "severity": AlertSeverity.HIGH,
        "title": "[DEMO] Vehicle Speed Violation — Gate B",
        "description": "[DEMO ONLY] Simulated vehicle MH12AB1234 detected at 45 km/h (limit: 20 km/h). Demo mode for UC4 presentation.",
        "metadata": {
            "plate_number": "MH12AB1234",
            "speed_kmph": 45,
            "speed_limit_kmph": 20,
            "gate": "Gate B",
            "vehicle_type": "car",
            "is_demo": True,
            "demo_notice": "UC4 Vehicle / ANPR is currently running in controlled DEMO simulation mode.",
        }
    },
    {
        "alert_type": "unauthorized_vehicle",
        "severity": AlertSeverity.CRITICAL,
        "title": "[DEMO] Unauthorized Vehicle Entry — Restricted Lot",
        "description": "[DEMO ONLY] Simulated unregistered truck entered restricted perimeter. Demo mode for UC4 presentation.",
        "metadata": {
            "plate_number": "KA01XY9999",
            "gate": "Gate C",
            "vehicle_type": "truck",
            "registered": False,
            "is_demo": True,
            "demo_notice": "UC4 Vehicle / ANPR is currently running in controlled DEMO simulation mode.",
        }
    },
]

async def main():
    logger.info("Initializing UC4 Worker (DEMO ONLY mode - isolated simulation)...")
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    publisher = AlertPublisher(redis_client)
    logger.info("UC4 DEMO worker connected to Redis. Emitting demo events every %s seconds.", ALERT_INTERVAL)
    i = 0
    while True:
        s = UC4_SCENARIOS[i % len(UC4_SCENARIOS)]
        i += 1
        alert = AlertEvent(
            camera_id=TEST_CAMERA_ID,
            timestamp=datetime.now(timezone.utc),
            severity=s["severity"],
            alert_type=s["alert_type"],
            title=s["title"],
            description=s["description"],
            source_event_id=uuid4(),
            source_uc=SourceUC.UC4,
            metadata=s["metadata"],
        )
        try:
            await publisher.publish(alert)
            logger.info("UC4 DEMO event published: %s (%s)", alert.title, alert.severity.value)
        except Exception as e:
            logger.warning("UC4 DEMO publisher warning: %s", e)
        await asyncio.sleep(ALERT_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())