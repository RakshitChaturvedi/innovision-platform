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
    "TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000003"
))
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDS", "12"))

UC3_SCENARIOS = [
    {
        "alert_type": "ppe_violation",
        "severity": AlertSeverity.HIGH,
        "title": "[STUB] ppe violation — construction zone a",
        "description": "[STUB] UC3 stub: worker detected without helmet in Construction Zone A.",
        "metadata": {
            "track_id": 7,
            "missing_ppe": ["helmet"],
            "zone": "Construction Zone A",
            "compliance_score": 0.0,
        }
    },
    {
        "alert_type": "ppe_violation",
        "severity": AlertSeverity.MEDIUM,
        "title": "[STUB] ppe partial violation — loading dock",
        "description": "[STUB] UC3 stub: worker missing safety jacket at Loading Dock.",
        "metadata": {
            "track_id": 23,
            "missing_ppe": ["safety_jacket"],
            "zone": "Loading Dock",
            "compliance_score": 0.5,
        }
    },
]

async def main():
    redis_client = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    publisher = AlertPublisher(redis_client)
    i = 0
    while True:
        s = UC3_SCENARIOS[i%len(UC3_SCENARIOS)]
        i+=1
        alert=AlertEvent(
            camera_id=TEST_CAMERA_ID,
            timestamp=datetime.now(timezone.utc),
            severity=s["severity"],
            alert_type=s["alert_type"],
            title=s["title"],
            description=s["description"],
            source_event_id=uuid4(),
            source_uc=SourceUC.UC3,
            metadata=s["metadata"],
        )
        await publisher.publish(alert)
        await asyncio.sleep(ALERT_INTERVAL)

if __name__ == "__main__":
    asyncio.run(main())