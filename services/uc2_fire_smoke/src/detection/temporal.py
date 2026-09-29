"""
Stage 3 — Temporal Persistence Verification.

Detections must persist for N consecutive frames before being promoted.
Tracks per-camera, per-class/spatial persistence with EMA confidence smoothing.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from services.uc2_fire_smoke.src.config import settings

logger = logging.getLogger("innovision.uc2.detection.temporal")


class TemporalPersistenceTracker:
    """
    Fine-grained spatial & temporal persistence tracker.
    Tracks persistence per camera and per spatial detection track key.
    """

    def __init__(
        self,
        persistence_threshold: Optional[int] = None,
        smoothing_alpha: Optional[float] = None,
    ) -> None:
        self.threshold = persistence_threshold or settings.temporal_frames
        self.alpha = smoothing_alpha or settings.smoothing_alpha
        # camera_id -> det_key -> consecutive_count
        self._counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # camera_id -> det_key -> smoothed_confidence
        self._smoothed: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def update(
        self,
        camera_id: str,
        det_key: str,
        raw_confidence: float,
    ) -> Tuple[bool, int, float]:
        """
        Update state for a detection key.
        Returns (is_persistent, consecutive_count, smoothed_score).
        """
        self._counts[camera_id][det_key] += 1
        count = self._counts[camera_id][det_key]

        prev_score = self._smoothed[camera_id][det_key]
        if prev_score == 0.0:
            smoothed = raw_confidence
        else:
            smoothed = self.alpha * raw_confidence + (1.0 - self.alpha) * prev_score

        self._smoothed[camera_id][det_key] = round(smoothed, 4)

        is_persistent = count >= self.threshold
        # Normalize temporal persistence score to [0.0, 1.0]
        temporal_score = min(1.0, count / max(self.threshold, 1))

        return is_persistent, count, round(temporal_score, 4)

    def decay(self, camera_id: str, active_keys: List[str]) -> None:
        """Decay or clear tracks that were not active in current frame."""
        camera_counts = self._counts.get(camera_id, {})
        for key in list(camera_counts.keys()):
            if key not in active_keys:
                camera_counts[key] -= 1
                if camera_counts[key] <= 0:
                    del camera_counts[key]
                    if key in self._smoothed[camera_id]:
                        del self._smoothed[camera_id][key]

    def reset(self, camera_id: str) -> None:
        self._counts.pop(camera_id, None)
        self._smoothed.pop(camera_id, None)


class TemporalVerifier:
    """Tracks detection persistence across consecutive frames per camera."""

    def __init__(self) -> None:
        self._counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._smoothed: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    def update(
        self,
        camera_id: str,
        detections: List[Dict[str, Any]],
        required_frames: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
        req = required_frames if required_frames is not None else settings.temporal_frames
        alpha = settings.smoothing_alpha

        detected_classes = {d["detection_type"] for d in detections}

        for cls in ("fire", "smoke"):
            if cls in detected_classes:
                self._counters[camera_id][cls] += 1
                class_max = max(
                    (d["confidence"] for d in detections if d["detection_type"] == cls),
                    default=0.0,
                )
                prev = self._smoothed[camera_id][cls]
                self._smoothed[camera_id][cls] = (
                    class_max if prev == 0.0
                    else round(alpha * class_max + (1 - alpha) * prev, 4)
                )
            else:
                self._counters[camera_id][cls] = 0
                self._smoothed[camera_id][cls] = 0.0

        verified: List[Dict[str, Any]] = []
        temporal_scores: Dict[str, float] = {}

        for d in detections:
            cls = d["detection_type"]
            count = self._counters[camera_id][cls]
            t_score = min(1.0, count / max(req, 1))
            temporal_scores[cls] = round(t_score, 4)

            if count >= req:
                d["confidence"] = self._smoothed[camera_id][cls]
                d["temporal_frames"] = count
                verified.append(d)

        return verified, temporal_scores

    def reset(self, camera_id: str) -> None:
        self._counters.pop(camera_id, None)
        self._smoothed.pop(camera_id, None)

    def get_state(self, camera_id: str) -> dict:
        return {
            "counters": dict(self._counters.get(camera_id, {})),
            "smoothed": dict(self._smoothed.get(camera_id, {})),
        }
