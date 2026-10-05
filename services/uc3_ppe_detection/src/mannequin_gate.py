"""
UC3 Mannequin Gate — Filters out mannequins/statues from detection pipeline.
"""

from __future__ import annotations

import logging
from typing import List

from services.uc3_ppe_detection.src import config

logger = logging.getLogger(__name__)


def filter_mannequins(detections: list[dict]) -> list[dict]:
    """Filter out detections flagged as mannequins."""
    if not config.MANNEQUIN_GATE_ENABLED:
        return detections
    filtered = []
    for d in detections:
        lbl = d.get("label", "").lower()
        if lbl == "mannequin" and d.get("conf", 0) >= config.MANNEQUIN_CONF_THRESHOLD:
            continue
        filtered.append(d)
    return filtered
