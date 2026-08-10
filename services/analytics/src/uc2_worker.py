"""
UC2 Analytics Worker — Fire & Smoke Detection.

Consumes FrameEvents, runs simulated fire/smoke inference, and emits
alerts via the shared AlertPublisher.
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

UC2_SCENARIOS = [
    {
        "alert_type": "fire_detected",
        "severity": AlertSeverity.CRITICAL,
        "title": "Fire detected — warehouse zone B",
        "description": "Visible flames identified in warehouse zone B. Immediate response required.",
        "metadata": {"zone_id": "zone-warehouse-b", "confidence": 0.94, "detection_method": "yolov8_fire"},
    },
    {
        "alert_type": "smoke_detected",
        "severity": AlertSeverity.HIGH,
        "title": "Smoke detected — parking level 2",
        "description": "Smoke plume detected in parking level 2 via visual analysis.",
        "metadata": {"zone_id": "zone-parking-l2", "confidence": 0.87, "detection_method": "smoke_classifier"},
    },
    {
        "alert_type": "thermal_anomaly",
        "severity": AlertSeverity.MEDIUM,
        "title": "Thermal anomaly — server room HVAC",
        "description": "Abnormal heat signature detected near server room HVAC outlet.",
        "metadata": {"zone_id": "zone-server-hvac", "temp_delta_c": 15.2},
    },
]


class UC2Worker(BaseConsumer):
    """UC2 Fire & Smoke Detection analytics worker."""

    source_uc = SourceUC.UC2

    def __init__(self) -> None:
        super().__init__()
        self._frame_counter = 0
        self._alert_interval = int(
            __import__("os").environ.get("UC2_ALERT_INTERVAL_FRAMES", "60")
        )

    async def process_frame(self, event: FrameEvent, frame: np.ndarray) -> None:
        self._frame_counter += 1
        if self._frame_counter % self._alert_interval != 0:
            return

        scenario = random.choice(UC2_SCENARIOS)
        alert = AlertEvent(
            camera_id=event.camera_id,
            timestamp=datetime.now(timezone.utc),
            severity=scenario["severity"],
            alert_type=scenario["alert_type"],
            title=scenario["title"],
            description=scenario["description"],
            source_event_id=event.event_id,
            source_uc=SourceUC.UC2,
            metadata=scenario["metadata"],
        )

        import cv2
        _, snap_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        success = await self.emit_alert(alert, snapshot_bytes=snap_buf.tobytes())
        if success:
            logger.info("uc2_alert_emitted type=%s camera=%s", alert.alert_type, event.camera_id)
