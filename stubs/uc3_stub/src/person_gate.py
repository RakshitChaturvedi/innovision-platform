"""
Lightweight person-presence gate — runs before the main PPE model so a
frame with nobody in it never pays for a full model call.
"""

from __future__ import annotations

import logging
import threading

import numpy as np
from ultralytics import YOLO

from stubs.uc3_stub.src import config

log = logging.getLogger("uc3.person_gate")

_COCO_PERSON_CLASS = 0

Box = tuple[float, float, float, float]

_thread_local = threading.local()


def _get_thread_model() -> YOLO:
    model = getattr(_thread_local, "model", None)
    if model is None:
        model_path = str(config.PERSON_GATE_MODEL_PATH)
        model = YOLO(model_path)
        warmup = np.zeros((config.PERSON_GATE_IMAGE_SIZE, config.PERSON_GATE_IMAGE_SIZE, 3), dtype=np.uint8)
        model.predict(warmup, classes=[_COCO_PERSON_CLASS], imgsz=config.PERSON_GATE_IMAGE_SIZE, verbose=False)
        _thread_local.model = model
        log.info("person_gate_model_loaded thread=%s model=%s", threading.get_ident(), model_path)
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
