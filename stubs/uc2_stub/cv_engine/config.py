"""
UC2 Fire & Smoke Analytics — Localised Configuration.

Self-contained settings previously in services/uc2_fire_smoke/src/config.py.
All tunables loaded from environment variables with production defaults.
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FireHSVConfig(BaseSettings):
    """HSV colour-range thresholds for deterministic fire verification."""
    model_config = SettingsConfigDict(env_prefix="UC2_FIRE_HSV_", extra="ignore")

    hsv_ranges: list = Field(
        default=[
            ((0, 30, 50), (25, 255, 255)),
            ((150, 30, 50), (180, 255, 255)),
            ((25, 30, 50), (45, 255, 255)),
        ],
        description="HSV lower/upper bound pairs for fire colour masking",
    )
    min_pixel_ratio: float = Field(0.01, description="Min ratio of fire pixels in ROI")
    min_brightness: float = Field(60.0, description="Min avg V of fire pixels")
    min_saturation: float = Field(60.0, description="Min avg S of fire pixels")
    min_component_size: int = Field(2, description="Min connected-component area (px)")


class SmokeHSVConfig(BaseSettings):
    """Texture / colour thresholds for deterministic smoke verification."""
    model_config = SettingsConfigDict(env_prefix="UC2_SMOKE_HSV_", extra="ignore")

    max_saturation: float = Field(130.0)
    min_brightness: float = Field(30.0)
    max_chroma: float = Field(60.0)
    min_texture_std: float = Field(2.0)
    max_texture_std: float = Field(80.0)
    max_edge_density: float = Field(0.20)
    min_entropy: float = Field(1.5)
    max_entropy: float = Field(8.0)
    max_contrast: float = Field(80.0)
    max_laplacian_var: float = Field(500.0)
    min_laplacian_var: float = Field(0.5)
    max_gradient_mag: float = Field(40.0)
    min_gradient_mag: float = Field(0.3)


class FusionWeights(BaseSettings):
    """Configurable weights for Stage 5 confidence fusion."""
    model_config = SettingsConfigDict(env_prefix="UC2_FUSION_", extra="ignore")

    yolo: float = Field(0.45, alias="UC2_FUSION_YOLO")
    hsv: float = Field(0.15, alias="UC2_FUSION_HSV")
    texture: float = Field(0.15, alias="UC2_FUSION_TEXTURE")
    temporal: float = Field(0.15, alias="UC2_FUSION_TEMPORAL")
    motion: float = Field(0.10, alias="UC2_FUSION_MOTION")


class UC2Config(BaseSettings):
    """Master configuration for the UC2 Fire & Smoke Analytics Service."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    # ── Service Identity ──────────────────────────────────────────────────────
    service_name: str = Field("uc2_fire_smoke", alias="UC2_SERVICE_NAME")
    service_port: int = Field(8022, alias="UC2_PORT")
    pipeline_version: str = Field("2.0.0", alias="UC2_PIPELINE_VERSION")

    # ── Model ─────────────────────────────────────────────────────────────────
    yolo_model_path: str = Field("models/best.pt", alias="UC2_YOLO_MODEL_PATH")
    model_version: str = Field("fireguard-v8m-1.2", alias="UC2_MODEL_VERSION")
    model_name: str = Field("YOLO26m Fire/Smoke/Sparks Detector", alias="UC2_MODEL_NAME")
    expected_model_checksum: str = Field(
        "227db351bf5bdeb27b86f2256d4a9b340042ea63fd0e92b0dea6734b99c482c1",
        alias="UC2_EXPECTED_MODEL_CHECKSUM",
    )
    validate_checksum: bool = Field(True, alias="UC2_VALIDATE_CHECKSUM")
    device: str = Field("auto", alias="UC2_DEVICE")
    half_precision: bool = Field(False, alias="UC2_HALF_PRECISION")
    inference_size: int = Field(640, alias="UC2_INFERENCE_SIZE")
    conf_threshold: float = Field(0.20, alias="UC2_CONF_THRESHOLD")
    iou_threshold: float = Field(0.45, alias="UC2_IOU_THRESHOLD")

    # ── Camera Health & Diagnostics ───────────────────────────────────────────
    camera_stale_threshold_s: float = Field(15.0, alias="UC2_CAMERA_STALE_THRESHOLD_S")
    camera_degraded_threshold_s: float = Field(3.0, alias="UC2_CAMERA_DEGRADED_THRESHOLD_S")
    evidence_buffer_size: int = Field(5, alias="UC2_EVIDENCE_BUFFER_SIZE")

    # ── Detection Mode ────────────────────────────────────────────────────────
    detection_mode: str = Field("BALANCED", alias="UC2_DETECTION_MODE")

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_host: str = Field("redis", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    stream_consumer_group: str = Field("uc2_group", alias="UC2_STREAM_GROUP")
    stream_consumer_name: str = Field("uc2_worker_1", alias="UC2_STREAM_CONSUMER")
    stream_batch_size: int = Field(5, alias="UC2_STREAM_BATCH_SIZE")
    stream_block_ms: int = Field(2000, alias="UC2_STREAM_BLOCK_MS")

    # ── Camera ────────────────────────────────────────────────────────────────
    camera_registry_url: str = Field(
        "http://camera_registry:8011", alias="CAMERA_REGISTRY_URL"
    )
    camera_refresh_interval_s: int = Field(60, alias="UC2_CAMERA_REFRESH_S")
    max_cameras: int = Field(32, alias="UC2_MAX_CAMERAS")
    target_fps: float = Field(10.0, alias="UC2_TARGET_FPS")
    heartbeat_interval_s: int = Field(5, alias="UC2_HEARTBEAT_S")

    # ── Verification ──────────────────────────────────────────────────────────
    temporal_frames: int = Field(3, alias="UC2_TEMPORAL_FRAMES")
    smoothing_alpha: float = Field(0.6, alias="UC2_SMOOTHING_ALPHA")
    alert_cooldown_s: float = Field(30.0, alias="UC2_ALERT_COOLDOWN_S")
    motion_threshold: float = Field(0.005, alias="UC2_MOTION_THRESHOLD")

    # ── Storage (MinIO) ───────────────────────────────────────────────────────
    minio_endpoint: str = Field("minio:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field("minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field("minioadmin", alias="MINIO_SECRET_KEY")
    minio_secure: bool = Field(False, alias="MINIO_SECURE")
    minio_frames_bucket: str = Field("innovision-frames", alias="UC2_FRAMES_BUCKET")
    minio_evidence_bucket: str = Field("innovision-evidence", alias="UC2_EVIDENCE_BUCKET")
    jpeg_quality: int = Field(85, alias="UC2_JPEG_QUALITY")
    database_url: Optional[str] = Field(None, alias="DATABASE_URL")

    # ── Monitoring ────────────────────────────────────────────────────────────
    prometheus_enabled: bool = Field(True, alias="UC2_PROMETHEUS_ENABLED")
    log_level: str = Field("INFO", alias="UC2_LOG_LEVEL")
    log_format: str = Field("json", alias="UC2_LOG_FORMAT")

    # ── Performance ───────────────────────────────────────────────────────────
    worker_count: int = Field(4, alias="UC2_WORKER_COUNT")
    processing_queue_size: int = Field(64, alias="UC2_QUEUE_SIZE")
    batch_inference: bool = Field(False, alias="UC2_BATCH_INFERENCE")
    frame_cache_ttl_s: int = Field(20, alias="UC2_FRAME_CACHE_TTL")

    # ── Nested Verification Configs ───────────────────────────────────────────
    fire_hsv: FireHSVConfig = Field(default_factory=FireHSVConfig)
    smoke_hsv: SmokeHSVConfig = Field(default_factory=SmokeHSVConfig)
    fusion_weights: FusionWeights = Field(default_factory=FusionWeights)


settings = UC2Config()
