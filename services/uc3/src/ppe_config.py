"""
UC3 Backend configuration — all values overridable via environment variables.
Ported natively from standalone PPE_DETECTION backend.
"""

from __future__ import annotations

import os
from pathlib import Path

def _float(key: str, default: float) -> float:
    return float(os.environ.get(key, default))

def _int(key: str, default: int) -> int:
    return int(os.environ.get(key, default))

def _bool(key: str, default: bool) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return v.lower() in ("1", "true", "yes")

# ── Inference ──────────────────────────────────────────────────────────────────
CONF_THRESHOLD: float = _float("PPE_CONF_THRESHOLD", 0.35)
IOU_THRESHOLD:  float = _float("PPE_IOU_THRESHOLD",  0.45)
IMAGE_SIZE:     int   = _int("PPE_IMAGE_SIZE",        640)

# Model paths
MODEL_PATH: str = os.environ.get("PPE_MODEL_PATH", "/app/services/uc3/models/best.pt")
TRACKER_CONFIG_PATH: str = os.environ.get("PPE_TRACKER_CONFIG", "/app/services/uc3/src/tracker_config.yaml")

# ── Gate Models ────────────────────────────────────────────────────────────────
PERSON_GATE_MODEL: str = os.environ.get("PPE_PERSON_GATE_MODEL", "yolo11n.pt")
PERSON_GATE_CONF_THRESHOLD: float = _float("PPE_PERSON_GATE_CONF", 0.25)
PERSON_GATE_IMAGE_SIZE: int = _int("PPE_PERSON_GATE_IMAGE_SIZE", 320)

PERSON_MANNEQUIN_MODEL: str = os.environ.get("PPE_MANNEQUIN_MODEL", "")
MANNEQUIN_CONF_THRESHOLD: float = _float("PPE_MANNEQUIN_CONF", 0.30)
MANNEQUIN_CLASS_CONFLICT_IOU: float = _float("PPE_MANNEQUIN_CONFLICT_IOU", 0.50)
MANNEQUIN_PERSON_OVERLAP: float = _float("PPE_MANNEQUIN_PERSON_OVERLAP", 0.40)
MANNEQUIN_MASK_PAD_PX: int = _int("PPE_MANNEQUIN_MASK_PAD_PX", 4)

# ── Motion Gate ────────────────────────────────────────────────────────────────
MOTION_GATE_ENABLED: bool = _bool("PPE_MOTION_GATE_ENABLED", True)
MOTION_GATE_METHOD: str = os.environ.get("PPE_MOTION_GATE_METHOD", "diff").lower()
MOTION_GATE_DIFF_THRESHOLD: float = _float("PPE_MOTION_DIFF_THRESHOLD", 15.0)
MOTION_GATE_MIN_CHANGED_PIXELS: int = _int("PPE_MOTION_MIN_PIXELS", 50)
MOTION_GATE_FORCE_INTERVAL_SECONDS: float = _float("PPE_MOTION_FORCE_INTERVAL", 2.0)
MOTION_GATE_MIN_PERSON_MOTION_PIXELS: int = _int("PPE_MOTION_MIN_PERSON_PIXELS", 15)

# ── Compliance — global overlap threshold (legacy / fallback) ─────────────────
OVERLAP_THRESHOLD: float = _float("PPE_OVERLAP_THRESHOLD", 0.10)

# ── Compliance — adaptive per-PPE overlap thresholds ──────────────────────────
PPE_OVERLAP: dict[str, float] = {
    "helmet":       _float("PPE_OV_HELMET",       0.05),
    "hard-hat":     _float("PPE_OV_HARDHAT",      0.05),
    "hardhat":      _float("PPE_OV_HARDHAT",      0.05),
    "gloves":       _float("PPE_OV_GLOVES",       0.05),
    "glove":        _float("PPE_OV_GLOVES",       0.05),
    "boots":        _float("PPE_OV_BOOTS",        0.05),
    "boot":         _float("PPE_OV_BOOTS",        0.05),
    "shoes":        _float("PPE_OV_SHOES",        0.05),
    "glasses":      _float("PPE_OV_GLASSES",      0.03),
    "goggles":      _float("PPE_OV_GLASSES",      0.03),
    "safety-glasses": _float("PPE_OV_GLASSES",    0.03),
    "mask":         _float("PPE_OV_MASK",         0.08),
    "face-mask":    _float("PPE_OV_MASK",         0.08),
    "face_mask":    _float("PPE_OV_MASK",         0.08),
    "face-guard":   _float("PPE_OV_FACE_GUARD",   0.08),
    "face_guard":   _float("PPE_OV_FACE_GUARD",   0.08),
    "face-shield":  _float("PPE_OV_FACE_GUARD",   0.08),
    "face_shield":  _float("PPE_OV_FACE_GUARD",   0.08),
    "safety-vest":  _float("PPE_OV_VEST",         0.15),
    "safety_vest":  _float("PPE_OV_VEST",         0.15),
    "vest":         _float("PPE_OV_VEST",         0.15),
    "medical-suit": _float("PPE_OV_SUIT",         0.15),
    "medical_suit": _float("PPE_OV_SUIT",         0.15),
    "safety-suit":  _float("PPE_OV_SUIT",         0.15),
    "safety_suit":  _float("PPE_OV_SUIT",         0.15),
}

# ── Hybrid association weights ─────────────────────────────────────────────────
ASSOC_W_DIST: float = _float("PPE_ASSOC_W_DIST", 0.50)
ASSOC_W_IOU:  float = _float("PPE_ASSOC_W_IOU",  0.30)
ASSOC_W_VPOS: float = _float("PPE_ASSOC_W_VPOS", 0.20)

# ── Temporal smoothing — duration-based ────────────────────────────────────────
VIOLATION_WINDOW_SECONDS: float = _float("PPE_VIOLATION_WINDOW_SECONDS", 2.0)
VIOLATION_RAISE_FRACTION: float = _float("PPE_VIOLATION_RAISE_FRACTION", 0.6)
VIOLATION_CLEAR_FRACTION: float = _float("PPE_VIOLATION_CLEAR_FRACTION", 0.3)
MIN_EVIDENCE_SECONDS: float = _float("PPE_MIN_EVIDENCE_SECONDS", 0.5)
MIN_EVIDENCE_SAMPLES: int = _int("PPE_MIN_EVIDENCE_SAMPLES", 2)
MAX_SAMPLE_GAP_SECONDS: float = _float("PPE_MAX_SAMPLE_GAP_SECONDS", 2.0)

GHOST_GRACE_SECONDS: float = _float("PPE_GHOST_GRACE_SECONDS", 2.0)
GHOST_SUPPRESS_IOU: float = _float("PPE_GHOST_SUPPRESS_IOU", 0.3)

MIN_BODY_PART_AREA: float = _float("PPE_MIN_BODY_PART_AREA", 0.001)
DEBUG_ASSOCIATION: bool = _bool("PPE_DEBUG_ASSOCIATION", False)
