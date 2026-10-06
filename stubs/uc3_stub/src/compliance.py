"""
PPE compliance engine — v3 for Platform Integration.

Evaluates detected objects (person, body parts, PPE items) using:
1. Hybrid spatial association: 0.50*norm_dist + 0.30*IoU + 0.20*vertical_position
2. Per-tracked-worker PPE association
3. Temporal duration-weighted sliding window hysteresis (VIOLATION_WINDOW_SECONDS)
4. Adaptive per-PPE overlap thresholds
5. Smarter body-part coverage rules (invisible parts covered, single-hand logic)
6. False-positive filters (min area, confidence, out-of-frame PPE)
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from typing import Optional

from stubs.uc3_stub.src.config import (
    CONF_THRESHOLD,
    PPE_OVERLAP,
    OVERLAP_THRESHOLD,
    ASSOC_W_DIST,
    ASSOC_W_IOU,
    ASSOC_W_VPOS,
    VIOLATION_WINDOW_SECONDS,
    VIOLATION_RAISE_FRACTION,
    VIOLATION_CLEAR_FRACTION,
    MIN_EVIDENCE_SECONDS,
    MIN_EVIDENCE_SAMPLES,
    MAX_SAMPLE_GAP_SECONDS,
    MIN_BODY_PART_AREA,
    DEBUG_ASSOCIATION,
)

log = logging.getLogger("uc3.compliance")

# ── Type alias ─────────────────────────────────────────────────────────────────
Box = tuple[float, float, float, float]   # normalised (x1, y1, x2, y2)

# ── Always-compliant labels ────────────────────────────────────────────────────
ALWAYS_COMPLIANT: frozenset[str] = frozenset({
    "person",
    "helmet", "hard-hat", "hardhat",
    "gloves", "glove",
    "shoes", "boot", "boots",
    "safety-vest", "safety_vest", "vest",
    "medical-suit", "medical_suit",
    "safety-suit", "safety_suit",
    "face-guard", "face_guard", "face-shield", "face_shield",
    "face-mask", "face_mask", "mask",
    "glasses", "goggles", "safety-glasses", "safety_glasses",
})

# ── Required PPE per body part ─────────────────────────────────────────────────
REQUIRED_PPE: dict[str, list[str]] = {
    "head":  ["helmet", "hard-hat", "hardhat"],
    "hands": ["gloves", "glove"],
    "foot":  ["shoes", "boot", "boots"],
    "face":  ["face-guard", "face_guard", "face-shield", "face_shield",
              "face-mask", "face_mask", "mask"],
}

# ── Map each check to zone-policy PPE type id ─────────────────────────────────
PART_TO_PPE_TYPE: dict[str, str] = {
    "head":  "helmet",
    "hands": "gloves",
    "foot":  "safety_shoes",
    "face":  "mask",
}
PERSON_CHECK_TO_PPE_TYPE: dict[str, str] = {
    "vest": "vest",
    "eye":  "eye_prot",
}

VERTICAL_EXPECTED: dict[str, int] = {
    "head":  +1,   # helmet above head
    "hands":  0,   # gloves beside/overlap hands
    "foot":  -1,   # boots below foot
    "face":  +1,   # mask/glasses above or at face level
}


# ── Geometry ──────────────────────────────────────────────────────────────────

def _iou(a: Box, b: Box) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1 = max(ax1, bx1); iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2); iy2 = min(ay2, by2)
    inter  = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union  = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _centre(b: Box) -> tuple[float, float]:
    return ((b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5)


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _is_in_frame(b: Box, margin: float = 0.01) -> bool:
    x1, y1, x2, y2 = b
    return x1 >= -margin and y1 >= -margin and x2 <= 1 + margin and y2 <= 1 + margin


# ── Hybrid association score ──────────────────────────────────────────────────

def _association_score(
    part_box: Box,
    ppe_box:  Box,
    part_label: str,
) -> float:
    px, py = _centre(part_box)
    qx, qy = _centre(ppe_box)

    pw = part_box[2] - part_box[0]
    ph = part_box[3] - part_box[1]
    diag = math.sqrt(pw * pw + ph * ph) or 1e-6
    dist = math.sqrt((px - qx) ** 2 + (py - qy) ** 2)
    norm_dist = max(0.0, 1.0 - dist / diag)

    iou = _iou(part_box, ppe_box)

    expected = VERTICAL_EXPECTED.get(part_label, 0)
    if expected == 0:
        v_score = 0.5
    else:
        diff = (py - qy) * expected
        v_score = 1.0 if diff >= 0 else 0.0

    score = (
        ASSOC_W_DIST * norm_dist +
        ASSOC_W_IOU  * iou       +
        ASSOC_W_VPOS * v_score
    )
    return score


# ── Per-worker temporal state ─────────────────────────────────────────────────

class _PartTimeline:
    __slots__ = ("samples", "violation_active", "first_seen_ts", "last_fraction_missing")

    def __init__(self) -> None:
        self.samples: deque[tuple[float, bool]] = deque()
        self.violation_active: bool = False
        self.first_seen_ts: float | None = None
        self.last_fraction_missing: float = 0.0


class _WorkerState:
    def __init__(self) -> None:
        self._parts: dict[str, _PartTimeline] = {}

    def _timeline(self, part: str) -> _PartTimeline:
        tl = self._parts.get(part)
        if tl is None:
            tl = self._parts[part] = _PartTimeline()
        return tl

    def update(self, part: str, covered: bool, now: float) -> bool:
        tl = self._timeline(part)

        if tl.first_seen_ts is None:
            tl.first_seen_ts = now

        tl.samples.append((now, covered))

        window_start = now - VIOLATION_WINDOW_SECONDS
        while len(tl.samples) > 1 and tl.samples[1][0] < window_start:
            tl.samples.popleft()

        missing_time = 0.0
        total_time = 0.0
        samples = tl.samples
        for i in range(1, len(samples)):
            t_prev, covered_prev = samples[i - 1]
            t_cur, _ = samples[i]
            seg = min(t_cur - t_prev, MAX_SAMPLE_GAP_SECONDS)
            if seg <= 0:
                continue
            total_time += seg
            if not covered_prev:
                missing_time += seg

        fraction_missing = (missing_time / total_time) if total_time > 0 else (0.0 if covered else 1.0)
        tl.last_fraction_missing = fraction_missing

        evidence_ok = (
            (now - tl.first_seen_ts) >= MIN_EVIDENCE_SECONDS
            and len(samples) >= MIN_EVIDENCE_SAMPLES
        )

        if evidence_ok:
            if fraction_missing >= VIOLATION_RAISE_FRACTION:
                tl.violation_active = True
            elif fraction_missing <= VIOLATION_CLEAR_FRACTION:
                tl.violation_active = False

        return tl.violation_active


WorkerStates = dict[int, _WorkerState]


def new_session_state() -> WorkerStates:
    log.info("Temporal state initialised for new session/camera.")
    return {}


def _get_worker_state(worker_id: int, worker_states: WorkerStates) -> _WorkerState:
    if worker_id not in worker_states:
        worker_states[worker_id] = _WorkerState()
    return worker_states[worker_id]


# ── Worker grouping ───────────────────────────────────────────────────────────

def _group_by_worker(detections: list[dict]) -> dict[int, list[dict]]:
    has_ids = any(d.get("_track_id") is not None for d in detections)
    groups: dict[int, list[dict]] = defaultdict(list)

    if has_ids:
        for d in detections:
            tid = d.get("_track_id")
            if tid is None:
                groups[-1].append(d)
            else:
                groups[int(tid)].append(d)
        return groups

    persons = [d for d in detections if d["label"].lower() == "person"]
    non_persons = [d for d in detections if d["label"].lower() != "person"]

    if not persons:
        groups[-1].extend(detections)
        return groups

    for pi, p in enumerate(persons):
        groups[pi].append(p)

    for det in non_persons:
        dc = _centre(tuple(det["box"]))  # type: ignore[arg-type]
        best_pi = min(
            range(len(persons)),
            key=lambda i: (
                (_centre(tuple(persons[i]["box"]))[0] - dc[0]) ** 2 +  # type: ignore[arg-type]
                (_centre(tuple(persons[i]["box"]))[1] - dc[1]) ** 2    # type: ignore[arg-type]
            ),
        )
        groups[best_pi].append(det)

    return groups


# ── Single-worker compliance evaluation ──────────────────────────────────────

def _evaluate_worker(
    worker_id:    int,
    worker_dets:  list[dict],
    frame_violations: list[str],
    worker_violations: list[dict],
    worker_states: WorkerStates,
    now: float,
    required_ppe: frozenset[str] | None,
) -> None:
    state = _get_worker_state(worker_id, worker_states)

    by_label: dict[str, list[tuple[int, Box]]] = defaultdict(list)
    for idx, d in enumerate(worker_dets):
        by_label[d["label"].lower()].append((idx, tuple(d["box"])))  # type: ignore[arg-type]

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

        valid_part_entries = [
            (idx, box) for idx, box in part_entries
            if _area(box) >= MIN_BODY_PART_AREA
        ]
        if not valid_part_entries:
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

        assignment_triples: list[tuple[float, int, tuple[str, int, Box]]] = []
        for part_local_i, (_, part_box) in enumerate(valid_part_entries):
            for cand in ppe_candidates:
                _, _, ppe_box = cand
                score = _association_score(part_box, ppe_box, part_label=part)
                assignment_triples.append((score, part_local_i, cand))

        assignment_triples.sort(reverse=True)

        used_parts:  set[int]              = set()
        used_ppe:    set[tuple[str, int]]  = set()
        coverage:    dict[int, bool]       = {}

        for score, part_local_i, cand in assignment_triples:
            ppe_lbl, local_idx, ppe_box = cand
            ppe_key = (ppe_lbl, local_idx)
            if part_local_i in used_parts or ppe_key in used_ppe:
                continue
            threshold = PPE_OVERLAP.get(ppe_lbl, OVERLAP_THRESHOLD)
            iou = _iou(valid_part_entries[part_local_i][1], ppe_box)
            covered = iou >= threshold
            coverage[part_local_i] = covered
            used_parts.add(part_local_i)
            used_ppe.add(ppe_key)
            if covered:
                claimed_global.add(ppe_key)

        for pi in range(len(valid_part_entries)):
            if pi not in coverage:
                coverage[pi] = False

        all_covered = all(coverage.values()) if coverage else False

        for pi, (det_idx, _) in enumerate(valid_part_entries):
            worker_dets[det_idx]["compliant"] = coverage.get(pi, False)

        was_active = state._timeline(part).violation_active
        raise_violation = state.update(part, covered=all_covered, now=now)
        if raise_violation:
            frame_violations.append(f"no-{part}-protection")
            if not was_active:
                worker_violations.append({
                    "worker_id": worker_id,
                    "ppe_type": PART_TO_PPE_TYPE[part],
                    "violation": f"no-{part}-protection",
                    "confidence": state._timeline(part).last_fraction_missing,
                })

    if "person" in by_label:
        vest_required = required_ppe is None or PERSON_CHECK_TO_PPE_TYPE["vest"] in required_ppe
        eye_required  = required_ppe is None or PERSON_CHECK_TO_PPE_TYPE["eye"]  in required_ppe

        has_vest = any(
            lbl in by_label
            for lbl in ("safety-vest", "safety_vest", "vest",
                        "medical-suit", "medical_suit",
                        "safety-suit", "safety_suit")
        )
        has_eye = any(
            lbl in by_label
            for lbl in ("glasses", "goggles", "safety-glasses", "safety_glasses",
                        "face-guard", "face_guard")
        )

        if not vest_required:
            state.update("vest", covered=True, now=now)
        elif not has_vest:
            was_active = state._timeline("vest").violation_active
            if state.update("vest", covered=False, now=now):
                frame_violations.append("no-safety-vest")
                if not was_active:
                    worker_violations.append({
                        "worker_id": worker_id, "ppe_type": "vest",
                        "violation": "no-safety-vest",
                        "confidence": state._timeline("vest").last_fraction_missing,
                    })
        else:
            state.update("vest", covered=True, now=now)

        if not eye_required:
            state.update("eye", covered=True, now=now)
        elif not has_eye:
            was_active = state._timeline("eye").violation_active
            if state.update("eye", covered=False, now=now):
                frame_violations.append("no-eye-protection")
                if not was_active:
                    worker_violations.append({
                        "worker_id": worker_id, "ppe_type": "eye_prot",
                        "violation": "no-eye-protection",
                        "confidence": state._timeline("eye").last_fraction_missing,
                    })
        else:
            state.update("eye", covered=True, now=now)

    for d in worker_dets:
        if "compliant" not in d:
            d["compliant"] = True


# ── Public API ────────────────────────────────────────────────────────────────

def evaluate_compliance(
    detections: list[dict],
    worker_states: WorkerStates,
    now: float,
    required_ppe: frozenset[str] | None = None,
) -> tuple[str, list[str], list[dict]]:
    """
    Evaluate PPE compliance for a single frame.

    Mutates each dict in `detections` by adding ``compliant: bool``.
    Returns (severity, violations, worker_violations).
    """
    for d in detections:
        if d["conf"] < CONF_THRESHOLD:
            d["compliant"] = True

    active = [d for d in detections if d["conf"] >= CONF_THRESHOLD]
    worker_groups = _group_by_worker(active)

    frame_violations: list[str] = []
    worker_violations: list[dict] = []

    for worker_id, worker_dets in worker_groups.items():
        _evaluate_worker(
            worker_id, worker_dets, frame_violations, worker_violations,
            worker_states, now, required_ppe,
        )

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
