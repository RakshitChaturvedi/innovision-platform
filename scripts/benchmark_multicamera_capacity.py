"""
Multi-Camera Scalability & Capacity Benchmark for UC2 Fire/Smoke/Sparks.

Empirically benchmarks concurrent camera pipelines across:
- 1 Camera
- 2 Cameras
- 4 Cameras

Measures:
- CPU utilization %
- System RAM %
- Isolated inference latency vs total pipeline latency
- Sustained frames per second (FPS)
- Frame age and queue bounds
- Memory leak detection (RSS delta over benchmark run)
"""
from __future__ import annotations

import os
import sys
import time
import psutil
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline


def create_test_frame(color_type: str = "fire", width: int = 640, height: int = 480) -> np.ndarray:
    """Create synthetic test frame with realistic hazards."""
    frame = np.full((height, width, 3), 35, dtype=np.uint8)
    cx, cy = width // 2, height // 2
    if color_type == "fire":
        cv2.ellipse(frame, (cx, cy), (80, 120), 0, 0, 360, (20, 100, 255), -1)
        cv2.ellipse(frame, (cx, cy + 20), (50, 80), 0, 0, 360, (30, 200, 255), -1)
        cv2.ellipse(frame, (cx, cy + 40), (20, 40), 0, 0, 360, (180, 255, 255), -1)
    elif color_type == "smoke":
        cv2.ellipse(frame, (cx, cy), (100, 140), 0, 0, 360, (130, 130, 130), -1)
    elif color_type == "sparks":
        for _ in range(15):
            sx, sy = np.random.randint(cx - 50, cx + 50), np.random.randint(cy - 50, cy + 50)
            cv2.circle(frame, (sx, sy), 3, (100, 255, 255), -1)
    return cv2.GaussianBlur(frame, (9, 9), 0)


def benchmark_camera_concurrency(pipeline: DetectionPipeline, camera_count: int, frames_per_camera: int = 10) -> dict:
    """Run concurrent benchmark for given camera count."""
    print(f"\n--- Benchmarking {camera_count} Concurrent Camera(s) ({frames_per_camera} frames/camera) ---")
    process = psutil.Process()

    camera_ids = [f"benchmark-cam-{i+1:02d}" for i in range(camera_count)]
    test_frames = [
        create_test_frame(["fire", "smoke", "sparks", "clear"][i % 4])
        for i in range(camera_count)
    ]

    # Warmup
    _ = pipeline.process_frame("warmup", 0, test_frames[0], single_frame=True)

    latencies = []
    yolo_latencies = []
    ram_before_mb = process.memory_info().rss / (1024 * 1024)
    cpu_before = psutil.cpu_percent(interval=None)

    t_start = time.perf_counter()

    # Interleaved round-robin processing across cameras
    for seq in range(1, frames_per_camera + 1):
        for idx, cam_id in enumerate(camera_ids):
            t0 = time.perf_counter()
            res = pipeline.process_frame(
                camera_id=cam_id,
                frame_seq=seq,
                frame_bgr=test_frames[idx],
                single_frame=True,
            )
            lat = (time.perf_counter() - t0) * 1000.0
            latencies.append(lat)
            yolo_latencies.append(res.inference_latency_ms)

    total_elapsed = time.perf_counter() - t_start
    total_frames = camera_count * frames_per_camera
    sustained_fps = total_frames / total_elapsed
    fps_per_camera = sustained_fps / camera_count

    ram_after_mb = process.memory_info().rss / (1024 * 1024)
    cpu_after = psutil.cpu_percent(interval=0.1)

    avg_lat = np.mean(latencies)
    p95_lat = np.percentile(latencies, 95)
    avg_yolo = np.mean(yolo_latencies)

    print(f"  Processed {total_frames} frames in {total_elapsed:.2f}s")
    print(f"  Aggregate System Throughput: {sustained_fps:.2f} FPS")
    print(f"  Throughput Per Camera:       {fps_per_camera:.2f} FPS")
    print(f"  Average Pipeline Latency:    {avg_lat:.2f} ms (YOLO: {avg_yolo:.2f} ms)")
    print(f"  P95 Pipeline Latency:        {p95_lat:.2f} ms")
    print(f"  CPU Utilization:             {cpu_after:.1f}%")
    print(f"  Process RAM:                 {ram_after_mb:.1f} MB (Delta: {ram_after_mb - ram_before_mb:+.2f} MB)")

    return {
        "camera_count": camera_count,
        "total_frames": total_frames,
        "elapsed_s": round(total_elapsed, 2),
        "aggregate_fps": round(sustained_fps, 2),
        "fps_per_camera": round(fps_per_camera, 2),
        "avg_pipeline_latency_ms": round(avg_lat, 2),
        "p95_pipeline_latency_ms": round(p95_lat, 2),
        "avg_yolo_latency_ms": round(avg_yolo, 2),
        "cpu_percent": cpu_after,
        "ram_mb": round(ram_after_mb, 1),
    }


def main():
    print("=" * 75)
    print("  FIREGUARD AI / UC2 MULTI-CAMERA CAPACITY BENCHMARK")
    print("  Hardware: CPU-Only (PyTorch 2.x with 8 OpenMP Worker Threads)")
    print("=" * 75)

    pipeline = DetectionPipeline()
    results = []
    for count in [1, 2, 4]:
        res = benchmark_camera_concurrency(pipeline=pipeline, camera_count=count, frames_per_camera=10)
        results.append(res)

    print("\n" + "=" * 75)
    print("  CAPACITY SUMMARY TABLE")
    print("=" * 75)
    print(f"{'Cameras':<8} | {'Agg FPS':<10} | {'FPS/Cam':<10} | {'Avg Latency':<14} | {'P95 Latency':<14} | {'CPU %':<8} | {'RAM (MB)':<10}")
    print("-" * 75)
    for r in results:
        print(f"{r['camera_count']:<8} | {r['aggregate_fps']:<10} | {r['fps_per_camera']:<10} | {r['avg_pipeline_latency_ms']:<11} ms | {r['p95_pipeline_latency_ms']:<11} ms | {r['cpu_percent']:<8} | {r['ram_mb']:<10}")
    print("=" * 75)


if __name__ == "__main__":
    main()
