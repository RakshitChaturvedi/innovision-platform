"""
UC3 Person Gate — Presence gate to verify person existence before full model.
"""

from __future__ import annotations

import logging
from ultralytics import YOLO

from services.uc3_ppe_detection.src import config

logger = logging.getLogger(__name__)

_person_gate_model: YOLO | None = None


def get_person_gate_model() -> YOLO | None:
    global _person_gate_model
    if not config.PERSON_GATE_ENABLED:
        return None
    if _person_gate_model is None:
        try:
            if config.PERSON_GATE_MODEL_PATH.exists():
                _person_gate_model = YOLO(str(config.PERSON_GATE_MODEL_PATH))
                logger.info("Person gate model loaded from %s", config.PERSON_GATE_MODEL_PATH)
        except Exception as exc:
            logger.warning("Failed to load person gate model: %s", exc)
    return _person_gate_model


def has_person(frame_bgr, model: YOLO | None = None) -> bool:
    if not config.PERSON_GATE_ENABLED:
        return True
    gate_model = model or get_person_gate_model()
    if gate_model is None:
        return True

    try:
        results = gate_model.predict(
            source=frame_bgr,
            conf=config.PERSON_GATE_CONF_THRESHOLD,
            imgsz=config.PERSON_GATE_IMAGE_SIZE,
            classes=[0],  # person class in COCO
            verbose=False,
        )
        for r in results:
            if r.boxes is not None and len(r.boxes) > 0:
                return True
        return False
    except Exception as exc:
        logger.warning("Person gate execution error: %s", exc)
        return True
