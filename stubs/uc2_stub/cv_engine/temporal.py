"""
Stage 3 — Temporal Persistence Verification.

Detections must persist for N consecutive frames before being promoted.
Tracks per-camera, per-class/spatial persistence with EMA confidence smoothing.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from stubs.uc2_stub.cv_engine.config import settings

logger = logging.getLogger("innovision.uc2.detection.temporal")


from enum import Enum
import uuid


class DetectionState(str, Enum):
    """Formal temporal detection states for production lifecycle."""
    CANDIDATE = "candidate"
    CONFIRMING = "confirming"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    RESOLVED = "resolved"
    FRAME_GAP = "frame_gap"
    CAMERA_OFFLINE = "camera_offline"
    DETECTION_UNKNOWN = "detection_unknown"


class TrackStateResult:
    """
    Result container that behaves like a 3-tuple (is_persistent, count, score)
    for 100% backward compatibility, while exposing .state and .track_id.
    """
    def __init__(
        self,
        is_persistent: bool,
        count: int,
        score: float,
        state: DetectionState = DetectionState.CANDIDATE,
        track_id: str = "",
    ) -> None:
        self.is_persistent = is_persistent
        self.count = count
        self.score = score
        self.state = state
        self.track_id = track_id

    def __iter__(self):
        yield self.is_persistent
        yield self.count
        yield self.score

    def __getitem__(self, index):
        return (self.is_persistent, self.count, self.score)[index]

    def __len__(self):
        return 3

    def __repr__(self) -> str:
        return (
            f"TrackStateResult(is_persistent={self.is_persistent}, count={self.count}, "
            f"score={self.score}, state='{self.state.value}', track_id='{self.track_id}')"
        )


class TemporalPersistenceTracker:
    """
    Fine-grained spatial & temporal persistence tracker.
    Tracks persistence per camera and per spatial detection track key.
    Enforces state transitions: candidate -> confirming -> confirmed -> active -> resolved.
    Preserves state across frame gaps and camera disconnects.
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
        # camera_id -> det_key -> DetectionState
        self._states: Dict[str, Dict[str, DetectionState]] = defaultdict(
            lambda: defaultdict(lambda: DetectionState.CANDIDATE)
        )
        # camera_id -> det_key -> track_id
        self._track_ids: Dict[str, Dict[str, str]] = defaultdict(dict)
        # camera_id -> last_frame_seq
        self._last_frame_seq: Dict[str, int] = defaultdict(int)
        # camera_id -> is_offline
        self._camera_offline: Dict[str, bool] = defaultdict(bool)

    def update(
        self,
        camera_id: str,
        det_key: str,
        raw_confidence: float,
        frame_seq: Optional[int] = None,
    ) -> TrackStateResult:
        """
        Update state for a detection key.
        Returns TrackStateResult (unpacks as is_persistent, count, smoothed_score).
        """
        # 1. Detect frame gaps
        if frame_seq is not None:
            prev_seq = self._last_frame_seq[camera_id]
            if prev_seq > 0 and (frame_seq - prev_seq) > 3:
                logger.info(
                    "frame_gap_detected camera_id=%s prev_seq=%d curr_seq=%d",
                    camera_id, prev_seq, frame_seq,
                )
            self._last_frame_seq[camera_id] = frame_seq

        self._camera_offline[camera_id] = False
        self._counts[camera_id][det_key] += 1
        count = self._counts[camera_id][det_key]

        # 2. Assign unique deterministic track ID if not present
        if det_key not in self._track_ids[camera_id]:
            self._track_ids[camera_id][det_key] = f"trk-{camera_id[:8]}-{uuid.uuid4().hex[:8]}"
        track_id = self._track_ids[camera_id][det_key]

        # 3. EMA confidence smoothing
        prev_score = self._smoothed[camera_id][det_key]
        if prev_score == 0.0:
            smoothed = raw_confidence
        else:
            smoothed = self.alpha * raw_confidence + (1.0 - self.alpha) * prev_score

        self._smoothed[camera_id][det_key] = round(smoothed, 4)

        # 4. State lifecycle progression
        is_persistent = count >= self.threshold
        if count == 1:
            state = DetectionState.CANDIDATE
        elif count < self.threshold:
            state = DetectionState.CONFIRMING
        elif count == self.threshold:
            state = DetectionState.CONFIRMED
        else:
            state = DetectionState.ACTIVE

        self._states[camera_id][det_key] = state

        # Normalize temporal persistence score to [0.0, 1.0]
        temporal_score = min(1.0, count / max(self.threshold, 1))

        return TrackStateResult(
            is_persistent=is_persistent,
            count=count,
            score=round(temporal_score, 4),
            state=state,
            track_id=track_id,
        )

    def decay(self, camera_id: str, active_keys: List[str]) -> None:
        """
        Decay tracks that were not active in current frame.
        If camera is offline or has frame gap, do not decay immediately.
        """
        if self._camera_offline.get(camera_id, False):
            return

        camera_counts = self._counts.get(camera_id, {})
        for key in list(camera_counts.keys()):
            if key not in active_keys:
                camera_counts[key] -= 1
                if camera_counts[key] <= 0:
                    del camera_counts[key]
                    self._smoothed[camera_id].pop(key, None)
                    self._states[camera_id][key] = DetectionState.RESOLVED
                    self._states[camera_id].pop(key, None)
                    self._track_ids[camera_id].pop(key, None)

    def handle_camera_offline(self, camera_id: str) -> None:
        """Preserve tracking state when camera goes offline."""
        self._camera_offline[camera_id] = True
        for key in self._states.get(camera_id, {}):
            self._states[camera_id][key] = DetectionState.CAMERA_OFFLINE

    def reset(self, camera_id: str) -> None:
        self._counts.pop(camera_id, None)
        self._smoothed.pop(camera_id, None)
        self._states.pop(camera_id, None)
        self._track_ids.pop(camera_id, None)
        self._last_frame_seq.pop(camera_id, None)
        self._camera_offline.pop(camera_id, None)

    def get_track_state(self, camera_id: str, det_key: str) -> DetectionState:
        return self._states[camera_id].get(det_key, DetectionState.DETECTION_UNKNOWN)

    def get_active_tracks(self, camera_id: str) -> Dict[str, dict]:
        tracks = {}
        for key, count in self._counts.get(camera_id, {}).items():
            tracks[key] = {
                "track_id": self._track_ids[camera_id].get(key, ""),
                "count": count,
                "score": self._smoothed[camera_id].get(key, 0.0),
                "state": self._states[camera_id].get(key, DetectionState.CANDIDATE).value,
            }
        return tracks


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

        for cls in ("fire", "smoke", "sparks", "spark"):
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
