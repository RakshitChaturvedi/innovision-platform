"""
Lightweight person-presence gate — ported natively for Innovision UC3.
Runs fast person detection using YOLO class 0 before running heavy model.
"""

from __future__ import annotations

import logging
import threading

import numpy as np
from ultralytics import YOLO

import services.uc3.src.ppe_config as config

log = logging.getLogger("uc3_person_gate")

_COCO_PERSON_CLASS = 0
Box = tuple[float, float, float, float]

_thread_local = threading.local()

def _get_thread_model() -> YOLO:
    model = getattr(_thread_local, "model", None)
    if model is None:
        model = YOLO(config.PERSON_GATE_MODEL)
        warmup = np.zeros((config.PERSON_GATE_IMAGE_SIZE, config.PERSON_GATE_IMAGE_SIZE, 3), dtype=np.uint8)
        model.predict(warmup, classes=[_COCO_PERSON_CLASS], imgsz=config.PERSON_GATE_IMAGE_SIZE, verbose=False)
        _thread_local.model = model
        log.info("person_gate_model_loaded thread=%s model=%s", threading.get_ident(), config.PERSON_GATE_MODEL)
    return model

def detect_persons(frame: np.ndarray) -> list[Box] | None:
    try:
        model = _get_thread_model()
        result = model.predict(
            frame,
            classes=[_COCO_PERSON_CLASS],
            conf=config.PERSON_GATE_CONF_THRESHOLD,
            imgsz=config.PERSON_GATE_IMAGE_SIZE,
            verbose=False,
        )[0]
        if result.boxes is None:
            return []
        return [tuple(box.xyxy[0].tolist()) for box in result.boxes]
    except Exception:
        log.exception("person_gate_failed — defaulting to detect_persons=None (fail open)")
        return None

def has_person(frame: np.ndarray) -> bool:
    boxes = detect_persons(frame)
    return boxes is None or len(boxes) > 0
