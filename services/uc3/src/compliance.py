"""
PPE compliance engine — ported natively for Innovision UC3.

Features:
1. Hybrid spatial association: 0.50*norm_dist + 0.30*IoU + 0.20*vertical_position
2. Per-tracked-worker PPE association
3. Temporal smoothing — hysteresis prevents single-frame false violations
4. Adaptive per-PPE overlap thresholds
5. Smarter body-part coverage rules (ignore invisible parts, both-hand logic)
6. False-positive filters (min area, confidence, out-of-frame PPE)
7. Optional DEBUG_ASSOCIATION logging
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque

from services.uc3.src.ppe_config import (
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

log = logging.getLogger("uc3_compliance")

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

PPE_TYPE_ALIASES: dict[str, set[str]] = {
    "helmet": {"helmet", "hard-hat", "hardhat"},
    "vest": {"vest", "safety-vest", "safety_vest", "medical-suit", "medical_suit", "safety-suit", "safety_suit"},
    "gloves": {"gloves", "glove"},
    "safety_shoes": {"safety_shoes", "shoes", "shoe", "boot", "boots", "safety-shoes"},
    "eye_prot": {"eye_prot", "glasses", "goggles", "safety-glasses", "safety_glasses"},
    "mask": {"mask", "face-mask", "face_mask", "face-guard", "face_guard", "face-shield", "face_shield"},
}

def is_ppe_required(ppe_type: str, required_ppe: frozenset[str] | None) -> bool:
    """
    Determine if a canonical PPE category is required.
    None = fallback standard platform default (all standard PPE required).
    frozenset() = explicitly 0 PPE required for this zone.
    """
    if required_ppe is None:
        return True
    aliases = PPE_TYPE_ALIASES.get(ppe_type, {ppe_type})
    req_norm = {r.strip().lower().replace("_", "-") for r in required_ppe}
    return any(a.replace("_", "-") in req_norm for a in aliases)

VERTICAL_EXPECTED: dict[str, int] = {
    "head":  +1,   # helmet above head
    "hands":  0,   # gloves beside/overlap hands
    "foot":  -1,   # boots below foot
    "face":  +1,   # mask/glasses above or at face level
}

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
    log.info("Temporal state initialised for new session.")
    return {}

def _get_worker_state(worker_id: int, worker_states: WorkerStates) -> _WorkerState:
    if worker_id not in worker_states:
        worker_states[worker_id] = _WorkerState()
    return worker_states[worker_id]

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
        dc = _centre(tuple(det["box"]))
        best_pi = min(
            range(len(persons)),
            key=lambda i: (
                (_centre(tuple(persons[i]["box"]))[0] - dc[0]) ** 2 +
                (_centre(tuple(persons[i]["box"]))[1] - dc[1]) ** 2
            ),
        )
        groups[best_pi].append(det)

    return groups

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

    by_label: dict[str, list[dict]] = defaultdict(list)
    for d in worker_dets:
        norm_label = d["label"].strip().lower().replace("_", "-")
        by_label[norm_label].append(d)

    # Default all worker detections to compliant and non-violation
    for d in worker_dets:
        d["compliant"] = True
        d["is_violation"] = False

    # 6 Canonical PPE evaluations covering model supported positive and negative classes
    PPE_EVALUATIONS = [
        {
            "category": "helmet",
            "part": "head",
            "violation": "no-head-protection",
            "pos_labels": {"helmet", "hard-hat", "hardhat"},
            "neg_labels": {"no-helmet"},
            "anatomical_part": "head",
        },
        {
            "category": "vest",
            "part": "vest",
            "violation": "no-safety-vest",
            "pos_labels": {"safety-vest", "safety_vest", "vest", "medical-suit", "medical_suit", "safety-suit", "safety_suit"},
            "neg_labels": {"no-vest"},
            "anatomical_part": None,
        },
        {
            "category": "gloves",
            "part": "hands",
            "violation": "no-hands-protection",
            "pos_labels": {"gloves", "glove"},
            "neg_labels": {"no-gloves"},
            "anatomical_part": "hands",
        },
        {
            "category": "safety_shoes",
            "part": "foot",
            "violation": "no-foot-protection",
            "pos_labels": {"shoes", "shoe", "boot", "boots", "safety-shoes"},
            "neg_labels": {"no-shoe", "no-shoes"},
            "anatomical_part": "foot",
        },
        {
            "category": "eye_prot",
            "part": "eye",
            "violation": "no-eye-protection",
            "pos_labels": {"glasses", "goggles", "safety-glasses", "safety_glasses", "face-guard", "face_guard"},
            "neg_labels": {"no-goggles"},
            "anatomical_part": None,
        },
        {
            "category": "mask",
            "part": "face",
            "violation": "no-face-protection",
            "pos_labels": {"face-guard", "face_guard", "face-shield", "face_shield", "face-mask", "face_mask", "mask"},
            "neg_labels": {"no-mask"},
            "anatomical_part": "face",
        },
    ]

    for item in PPE_EVALUATIONS:
        cat = item["category"]
        part = item["part"]
        vio_name = item["violation"]
        pos_labels = item["pos_labels"]
        neg_labels = item["neg_labels"]
        anat_part = item["anatomical_part"]

        # Check zone requirement
        if not is_ppe_required(cat, required_ppe):
            # Not required: mark state as compliant, and any negative detections as compliant
            state.update(part, covered=True, now=now)
            for nl in neg_labels:
                for d in by_label.get(nl, []):
                    d["compliant"] = True
                    d["is_violation"] = False
            continue

        pos_dets = [d for nl in pos_labels for d in by_label.get(nl, [])]
        neg_dets = [d for nl in neg_labels for d in by_label.get(nl, [])]
        anat_entries = (
            [
                d for d in by_label.get(anat_part, [])
                if _area(tuple(d["box"])) >= MIN_BODY_PART_AREA
            ]
            if anat_part is not None
            else []
        )

        has_pos = len(pos_dets) > 0
        has_neg = len(neg_dets) > 0

        covered = True

        if has_pos and has_neg:
            # Positive/negative conflict reconciliation on the same tracked worker
            best_pos_conf = max(d["conf"] for d in pos_dets)
            best_neg_conf = max(d["conf"] for d in neg_dets)
            if best_pos_conf >= best_neg_conf:
                covered = True
            else:
                covered = False
        elif has_neg:
            # Only negative detected: directly contributes to missing PPE
            covered = False
        elif has_pos:
            # Only positive detected
            covered = True
        else:
            # Neither positive nor negative detected
            if anat_part is not None:
                # Check anatomical body part
                if anat_entries:
                    # Anatomical part is visible, but no PPE detected covering it
                    covered = False
                else:
                    # Anatomical part is not detected.
                    # Per requirement 10: do not use absence of anatomical part as sole evidence of missing PPE.
                    covered = True
            else:
                # Vest or eye: check if person is detected
                if "person" in by_label or "worker" in by_label:
                    covered = False
                else:
                    covered = True

        was_active = state._timeline(part).violation_active
        raise_violation = state.update(part, covered=covered, now=now)

        if raise_violation:
            frame_violations.append(vio_name)
            if not was_active:
                worker_violations.append({
                    "worker_id": worker_id,
                    "ppe_type": cat,
                    "violation": vio_name,
                    "confidence": state._timeline(part).last_fraction_missing,
                })

            # Geometry localization for confirmed missing PPE violation
            if not covered:
                vio_display_label = f"No {cat.replace('_', ' ').title()}"
                if has_neg and neg_dets:
                    for nd in neg_dets:
                        nd["compliant"] = False
                        nd["is_violation"] = True
                        nd["violation_type"] = vio_name
                        nd["violation_label"] = vio_display_label
                elif anat_entries:
                    for ad in anat_entries:
                        ad["compliant"] = False
                        ad["is_violation"] = True
                        ad["violation_type"] = vio_name
                        ad["violation_label"] = vio_display_label
                else:
                    person_entries = by_label.get("person", []) or by_label.get("worker", [])
                    if person_entries:
                        p = person_entries[0]
                        worker_dets.append({
                            "box": p["box"],
                            "conf": round(state._timeline(part).last_fraction_missing or p["conf"], 2),
                            "label": f"no-{cat}",
                            "_track_id": worker_id,
                            "compliant": False,
                            "is_violation": True,
                            "violation_type": vio_name,
                            "violation_label": vio_display_label,
                        })
        else:
            # Not confirmed active: all candidate detections remain compliant
            for nd in neg_dets:
                nd["compliant"] = True
                nd["is_violation"] = False
            for ad in anat_entries:
                ad["compliant"] = True
                ad["is_violation"] = False

    for d in worker_dets:
        if "compliant" not in d:
            d["compliant"] = True

def evaluate_compliance(
    detections: list[dict],
    worker_states: WorkerStates,
    now: float,
    required_ppe: frozenset[str] | None = None,
    min_confidence: float | None = None,
) -> tuple[str, list[str], list[dict]]:
    eff_conf = min_confidence if min_confidence is not None else CONF_THRESHOLD

    for d in detections:
        if d["conf"] < eff_conf:
            d["compliant"] = True
            d["is_violation"] = False

    active = [d for d in detections if d["conf"] >= eff_conf]
    worker_groups = _group_by_worker(active)

    frame_violations: list[str] = []
    worker_violations: list[dict] = []

    for worker_id, worker_dets in worker_groups.items():
        orig_len = len(worker_dets)
        _evaluate_worker(
            worker_id, worker_dets, frame_violations, worker_violations,
            worker_states, now, required_ppe,
        )
        if len(worker_dets) > orig_len:
            for new_d in worker_dets[orig_len:]:
                detections.append(new_d)

    for d in detections:
        if "compliant" not in d:
            d["compliant"] = True
        if "is_violation" not in d:
            d["is_violation"] = not d["compliant"]

    seen:       set[str] = set()
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
