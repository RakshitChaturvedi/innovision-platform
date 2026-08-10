"""
UC3 Analytics Worker — Safety Compliance (PPE Detection).

Consumes FrameEvents, runs simulated PPE/safety-gear inference, and
emits alerts via the shared AlertPublisher.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

import numpy as np

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, SourceUC
from shared.contracts.frame_event import FrameEvent
from services.analytics.src.base_consumer import BaseConsumer

logger = logging.getLogger(__name__)

UC3_SCENARIOS = [
    {
        "alert_type": "no_helmet",
        "severity": AlertSeverity.HIGH,
        "title": "Missing helmet — construction zone A",
        "description": "Worker detected without hard hat in mandatory helmet area.",
        "metadata": {"zone_id": "zone-construction-a", "confidence": 0.92, "ppe_type": "helmet"},
    },
    {
        "alert_type": "no_vest",
        "severity": AlertSeverity.MEDIUM,
        "title": "Missing high-vis vest — loading dock",
        "description": "Individual without high-visibility vest in loading dock area.",
        "metadata": {"zone_id": "zone-loading-dock", "confidence": 0.88, "ppe_type": "vest"},
    },
    {
        "alert_type": "restricted_zone_entry",
        "severity": AlertSeverity.HIGH,
        "title": "Unauthorised entry — hazardous materials area",
        "description": "Person without required safety gear entered hazardous materials zone.",
        "metadata": {"zone_id": "zone-hazmat", "required_ppe": ["helmet", "goggles", "gloves"]},
    },
]


class UC3Worker(BaseConsumer):
    """UC3 Safety Compliance / PPE Detection analytics worker."""

    source_uc = SourceUC.UC3

    def __init__(self) -> None:
        super().__init__()
        self._frame_counter = 0
        self._alert_interval = int(
            __import__("os").environ.get("UC3_ALERT_INTERVAL_FRAMES", "55")
        )

    async def process_frame(self, event: FrameEvent, frame: np.ndarray) -> None:
        self._frame_counter += 1
        if self._frame_counter % self._alert_interval != 0:
            return

        scenario = random.choice(UC3_SCENARIOS)
        alert = AlertEvent(
            camera_id=event.camera_id,
            timestamp=datetime.now(timezone.utc),
            severity=scenario["severity"],
            alert_type=scenario["alert_type"],
            title=scenario["title"],
            description=scenario["description"],
            source_event_id=event.event_id,
            source_uc=SourceUC.UC3,
            metadata=scenario["metadata"],
        )

        import cv2
        _, snap_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        success = await self.emit_alert(alert, snapshot_bytes=snap_buf.tobytes())
        if success:
            logger.info("uc3_alert_emitted type=%s camera=%s", alert.alert_type, event.camera_id)
