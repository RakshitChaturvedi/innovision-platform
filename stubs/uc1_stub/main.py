import asyncio
import logging
import os
import random
import sys
import redis.asyncio as aioredis

from datetime import datetime, timezone
from uuid import uuid4, UUID

sys.path.insert(0, "/app")
from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, AlertStatus, SourceUC
from shared.platform_client.alert_publisher import AlertPublisher

logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6579"))

TEST_CAMERA_ID = UUID(os.environ.get("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000001"))
ALERT_INTERVAL = int(os.environ.get("ALERT_INTERVAL_SECONDs", "10"))

UC1_ALERT_SCENARIOS = [
    {
        "alert_type": "intruder",
        "severity": AlertSeverity.CRITICAL,
        "title": "[STUB] intruder detection -- server room",
        "description": "[STUB] UC1 stub: unknown individual entered restricted zone 'Server Room'.",
        "metadata": {
            "zone_id": "test-zone-server-room",
            "zone_name": "Server Room",
            "track_id": 42,
            "classification_reason": "unknown_in_restricted"
        }
    },
    {
        "alert_type": "restricted_entry",
        "severity": AlertSeverity.HIGH,
        "title": "[STUB] restricted entry -- main gate",
        "description": "[STUB] UC1 stub: blocklisted individual detected at main gate.",
        "metadata": {
            "track_id": 17,
            "similarity_score": 0.91,
            "match_type": "enrolled_match",
            "blocklist_reason": "Former employee — access revoked",
        }
    },
    {
        "alert_type": "headcount_breach",
        "severity": AlertSeverity.HIGH,
        "title": "[STUB] headcount threshold exceeded — lobby",
        "description": "[STUB] UC1 stub: lobby zone has 45 persons (threshold: 40).",
        "metadata": {
            "zone_id": "test-zone-lobby",
            "zone_name": "Lobby",
            "count": 45,
            "threshold": 40,
        }
    },
    {
        "alert_type": "crowd_density",
        "severity": AlertSeverity.MEDIUM,
        "title": "[STUB] high crowd density — atrium",
        "description": "[STUB] UC1 stub: atrium crowd density reached HIGH level.",
        "metadata": {
            "zone_id": "test-zone-atrium",
            "zone_name": "Atrium",
            "density_level": "high",
            "raw_count": 120,
        }
    }
]

async def main():
    logger.info("uc1_stub_starting camera_id=%s interval=%ds", TEST_CAMERA_ID, ALERT_INTERVAL)

    redis_client  = await aioredis.from_url(f"redis://{REDIS_HOST}:{REDIS_PORT}")
    publisher = AlertPublisher(redis_client)
    scenario_index=0

    while True:
        scenario = UC1_ALERT_SCENARIOS[scenario_index%len(UC1_ALERT_SCENARIOS)]
        scenario_index +=1

        alert = AlertEvent(
            camera_id=TEST_CAMERA_ID,
            timestamp=datetime.now(timezone.utc),
            severity=scenario["severity"],
            alert_type=scenario["alert_type"],
            title=scenario["title"],
            description=scenario["description"],
            source_event_id=uuid4(),
            source_uc=SourceUC.UC1,
            frame_reference=None,
            frame_provider=None,
            metadata=scenario["metadata"],
        )
        success = await publisher.publish(alert)
        if success:
            logger.info("stub_alert_published type=%s severity=%s", alert.alert_type, alert.severity.value)
        else:
            logger.error("stub_alert_publish_failed")

        await asyncio.sleep(ALERT_INTERVAL)

if __name__=="__main__":
    asyncio.run(main())
    