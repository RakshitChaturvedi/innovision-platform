"""
Centralised configuration for the Ingestion Service.

All tunables are loaded from environment variables with sensible defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class IngestionConfig:
    """Immutable configuration object loaded once at service startup."""

    # ── PostgreSQL ────────────────────────────────────────────────────
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://innovision:changeme@localhost:5432/innovision_platform",
        )
    )

    # ── Redis ─────────────────────────────────────────────────────────
    redis_url: str = field(
        default_factory=lambda: os.environ.get("REDIS_URL", "redis://localhost:6379")
    )

    # ── MinIO ─────────────────────────────────────────────────────────
    minio_endpoint: str = field(
        default_factory=lambda: os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    )
    minio_access_key: str = field(
        default_factory=lambda: os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    )
    minio_secret_key: str = field(
        default_factory=lambda: os.environ.get("MINIO_SECRET_KEY", "changeme")
    )
    minio_secure: bool = field(
        default_factory=lambda: os.environ.get("MINIO_SECURE", "false").lower()
        == "true"
    )
    minio_bucket: str = "innovision-frames"

    # ── Pipeline Defaults ─────────────────────────────────────────────
    default_fps: int = 10
    jpeg_quality: int = 85
    heartbeat_interval_s: float = 5.0
    offline_timeout_s: float = 10.0
    backoff_base_s: float = 1.0
    backoff_max_s: float = 30.0
    stream_maxlen: int = 1000

    # ── Shake Detection ───────────────────────────────────────────────
    shake_window_size: int = 5
    shake_variance_threshold: float = 50.0

    # ── Health Server ─────────────────────────────────────────────────
    health_port: int = field(
        default_factory=lambda: int(os.environ.get("HEALTH_PORT", "8020"))
    )


def load_config() -> IngestionConfig:
    """Factory: build config from current environment."""
    return IngestionConfig()
