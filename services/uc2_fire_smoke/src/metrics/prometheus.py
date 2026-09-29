"""
Prometheus Metrics Instrumentation for UC2 Fire & Smoke Analytics Service.
"""
from __future__ import annotations

import logging
from typing import Optional

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger("innovision.uc2.metrics")

# Shared registry
REGISTRY = CollectorRegistry()

# ── Counters ──────────────────────────────────────────────────────────────────
FRAMES_PROCESSED = Counter(
    "uc2_frames_processed_total",
    "Total frames processed by UC2 pipeline",
    ["camera_id"],
    registry=REGISTRY,
)

ALERTS_GENERATED = Counter(
    "uc2_alerts_generated_total",
    "Total AlertEvents published to alerts:live",
    ["camera_id", "severity", "alert_type"],
    registry=REGISTRY,
)

FIRE_DETECTIONS = Counter(
    "uc2_fire_detections_total",
    "Total confirmed fire detections",
    ["camera_id", "zone_id"],
    registry=REGISTRY,
)

SMOKE_DETECTIONS = Counter(
    "uc2_smoke_detections_total",
    "Total confirmed smoke detections",
    ["camera_id", "zone_id"],
    registry=REGISTRY,
)

FALSE_ALARMS = Counter(
    "uc2_false_alarms_total",
    "Total candidate detections suppressed by false alarm engine",
    ["camera_id", "reason", "detection_type"],
    registry=REGISTRY,
)

DROPPED_FRAMES = Counter(
    "uc2_dropped_frames_total",
    "Total frames dropped due to queue full or decoding failure",
    ["camera_id"],
    registry=REGISTRY,
)

OFFLINE_CAMERAS = Counter(
    "uc2_offline_cameras_total",
    "Count of camera offline events encountered",
    ["camera_id"],
    registry=REGISTRY,
)

# ── Histograms ────────────────────────────────────────────────────────────────
INFERENCE_LATENCY = Histogram(
    "uc2_inference_latency_seconds",
    "YOLO inference wall-clock latency per frame in seconds",
    ["camera_id"],
    buckets=[0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0],
    registry=REGISTRY,
)

VERIFICATION_LATENCY = Histogram(
    "uc2_verification_latency_seconds",
    "Deterministic verification latency per frame in seconds",
    ["camera_id"],
    buckets=[0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2],
    registry=REGISTRY,
)

E2E_LATENCY = Histogram(
    "uc2_e2e_latency_seconds",
    "End-to-end frame receipt to alert publication latency in seconds",
    ["camera_id"],
    buckets=[0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0],
    registry=REGISTRY,
)

# ── Gauges ────────────────────────────────────────────────────────────────────
CAMERA_FPS = Gauge(
    "uc2_camera_fps",
    "Current processing frame rate for camera",
    ["camera_id"],
    registry=REGISTRY,
)

ACTIVE_WORKERS = Gauge(
    "uc2_active_workers",
    "Number of active camera workers running in UC2",
    registry=REGISTRY,
)

QUEUE_SIZE = Gauge(
    "uc2_queue_size",
    "Current depth of processing queue",
    ["camera_id"],
    registry=REGISTRY,
)

STREAM_LAG = Gauge(
    "uc2_stream_lag",
    "Estimated message lag behind ingestion stream",
    ["camera_id"],
    registry=REGISTRY,
)

HEALTH_STATUS = Gauge(
    "uc2_health_status",
    "Binary health status (1 = healthy, 0 = degraded/unhealthy)",
    registry=REGISTRY,
)


def get_latest_metrics() -> tuple[bytes, str]:
    """Generate Prometheus metric payload and content-type."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
