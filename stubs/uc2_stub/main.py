import asyncio, logging, os, sys
import redis.asyncio as aioredis

from datetime import datetime, timezone
from uuid import uuid4, UUID

sys.path.insert(0, "/app")
from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

logging.basicConfig(level=logging.INFO, format="%s(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
TEST_CAMERA_ID = UUID(os.environ.get("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000002"))
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDS", "15"))

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
        }
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
        }
    },
]

async def main():
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    publisher = AlertPublisher(redis_client)
    i = 0
    while True:
        s = UC2_SCENARIOS[i%len(UC2_SCENARIOS)]
        i+=1
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

if __name__=="__main__":
    asyncio.run(main())