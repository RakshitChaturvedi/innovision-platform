"""
UC3 PPE Compliance Engine — Track-based, Duration-weighted Sliding Window Engine.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Set, Tuple

from services.uc3_ppe_detection.src import config

logger = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]


# ── Constants & Mappings ──────────────────────────────────────────────────────

REQUIRED_PPE: dict[str, list[str]] = {
    "head": [
        "helmet", "hard-hat", "hardhat",
        "face-guard", "face_guard", "face-shield", "face_shield",
        "medical-suit", "medical_suit", "safety-suit", "safety_suit",
    ],
    "hands": [
        "gloves", "glove",
        "medical-suit", "medical_suit", "safety-suit", "safety_suit",
    ],
    "foot": [
        "boots", "boot", "shoes",
        "medical-suit", "medical_suit", "safety-suit", "safety_suit",
    ],
}

ALWAYS_COMPLIANT: set[str] = {
    "helmet", "hard-hat", "hardhat",
    "gloves", "glove", "boots", "boot", "shoes",
    "safety-vest", "safety_vest", "vest",
    "medical-suit", "medical_suit", "safety-suit", "safety_suit",
    "glasses", "goggles", "safety-glasses", "safety_glasses",
    "mask", "face-mask", "face_mask", "face-guard", "face_guard", "face-shield", "face_shield",
}

PART_TO_PPE_TYPE: dict[str, str] = {
    "head": "helmet",
    "hands": "gloves",
    "foot": "safety_boots",
}

PERSON_CHECK_TO_PPE_TYPE: dict[str, str] = {
    "vest": "safety_jacket",
    "eye": "eye_protection",
}


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _area(box: Box) -> int:
    w = max(0, box[2] - box[0])
    h = max(0, box[3] - box[1])
    return w * h


def _centre(box: Box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0


def _iou(a: Box, b: Box) -> float:
    ix1 = max(a[0], b[0])
    iy1 = max(a[1], b[1])
    ix2 = min(a[2], b[2])
    iy2 = min(a[3], b[3])
    iw = max(0, ix2 - ix1)
    ih = max(0, iy2 - iy1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    union = _area(a) + _area(b) - inter
    return inter / union if union > 0 else 0.0


def _association_score(part_box: Box, ppe_box: Box, part_label: str = "") -> float:
    cx_part, cy_part = _centre(part_box)
    cx_ppe, cy_ppe = _centre(ppe_box)
    part_w = max(1.0, float(part_box[2] - part_box[0]))
    part_h = max(1.0, float(part_box[3] - part_box[1]))
    diag = (part_w ** 2 + part_h ** 2) ** 0.5

    dist = ((cx_part - cx_ppe) ** 2 + (cy_part - cy_ppe) ** 2) ** 0.5
    norm_dist = max(0.0, 1.0 - (dist / diag))

    iou_val = _iou(part_box, ppe_box)

    if part_label == "head":
        vpos = max(0.0, 1.0 - max(0.0, cy_ppe - cy_part) / part_h)
    elif part_label == "foot":
        vpos = max(0.0, 1.0 - max(0.0, cy_part - cy_ppe) / part_h)
    else:
        vpos = max(0.0, 1.0 - abs(cy_part - cy_ppe) / part_h)

    return (
        config.ASSOC_W_DIST * norm_dist
        + config.ASSOC_W_IOU * iou_val
        + config.ASSOC_W_VPOS * vpos
    )


def _is_in_frame(box: Box) -> bool:
    return (box[2] > box[0]) and (box[3] > box[1])


# ── Sliding Window State Tracking ──────────────────────────────────────────────

class PartTimeline:
    def __init__(self) -> None:
        self.samples: list[tuple[float, bool]] = []
        self.violation_active: bool = False
        self.last_fraction_missing: float = 0.0

    def prune(self, now: float) -> None:
        cutoff = now - config.VIOLATION_WINDOW_SECONDS
        self.samples = [(t, missing) for t, missing in self.samples if t >= cutoff]

    def add_sample(self, now: float, is_missing: bool) -> None:
        self.samples.append((now, is_missing))
        self.prune(now)

    def evaluate(self, now: float) -> bool:
        self.prune(now)
        if len(self.samples) < config.MIN_EVIDENCE_SAMPLES:
            return self.violation_active

        span = self.samples[-1][0] - self.samples[0][0]
        if span < config.MIN_EVIDENCE_SECONDS:
            return self.violation_active

        missing_dt = 0.0
        total_dt = 0.0
        for i in range(1, len(self.samples)):
            t_prev, m_prev = self.samples[i - 1]
            t_curr, _ = self.samples[i]
            dt = min(t_curr - t_prev, config.MAX_SAMPLE_GAP_SECONDS)
            total_dt += dt
            if m_prev:
                missing_dt += dt

        if total_dt <= 0:
            return self.violation_active

        fraction_missing = missing_dt / total_dt
        self.last_fraction_missing = fraction_missing

        if not self.violation_active:
            if fraction_missing >= config.VIOLATION_RAISE_FRACTION:
                self.violation_active = True
                return True
        else:
            if fraction_missing <= config.VIOLATION_CLEAR_FRACTION:
                self.violation_active = False

        return False


class WorkerState:
    def __init__(self, worker_id: int) -> None:
        self.worker_id = worker_id
        self.timelines: dict[str, PartTimeline] = defaultdict(PartTimeline)

    def update(self, part: str, covered: bool, now: float) -> bool:
        tl = self.timelines[part]
        tl.add_sample(now, is_missing=not covered)
        return tl.evaluate(now)


class WorkerStates:
    def __init__(self) -> None:
        self.workers: dict[int, WorkerState] = {}

    def get(self, worker_id: int) -> WorkerState:
        if worker_id not in self.workers:
            self.workers[worker_id] = WorkerState(worker_id)
        return self.workers[worker_id]


def _group_by_worker(detections: list[dict]) -> dict[int, list[dict]]:
    groups: dict[int, list[dict]] = defaultdict(list)
    persons: list[dict] = []
    non_persons: list[dict] = []

    for d in detections:
        lbl = d.get("label", "").lower()
        if lbl in ("person", "worker"):
            persons.append(d)
        else:
            non_persons.append(d)

    if persons:
        for idx, p in enumerate(persons):
            wid = p.get("track_id", idx + 1)
            groups[wid].append(p)

    for det in non_persons:
        if persons:
            dc = _centre(tuple(det["box"]))
            best_i = min(
                range(len(persons)),
                key=lambda i: (
                    (_centre(tuple(persons[i]["box"]))[0] - dc[0]) ** 2
                    + (_centre(tuple(persons[i]["box"]))[1] - dc[1]) ** 2
                ),
            )
            wid = persons[best_i].get("track_id", best_i + 1)
            groups[wid].append(det)
        else:
            groups[1].append(det)

    return groups


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_compliance(
    detections: list[dict],
    worker_states: WorkerStates,
    now: float,
    required_ppe: set[str] | None = None,
) -> tuple[str, list[str], list[dict]]:
    """
    Evaluate PPE compliance for detections in a frame.
    Mutates detection dicts by adding 'compliant' key.
    Returns (severity, unique_violations, worker_violations).
    """
    for d in detections:
        if d.get("conf", 1.0) < config.CONF_THRESHOLD:
            d["compliant"] = True

    active = [d for d in detections if d.get("conf", 1.0) >= config.CONF_THRESHOLD]
    worker_groups = _group_by_worker(active)

    frame_violations: list[str] = []
    worker_violations: list[dict] = []

    for worker_id, worker_dets in worker_groups.items():
        state = worker_states.get(worker_id)

        by_label: dict[str, list[tuple[int, Box]]] = defaultdict(list)
        for idx, d in enumerate(worker_dets):
            by_label[d["label"].lower()].append((idx, tuple(d["box"])))

        for d in worker_dets:
            if d["label"].lower() in ALWAYS_COMPLIANT:
                d["compliant"] = True

        claimed_global: set[tuple[str, int]] = set()

        for part, protectors in REQUIRED_PPE.items():
            if required_ppe is not None and PART_TO_PPE_TYPE[part] not in required_ppe:
                state.update(part, covered=True, now=now)
                continue

            part_entries = by_label.get(part, [])
            if not part_entries:
                state.update(part, covered=True, now=now)
                continue

            valid_parts = [
                (idx, box) for idx, box in part_entries
                if _area(box) >= config.MIN_BODY_PART_AREA * 640 * 640
            ]
            if not valid_parts:
                state.update(part, covered=True, now=now)
                continue

            ppe_candidates: list[tuple[str, int, Box]] = []
            for ppe_lbl in protectors:
                for local_idx, ppe_box in by_label.get(ppe_lbl, []):
                    if (ppe_lbl, local_idx) in claimed_global:
                        continue
                    if not _is_in_frame(ppe_box):
                        continue
                    ppe_candidates.append((ppe_lbl, local_idx, ppe_box))

            triples: list[tuple[float, int, tuple[str, int, Box]]] = []
            for part_i, (_, part_box) in enumerate(valid_parts):
                for cand in ppe_candidates:
                    score = _association_score(part_box, cand[2], part_label=part)
                    triples.append((score, part_i, cand))

            triples.sort(reverse=True, key=lambda x: x[0])

            used_parts: set[int] = set()
            used_ppe: set[tuple[str, int]] = set()
            coverage: dict[int, bool] = {}

            for score, part_i, cand in triples:
                ppe_lbl, local_idx, ppe_box = cand
                ppe_key = (ppe_lbl, local_idx)
                if part_i in used_parts or ppe_key in used_ppe:
                    continue
                threshold = config.PPE_OVERLAP.get(ppe_lbl, config.OVERLAP_THRESHOLD)
                iou_val = _iou(valid_parts[part_i][1], ppe_box)
                covered = iou_val >= threshold
                coverage[part_i] = covered
                used_parts.add(part_i)
                used_ppe.add(ppe_key)
                if covered:
                    claimed_global.add(ppe_key)

            for pi in range(len(valid_parts)):
                if pi not in coverage:
                    coverage[pi] = False

            all_covered = all(coverage.values()) if coverage else False

            for pi, (det_idx, _) in enumerate(valid_parts):
                worker_dets[det_idx]["compliant"] = coverage.get(pi, False)

            was_active = state.timelines[part].violation_active
            raise_violation = state.update(part, covered=all_covered, now=now)
            if raise_violation:
                frame_violations.append(f"no-{part}-protection")
                if not was_active:
                    worker_violations.append({
                        "worker_id": worker_id,
                        "ppe_type": PART_TO_PPE_TYPE[part],
                        "violation": f"no-{part}-protection",
                        "confidence": state.timelines[part].last_fraction_missing,
                    })

    for d in detections:
        if "compliant" not in d:
            d["compliant"] = True

    seen: set[str] = set()
    unique_vio: list[str] = []
    for v in frame_violations:
        if v not in seen:
            seen.add(v)
            unique_vio.append(v)

    if not unique_vio:
        severity = "ok"
    elif len(unique_vio) == 1:
        severity = "medium"
    else:
        severity = "high"

    return severity, unique_vio, worker_violations
