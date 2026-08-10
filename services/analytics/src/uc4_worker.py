"""
UC4 Analytics Worker — Vehicle & Traffic Monitoring.

Consumes FrameEvents, runs simulated vehicle/traffic inference, and
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

UC4_SCENARIOS = [
    {
        "alert_type": "wrong_way_vehicle",
        "severity": AlertSeverity.CRITICAL,
        "title": "Wrong-way vehicle — exit ramp",
        "description": "Vehicle travelling in the wrong direction on exit ramp.",
        "metadata": {"zone_id": "zone-exit-ramp", "confidence": 0.96, "vehicle_type": "sedan"},
    },
    {
        "alert_type": "illegal_parking",
        "severity": AlertSeverity.MEDIUM,
        "title": "Illegal parking — fire lane",
        "description": "Vehicle parked in fire lane for more than 2 minutes.",
        "metadata": {"zone_id": "zone-fire-lane", "dwell_time_s": 145, "vehicle_type": "suv"},
    },
    {
        "alert_type": "speed_violation",
        "severity": AlertSeverity.HIGH,
        "title": "Speed violation — campus road",
        "description": "Vehicle exceeding 30 km/h speed limit on campus road.",
        "metadata": {"zone_id": "zone-campus-road", "estimated_speed_kmh": 52, "limit_kmh": 30},
    },
    {
        "alert_type": "vehicle_count_exceeded",
        "severity": AlertSeverity.LOW,
        "title": "Parking lot near capacity — lot C",
        "description": "Parking lot C at 95% capacity (190/200 spots).",
        "metadata": {"zone_id": "zone-lot-c", "occupied": 190, "capacity": 200},
    },
]


class UC4Worker(BaseConsumer):
    """UC4 Vehicle & Traffic Monitoring analytics worker."""

    source_uc = SourceUC.UC4

    def __init__(self) -> None:
        super().__init__()
        self._frame_counter = 0
        self._alert_interval = int(
            __import__("os").environ.get("UC4_ALERT_INTERVAL_FRAMES", "45")
        )

    async def process_frame(self, event: FrameEvent, frame: np.ndarray) -> None:
        self._frame_counter += 1
        if self._frame_counter % self._alert_interval != 0:
            return

        scenario = random.choice(UC4_SCENARIOS)
        alert = AlertEvent(
            camera_id=event.camera_id,
            timestamp=datetime.now(timezone.utc),
            severity=scenario["severity"],
            alert_type=scenario["alert_type"],
            title=scenario["title"],
            description=scenario["description"],
            source_event_id=event.event_id,
            source_uc=SourceUC.UC4,
            metadata=scenario["metadata"],
        )

        import cv2
        _, snap_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        success = await self.emit_alert(alert, snapshot_bytes=snap_buf.tobytes())
        if success:
            logger.info("uc4_alert_emitted type=%s camera=%s", alert.alert_type, event.camera_id)
