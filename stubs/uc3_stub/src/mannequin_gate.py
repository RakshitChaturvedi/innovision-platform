"""
Mannequin exclusion gate — stage between motion pre-gate and PPE model.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
from ultralytics import YOLO

from stubs.uc3_stub.src import config

log = logging.getLogger("uc3.mannequin_gate")

Box = tuple[float, float, float, float]
_thread_local = threading.local()


def enabled() -> bool:
    model_path = getattr(config, "MANNEQUIN_MODEL_PATH", None)
    return bool(model_path) and Path(model_path).is_file()


def _get_thread_model() -> YOLO:
    model = getattr(_thread_local, "model", None)
    if model is None:
        model_path = str(config.MANNEQUIN_MODEL_PATH)
        model = YOLO(model_path)
        names = {str(v).lower(): int(k) for k, v in model.names.items()}
        if "person" not in names or "mannequin" not in names:
            raise RuntimeError(f"{model_path} must have 'person' and 'mannequin' classes, got {model.names}")
        _thread_local.names = names
        imgsz = getattr(config, "PERSON_GATE_IMAGE_SIZE", 1280)
        model.predict(np.zeros((imgsz, imgsz, 3), dtype=np.uint8), imgsz=imgsz, verbose=False)
        _thread_local.model = model
        log.info("mannequin_gate_model_loaded thread=%s model=%s", threading.get_ident(), model_path)
    return model


def _iou(a: Box, b: Box) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _covered_fraction(inner: Box, outer: Box) -> float:
    ix1, iy1, ix2, iy2 = max(inner[0], outer[0]), max(inner[1], outer[1]), min(inner[2], outer[2]), min(inner[3], outer[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return inter / area if area > 0 else 0.0


def resolve(persons: list[tuple[Box, float]], mannequins: list[tuple[Box, float]]) -> tuple[list[Box], list[Box]]:
    conflict_iou = getattr(config, "MANNEQUIN_CLASS_CONFLICT_IOU", 0.7)
    keep_p = [True] * len(persons)
    keep_m = [True] * len(mannequins)
    for i, (pb, pc) in enumerate(persons):
        for j, (mb, mc) in enumerate(mannequins):
            if _iou(pb, mb) >= conflict_iou:
                if pc >= mc:
                    keep_m[j] = False
                else:
                    keep_p[i] = False
    return ([b for (b, _), k in zip(persons, keep_p) if k], [b for (b, _), k in zip(mannequins, keep_m) if k])


def detect(frame: np.ndarray) -> tuple[list[Box], list[Box]] | None:
    if not enabled():
        return None
    try:
        model = _get_thread_model()
        names = _thread_local.names
        conf_thresh = getattr(config, "PERSON_GATE_CONF_THRESHOLD", 0.05)
        imgsz = getattr(config, "PERSON_GATE_IMAGE_SIZE", 1280)
        r = model.predict(frame, conf=conf_thresh, imgsz=imgsz, verbose=False)[0]
        persons, mannequins = [], []
        mannequin_conf = getattr(config, "MANNEQUIN_CONF_THRESHOLD", 0.35)
        if r.boxes is not None:
            for b in r.boxes:
                box, conf, cls = tuple(b.xyxy[0].tolist()), float(b.conf[0]), int(b.cls[0])
                if cls == names["person"]:
                    persons.append((box, conf))
                elif cls == names["mannequin"] and conf >= mannequin_conf:
                    mannequins.append((box, conf))
        return resolve(persons, mannequins)
    except Exception:
        log.exception("mannequin_gate_failed — falling back (fail open)")
        return None


def exclusion_regions(mannequins: list[Box], persons: list[Box]) -> list[Box]:
    overlap_thresh = getattr(config, "MANNEQUIN_PERSON_OVERLAP", 0.3)
    return [m for m in mannequins
            if not any(_covered_fraction(m, p) >= overlap_thresh for p in persons)]


def mask_regions(frame: np.ndarray, regions: list[Box]) -> np.ndarray:
    if not regions:
        return frame
    out = frame.copy()
    fill = tuple(int(v) for v in frame.reshape(-1, frame.shape[-1]).mean(axis=0))
    h, w = frame.shape[:2]
    pad = getattr(config, "MANNEQUIN_MASK_PAD_PX", 4)
    for x1, y1, x2, y2 in regions:
        out[max(0, int(y1) - pad):min(h, int(y2) + pad), max(0, int(x1) - pad):min(w, int(x2) + pad)] = fill
    return out


def drop_in_regions(detections: list[dict], regions: list[Box], frame_w: int, frame_h: int) -> list[dict]:
    if not regions:
        return detections
    px = [(x1 / frame_w, y1 / frame_h, x2 / frame_w, y2 / frame_h) for x1, y1, x2, y2 in regions]
    kept = []
    for d in detections:
        bx1, by1, bx2, by2 = d["box"]
        cx, cy = (bx1 + bx2) / 2, (by1 + by2) / 2
        if not any(x1 <= cx <= x2 and y1 <= cy <= y2 for x1, y1, x2, y2 in px):
            kept.append(d)
    return kept
