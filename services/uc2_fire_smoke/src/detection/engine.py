"""
Stage 1 — YOLO26m Inference Engine.

Loads the fire/smoke YOLO weights, performs warm-up inference,
and returns raw bounding-box candidates with class probabilities.
Supports FP16 half-precision on CUDA and letterbox-preserving resize.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from services.uc2_fire_smoke.src.config import settings

logger = logging.getLogger("uc2.detection.engine")


class YOLOEngine:
    """Stage 1 YOLO26m inference engine for fire & smoke detection."""

    CLASS_MAP = {
        "fire": "fire", "flame": "fire", "0": "fire",
        "smoke": "smoke", "1": "smoke",
        "sparks": "sparks", "spark": "sparks", "2": "sparks",
    }

    def __init__(self) -> None:
        self.model: YOLO | None = None
        self.class_names: Dict[int, str] = {}
        self.device: str = "cpu"
        self.ready: bool = False
        self._load()

    # ── Model lifecycle ───────────────────────────────────────────────────────

    def _resolve_path(self, raw: str) -> str:
        """Search common roots for model weights."""
        candidates = [
            raw,
            os.path.join(os.path.dirname(__file__), "..", "..", raw),
            os.path.join(os.path.dirname(__file__), "..", "..", "..", raw),
            os.path.join("/app", raw),
        ]
        for c in candidates:
            p = os.path.normpath(c)
            if os.path.exists(p):
                return p
        return raw

    def _load(self) -> None:
        path = self._resolve_path(settings.yolo_model_path)
        logger.info("yolo_loading model_path=%s device=%s", path, settings.device)

        if not os.path.exists(path):
            logger.error("yolo_model_not_found path=%s", path)
            return

        try:
            self.device = "cuda" if (torch.cuda.is_available() and settings.device == "cuda") else "cpu"
            self.model = YOLO(path, task="detect")
            self.model.to(self.device)
            self.class_names = self.model.names or {}
            self.ready = True
            logger.info(
                "yolo_loaded device=%s classes=%s half=%s",
                self.device, self.class_names, settings.half_precision,
            )
            self._warmup()
        except Exception as exc:
            logger.error("yolo_load_failed error=%s", exc, exc_info=True)
            self.ready = False

    def _warmup(self) -> None:
        """Run a dummy frame through the model to initialise CUDA kernels."""
        if not self.model:
            return
        try:
            dummy = np.zeros((settings.inference_size, settings.inference_size, 3), dtype=np.uint8)
            self.model(
                dummy, verbose=False,
                conf=settings.conf_threshold,
                device=self.device,
            )
            logger.info("yolo_warmup_complete")
        except Exception as exc:
            logger.warning("yolo_warmup_failed error=%s", exc)

    # ── Inference ─────────────────────────────────────────────────────────────

    def _map_class(self, raw_name: str) -> str | None:
        low = raw_name.lower().strip()
        for keyword, mapped in self.CLASS_MAP.items():
            if keyword in low:
                return mapped
        return None

    def infer(
        self,
        frame: np.ndarray,
        conf_override: float | None = None,
        iou_override: float | None = None,
    ) -> tuple[List[Dict[str, Any]], float]:
        """
        Run YOLO26m on a BGR frame.

        Returns
        -------
        (detections, latency_ms)
          detections — list of {detection_type, confidence, bbox, raw_class_name, class_id}
          latency_ms — inference wall-clock time
        """
        if not self.ready or self.model is None:
            return [], 0.0

        conf = conf_override or settings.conf_threshold
        iou = iou_override or settings.iou_threshold

        t0 = time.perf_counter()
        results = self.model(
            frame,
            imgsz=settings.inference_size,
            verbose=False,
            conf=conf,
            iou=iou,
            device=self.device,
            half=(self.device == "cuda" and settings.half_precision),
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0

        detections: List[Dict[str, Any]] = []
        for r in results:
            if r.boxes is None or len(r.boxes) == 0:
                continue
            for box in r.boxes:
                cls_id = int(box.cls[0])
                raw_name = self.class_names.get(cls_id, str(cls_id))
                mapped = self._map_class(raw_name)
                if mapped is None:
                    continue

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                detections.append({
                    "detection_type": mapped,
                    "confidence": round(float(box.conf[0]), 4),
                    "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "raw_class_name": raw_name,
                    "class_id": cls_id,
                })

        return detections, latency_ms

    def get_model_info(self) -> dict:
        return {
            "model_version": settings.model_version,
            "model_path": settings.yolo_model_path,
            "device": self.device,
            "inference_size": settings.inference_size,
            "half_precision": settings.half_precision,
            "ready": self.ready,
            "classes": dict(self.class_names),
        }
