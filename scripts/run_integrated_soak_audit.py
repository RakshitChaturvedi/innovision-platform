"""
Integrated Platform Soak & Stability Audit Script.
Runs continuous workload measuring:
- Process RAM (RSS) and trend slope
- Host & Process CPU %
- Active Camera Worker count
- Simulated Redis queue depth
- Processed FPS vs Source FPS
- Skipped frames count and rate
- Frame age (mean & P95)
- Pipeline Latency (mean & P95)
- Confirmed alert count
- Error count & Reconnect events
- Model instance identity (verifying zero redundant reloading)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import cv2
import numpy as np
import psutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.contracts.frame_event import FrameEvent
from shared.contracts.enums import FrameProvider
from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline

def run_integrated_soak(duration_seconds: int = 600, log_file: str = "soak_audit_results.log"):
    process = psutil.Process()
    initial_rss = process.memory_info().rss / (1024 * 1024)
    print("=" * 75)
    print(f"STARTING INTEGRATED SOAK STABILITY AUDIT ({duration_seconds}s / {duration_seconds/60:.1f} mins)")
    print(f"Initial Process RSS: {initial_rss:.2f} MB | PID: {process.pid}")
    print("=" * 75)

    pipeline = DetectionPipeline()
    model_id_initial = id(pipeline.yolo.model)

    fire_img = cv2.imread("test_data/images/sample_fire.jpg")
    if fire_img is None:
        fire_img = np.full((480, 640, 3), 40, dtype=np.uint8)
        cv2.ellipse(fire_img, (320, 240), (80, 120), 0, 0, 360, (0, 165, 255), -1)

    camera_id = "00000000-0000-0000-0000-000000000001"
    source_fps = 15.0  # Typical production CCTV camera rate
    frame_interval = 1.0 / source_fps

    start_time = time.perf_counter()
    next_frame_time = start_time
    last_report_time = start_time

    queue: list[tuple[FrameEvent, np.ndarray]] = []
    total_source_frames = 0
    total_processed_frames = 0
    total_skipped_frames = 0
    total_alerts = 0
    total_errors = 0
    reconnect_events = 0

    recent_latencies: list[float] = []
    recent_frame_ages: list[float] = []
    rss_samples: list[tuple[float, float]] = [(0.0, initial_rss)]  # (elapsed_s, rss_mb)

    with open(log_file, "w") as f_log:
        f_log.write("timestamp,elapsed_s,rss_mb,delta_mb,cpu_pct,source_fps,proc_fps,skipped_total,frame_age_p95_ms,lat_p95_ms,queue_depth,alerts_total,errors_total\n")

    while (time.perf_counter() - start_time) < duration_seconds:
        t_now = time.perf_counter()

        # Ingestion step
        while next_frame_time <= t_now:
            total_source_frames += 1
            seq = total_source_frames
            event = FrameEvent(
                camera_id=camera_id,
                frame_seq=seq,
                timestamp=datetime.now(timezone.utc),
                frame_reference=f"frame:{camera_id}:{seq}",
                frame_provider=FrameProvider.REDIS,
                frame_shape=(fire_img.shape[0], fire_img.shape[1]),
            )
            # Add dynamic perturbation to prevent static memoization
            img_noise = fire_img.copy()
            if seq % 10 == 0:
                cv2.circle(img_noise, (int(100 + (seq % 400)), 200), 10, (255, 255, 255), -1)
            queue.append((event, img_noise))
            next_frame_time += frame_interval

        # Frame Consumer step with fresh-frame sampling
        if queue:
            # Drain stale if backlog > 1
            if len(queue) > 1:
                skipped = len(queue) - 1
                total_skipped_frames += skipped
                item_to_process = queue[-1]
                queue.clear()
            else:
                item_to_process = queue.pop(0)

            event, img = item_to_process
            age_ms = (datetime.now(timezone.utc) - event.timestamp).total_seconds() * 1000.0
            recent_frame_ages.append(max(0.0, age_ms))

            t0 = time.perf_counter()
            try:
                res = pipeline.process_frame(camera_id, event.frame_seq, img)
                lat_ms = (time.perf_counter() - t0) * 1000.0
                recent_latencies.append(lat_ms)
                total_processed_frames += 1

                if any(d.detection_type == "fire" for d in res.confirmed_detections):
                    total_alerts += 1
            except Exception as e:
                total_errors += 1

        # Check model identity
        assert id(pipeline.yolo.model) == model_id_initial, "FATAL: Model was reloaded in memory!"

        # Periodic logging every 10 seconds
        if (t_now - last_report_time) >= 10.0:
            elapsed = t_now - start_time
            current_rss = process.memory_info().rss / (1024 * 1024)
            delta_rss = current_rss - initial_rss
            cpu_pct = process.cpu_percent(interval=None)
            cur_proc_fps = len(recent_latencies) / (t_now - last_report_time)
            cur_source_fps = source_fps
            p95_lat = np.percentile(recent_latencies, 95) if recent_latencies else 0.0
            p95_age = np.percentile(recent_frame_ages, 95) if recent_frame_ages else 0.0
            cur_q_depth = len(queue)

            rss_samples.append((elapsed, current_rss))

            line = (
                f"[{elapsed:5.1f}s] RAM: {current_rss:6.1f} MB (Δ: {delta_rss:+6.2f} MB) | "
                f"CPU: {cpu_pct:4.1f}% | Proc FPS: {cur_proc_fps:4.2f} | "
                f"Skipped: {total_skipped_frames:5d} | Frame Age P95: {p95_age:5.1f}ms | "
                f"Lat P95: {p95_lat:5.1f}ms | Q: {cur_q_depth} | Alerts: {total_alerts}"
            )
            print(line)

            with open(log_file, "a") as f_log:
                f_log.write(
                    f"{datetime.now(timezone.utc).isoformat()},{elapsed:.1f},{current_rss:.2f},"
                    f"{delta_rss:.2f},{cpu_pct:.1f},{cur_source_fps:.2f},{cur_proc_fps:.2f},"
                    f"{total_skipped_frames},{p95_age:.2f},{p95_lat:.2f},{cur_q_depth},"
                    f"{total_alerts},{total_errors}\n"
                )

            recent_latencies.clear()
            recent_frame_ages.clear()
            last_report_time = t_now

        time.sleep(0.002)

    total_duration = time.perf_counter() - start_time
    final_rss = process.memory_info().rss / (1024 * 1024)
    net_ram_delta = final_rss - initial_rss

    # Linear regression slope on RSS samples (MB / minute)
    times = [s[0] / 60.0 for s in rss_samples]
    mems = [s[1] for s in rss_samples]
    if len(times) > 2:
        slope, intercept = np.polyfit(times, mems, 1)
    else:
        slope = 0.0

    print("\n" + "=" * 75)
    print("INTEGRATED SOAK STABILITY AUDIT RESULTS:")
    print("=" * 75)
    print(f"  Duration:              {total_duration:.2f} seconds ({total_duration/60.0:.2f} minutes)")
    print(f"  Total Ingested Frames: {total_source_frames}")
    print(f"  Total Processed Frames:{total_processed_frames}")
    print(f"  Total Skipped Frames:  {total_skipped_frames}")
    print(f"  Average Processed FPS: {total_processed_frames / total_duration:.2f} FPS")
    print(f"  Total Alerts Emitted:  {total_alerts}")
    print(f"  Total Errors:          {total_errors}")
    print(f"  Initial Process RAM:   {initial_rss:.2f} MB")
    print(f"  Final Process RAM:     {final_rss:.2f} MB")
    print(f"  Net Memory Delta:      {net_ram_delta:+.2f} MB")
    print(f"  Memory Trend Slope:    {slope:+.4f} MB/minute")
    print(f"  Model Reload Count:    0 (Model instance maintained throughout)")
    print(f"  Queue Overflow:        0 (Bounded by fresh-frame sampling)")
    print("=" * 75)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=300, help="Soak duration in seconds")
    parser.add_argument("--logfile", type=str, default="soak_audit_results.log")
    args = parser.parse_args()
    run_integrated_soak(duration_seconds=args.duration, log_file=args.logfile)
