"""
UC1 Analytics Worker — Intrusion & Access Control.

Consumes FrameEvents from the ingestion pipeline, runs simulated
inference (placeholder for a real CV model), and emits alerts via
the shared AlertPublisher when detection criteria are met.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np

from shared.contracts.alert_event import AlertEvent
from shared.contracts.enums import AlertSeverity, SourceUC
from shared.contracts.frame_event import FrameEvent
from services.analytics.src.base_consumer import BaseConsumer

logger = logging.getLogger(__name__)

# Alert scenarios — mirrors the Phase 1 stub but now triggered by real
# frame processing rather than a blind timer.
UC1_SCENARIOS = [
    {
        "alert_type": "intruder",
        "severity": AlertSeverity.CRITICAL,
        "title": "Intruder detection — server room",
        "description": "Unknown individual entered restricted zone 'Server Room'.",
        "metadata": {
            "zone_id": "zone-server-room",
            "zone_name": "Server Room",
            "classification_reason": "unknown_in_restricted",
        },
    },
    {
        "alert_type": "restricted_entry",
        "severity": AlertSeverity.HIGH,
        "title": "Restricted entry — main gate",
        "description": "Blocklisted individual detected at main gate.",
        "metadata": {
            "match_type": "enrolled_match",
            "similarity_score": 0.91,
            "blocklist_reason": "Former employee — access revoked",
        },
    },
    {
        "alert_type": "headcount_breach",
        "severity": AlertSeverity.HIGH,
        "title": "Headcount threshold exceeded — lobby",
        "description": "Lobby zone has 45 persons (threshold: 40).",
        "metadata": {
            "zone_id": "zone-lobby",
            "zone_name": "Lobby",
            "count": 45,
            "threshold": 40,
        },
    },
    {
        "alert_type": "crowd_density",
        "severity": AlertSeverity.MEDIUM,
        "title": "High crowd density — atrium",
        "description": "Atrium crowd density reached HIGH level.",
        "metadata": {
            "zone_id": "zone-atrium",
            "zone_name": "Atrium",
            "density_level": "high",
            "raw_count": 120,
        },
    },
]


class UC1Worker(BaseConsumer):
    """UC1 Intrusion & Access Control analytics worker."""

    source_uc = SourceUC.UC1

    def __init__(self) -> None:
        super().__init__()
        self._frame_counter = 0
        # Trigger an alert roughly every 50 frames (≈ 5 s at 10 FPS)
        self._alert_interval = int(
            __import__("os").environ.get("UC1_ALERT_INTERVAL_FRAMES", "50")
        )

    async def process_frame(self, event: FrameEvent, frame: np.ndarray) -> None:
        """
        Simulated inference pipeline.

        In production this would run a person-detection / re-ID model.
        Here we increment a counter and periodically fire an alert.
        """
        self._frame_counter += 1

        if self._frame_counter % self._alert_interval != 0:
            return

        scenario = random.choice(UC1_SCENARIOS)

        alert = AlertEvent(
            camera_id=event.camera_id,
            timestamp=datetime.now(timezone.utc),
            severity=scenario["severity"],
            alert_type=scenario["alert_type"],
            title=scenario["title"],
            description=scenario["description"],
            source_event_id=event.event_id,
            source_uc=SourceUC.UC1,
            metadata=scenario["metadata"],
        )

        # Encode current frame as snapshot
        import cv2
        _, snap_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        snapshot_bytes = snap_buf.tobytes()

        success = await self.emit_alert(alert, snapshot_bytes=snapshot_bytes)
        if success:
            logger.info(
                "uc1_alert_emitted type=%s severity=%s camera=%s",
                alert.alert_type,
                alert.severity.value,
                event.camera_id,
            )
