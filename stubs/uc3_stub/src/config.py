"""
UC3 Backend configuration — all values overridable via environment variables.
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


# ── Platform Integration ───────────────────────────────────────────────────────
REDIS_HOST: str = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT: int = _int("REDIS_PORT", 6379)
REDIS_URL: str = os.environ.get("REDIS_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}")

CAMERA_REGISTRY_URL: str = os.environ.get("CAMERA_REGISTRY_URL", "http://camera_registry:8011")
TEST_CAMERA_ID: str = os.environ.get("TEST_CAMERA_ID", "00000000-0000-0000-0000-000000000003")

REDIS_CONSUMER_GROUP: str = os.environ.get("REDIS_CONSUMER_GROUP", "uc3_compliance_group")
REDIS_CONSUMER_NAME: str = os.environ.get("REDIS_CONSUMER_NAME", "uc3_worker_1")
UC_ID: str = os.environ.get("UC_ID", "uc3")

# ── Inference ──────────────────────────────────────────────────────────────────
CONF_THRESHOLD: float = _float("PPE_CONF_THRESHOLD", 0.35)
IOU_THRESHOLD: float = _float("PPE_IOU_THRESHOLD", 0.45)
IMAGE_SIZE: int = _int("PPE_IMAGE_SIZE", 640)
OVERLAP_THRESHOLD: float = _float("PPE_OVERLAP_THRESHOLD", 0.10)

# Adaptive per-PPE overlap thresholds
PPE_OVERLAP: dict[str, float] = {
    "helmet": _float("PPE_OV_HELMET", 0.05),
    "hard-hat": _float("PPE_OV_HARDHAT", 0.05),
    "hardhat": _float("PPE_OV_HARDHAT", 0.05),
    "gloves": _float("PPE_OV_GLOVES", 0.05),
    "glove": _float("PPE_OV_GLOVES", 0.05),
    "boots": _float("PPE_OV_BOOTS", 0.05),
    "boot": _float("PPE_OV_BOOTS", 0.05),
    "shoes": _float("PPE_OV_SHOES", 0.05),
    "glasses": _float("PPE_OV_GLASSES", 0.03),
    "goggles": _float("PPE_OV_GLASSES", 0.03),
    "safety-glasses": _float("PPE_OV_GLASSES", 0.03),
    "mask": _float("PPE_OV_MASK", 0.08),
    "face-mask": _float("PPE_OV_MASK", 0.08),
    "face_mask": _float("PPE_OV_MASK", 0.08),
    "face-guard": _float("PPE_OV_FACE_GUARD", 0.08),
    "face_guard": _float("PPE_OV_FACE_GUARD", 0.08),
    "face-shield": _float("PPE_OV_FACE_GUARD", 0.08),
    "face_shield": _float("PPE_OV_FACE_GUARD", 0.08),
    "safety-vest": _float("PPE_OV_VEST", 0.15),
    "safety_vest": _float("PPE_OV_VEST", 0.15),
    "vest": _float("PPE_OV_VEST", 0.15),
    "medical-suit": _float("PPE_OV_SUIT", 0.15),
    "medical_suit": _float("PPE_OV_SUIT", 0.15),
    "safety-suit": _float("PPE_OV_SUIT", 0.15),
    "safety_suit": _float("PPE_OV_SUIT", 0.15),
}

# Hybrid association weights
ASSOC_W_DIST: float = _float("PPE_ASSOC_W_DIST", 0.50)
ASSOC_W_IOU: float = _float("PPE_ASSOC_W_IOU", 0.30)
ASSOC_W_VPOS: float = _float("PPE_ASSOC_W_VPOS", 0.20)

# Temporal smoothing — duration-based sliding window
VIOLATION_WINDOW_SECONDS: float = _float("PPE_VIOLATION_WINDOW_SECONDS", 3.0)
VIOLATION_RAISE_FRACTION: float = _float("PPE_VIOLATION_RAISE_FRACTION", 0.60)
VIOLATION_CLEAR_FRACTION: float = _float("PPE_VIOLATION_CLEAR_FRACTION", 0.30)
MIN_EVIDENCE_SECONDS: float = _float("PPE_MIN_EVIDENCE_SECONDS", 1.0)
MIN_EVIDENCE_SAMPLES: int = _int("PPE_MIN_EVIDENCE_SAMPLES", 2)
MAX_SAMPLE_GAP_SECONDS: float = _float("PPE_MAX_SAMPLE_GAP_SECONDS", 2.0)

# False-positive filters
MIN_BODY_PART_AREA: float = _float("PPE_MIN_BODY_PART_AREA", 0.001)
DEBUG_ASSOCIATION: bool = _bool("PPE_DEBUG_ASSOCIATION", False)

# Presence Cascade
PERSON_GATE_ENABLED: bool = _bool("PPE_PERSON_GATE_ENABLED", True)
PERSON_GATE_CONF_THRESHOLD: float = _float("PPE_PERSON_GATE_CONF_THRESHOLD", 0.05)
PERSON_GATE_IMAGE_SIZE: int = _int("PPE_PERSON_GATE_IMAGE_SIZE", 1280)

MOTION_GATE_ENABLED: bool = _bool("PPE_MOTION_GATE_ENABLED", True)
MOTION_PREGATE_ENABLED: bool = _bool("PPE_MOTION_PREGATE", True)
MOTION_GLOBAL_MIN_FRACTION: float = _float("PPE_MOTION_GLOBAL_MIN_FRACTION", 0.001)
MOTION_GATE_METHOD: str = os.environ.get("PPE_MOTION_GATE_METHOD", "diff")
MOTION_DIFF_THRESHOLD: int = _int("PPE_MOTION_DIFF_THRESHOLD", 20)

MANNEQUIN_GATE_ENABLED: bool = _bool("PPE_MANNEQUIN_GATE_ENABLED", True)
MANNEQUIN_CONF_THRESHOLD: float = _float("PPE_MANNEQUIN_CONF_THRESHOLD", 0.35)

# Model paths
BASE_DIR = Path(__file__).parent.parent
MODEL_PATH = BASE_DIR / "models" / "best.pt"
PERSON_GATE_MODEL_PATH = BASE_DIR / "models" / "yolo11n.pt"
MANNEQUIN_MODEL_PATH = BASE_DIR / "models" / "person_mannequin.pt"
TRACKER_CONFIG_PATH = BASE_DIR / "models" / "tracker_config.yaml"
