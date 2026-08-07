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
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDS", "8"))

UC4_SCENARIOS = [
    {
        "alert_type": "speed_violation",
        "severity": AlertSeverity.HIGH,
        "title": "[STUB] speed violation — gate b",
        "description": "[STUB] UC4 stub: vehicle MH12AB1234 detected at 45 km/h (limit: 20 km/h).",
        "metadata": {
            "plate_number": "MH12AB1234",
            "speed_kmph": 45,
            "speed_limit_kmph": 20,
            "gate": "Gate B",
            "vehicle_type": "car",
        }
    },
    {
        "alert_type": "unauthorized_vehicle",
        "severity": AlertSeverity.CRITICAL,
        "title": "[STUB] unauthorized vehicle entry — restricted lot",
        "description": "[STUB] UC4 stub: unregistered vehicle entered restricted parking lot.",
        "metadata": {
            "plate_number": "KA01XY9999",
            "gate": "Gate C",
            "vehicle_type": "truck",
            "registered": False,
        }
    },
]

async def main():
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    publisher = AlertPublisher(redis_client)
    i=0
    while True:
        s= UC4_SCENARIOS[i%len(UC4_SCENARIOS)]
        i+=1
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
        await publisher.publish(alert)
        await asyncio.sleep(ALERT_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())