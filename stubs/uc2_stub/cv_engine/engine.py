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

from stubs.uc2_stub.cv_engine.config import settings

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
        self.checksum: str = ""
        self.checksum_validated: bool = False
        self.classes_validated: bool = False
        self.load_error: str | None = None
        self.loaded_at: float | None = None
        self._load()

    # ── Model lifecycle ───────────────────────────────────────────────────────

    def _resolve_path(self, raw: str) -> str:
        """Search common roots for model weights."""
        candidates = [
            raw,
            os.path.join(os.path.dirname(__file__), raw),
            os.path.join(os.path.dirname(__file__), "..", raw),
            os.path.join("/app", raw),
            os.path.join("/app", "stubs", "uc2_stub", "cv_engine", raw),
        ]
        for c in candidates:
            p = os.path.normpath(c)
            if os.path.exists(p):
                return p
        return raw

    def _load(self) -> None:
        import hashlib
        path = self._resolve_path(settings.yolo_model_path)
        logger.info("yolo_loading model_path=%s device=%s", path, settings.device)

        if not os.path.exists(path):
            err_msg = f"YOLO model file not found at path: {path}"
            logger.error(err_msg)
            self.load_error = err_msg
            self.ready = False
            return

        try:
            # 1. Validate SHA256 model checksum
            with open(path, "rb") as mf:
                self.checksum = hashlib.sha256(mf.read()).hexdigest()

            if settings.validate_checksum and settings.expected_model_checksum:
                if self.checksum.lower() != settings.expected_model_checksum.lower():
                    err_msg = (
                        f"Model checksum mismatch! Expected {settings.expected_model_checksum}, "
                        f"found {self.checksum} on {path}"
                    )
                    logger.error(err_msg)
                    self.load_error = err_msg
                    self.ready = False
                    raise RuntimeError(err_msg)
            self.checksum_validated = True

            # 2. Hardware auto-detection
            cuda_avail = torch.cuda.is_available()
            req_dev = str(settings.device).lower()
            if req_dev == "cuda":
                if not cuda_avail:
                    err_msg = "CUDA requested via UC2_DEVICE='cuda' but torch.cuda.is_available() is False"
                    logger.error(err_msg)
                    self.load_error = err_msg
                    self.ready = False
                    raise RuntimeError(err_msg)
                self.device = "cuda"
            elif req_dev in ("auto", "gpu"):
                self.device = "cuda" if cuda_avail else "cpu"
            else:
                self.device = "cpu"

            if self.device == "cpu":
                # Tune OpenMP thread pool for optimal multi-threaded inference latency
                cpu_threads = min(8, max(2, os.cpu_count() or 4))
                torch.set_num_threads(cpu_threads)

            self.model = YOLO(path, task="detect")
            self.model.to(self.device)
            self.class_names = self.model.names or {}

            # 3. Validate class IDs: 0 = fire, 1 = smoke, 2 = sparks
            c0 = self._map_class(self.class_names.get(0, ""))
            c1 = self._map_class(self.class_names.get(1, ""))
            c2 = self._map_class(self.class_names.get(2, ""))
            if c0 != "fire" or c1 != "smoke" or c2 != "sparks":
                err_msg = (
                    f"Model classes invalid! Expected {{0: 'fire', 1: 'smoke', 2: 'sparks'}}, "
                    f"found: {self.class_names}"
                )
                logger.error(err_msg)
                self.load_error = err_msg
                self.ready = False
                raise RuntimeError(err_msg)
            self.classes_validated = True

            self.ready = True
            self.loaded_at = time.time()
            gpu_name = torch.cuda.get_device_name(0) if cuda_avail else "N/A (No CUDA GPU detected)"
            logger.info(
                "yolo_loaded device=%s cuda_avail=%s gpu_name=%s threads=%d sha256=%s classes=%s half=%s",
                self.device, cuda_avail, gpu_name, torch.get_num_threads(), self.checksum[:12], self.class_names, settings.half_precision,
            )
            self._warmup()
        except Exception as exc:
            logger.error("yolo_load_failed error=%s", exc, exc_info=True)
            self.load_error = str(exc)
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
        cuda_avail = torch.cuda.is_available()
        return {
            "model_name": settings.model_name,
            "model_version": settings.model_version,
            "model_path": settings.yolo_model_path,
            "model_checksum": self.checksum,
            "expected_checksum": settings.expected_model_checksum,
            "checksum_validated": self.checksum_validated,
            "expected_classes_validated": self.classes_validated,
            "device": self.device,
            "cuda_available": cuda_avail,
            "gpu_name": torch.cuda.get_device_name(0) if cuda_avail else "N/A (No CUDA GPU detected)",
            "pytorch_version": torch.__version__,
            "cpu_threads": torch.get_num_threads(),
            "inference_size": settings.inference_size,
            "half_precision": settings.half_precision,
            "ready": self.ready,
            "classes": dict(self.class_names),
            "load_error": self.load_error,
            "loaded_at": self.loaded_at,
        }
