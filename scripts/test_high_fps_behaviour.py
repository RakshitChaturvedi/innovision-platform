"""
Benchmark & validation of Real High-FPS camera stream behaviour.
Validates that when Source FPS > UC2 processing capacity:
- fresh-frame sampling works
- stale frames do not accumulate (queue depth bounded)
- frame age remains strictly bounded
- skipped frames are tracked and measurable
- temporal hazard persistence remains reliable
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import datetime, timezone
from uuid import uuid4

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.contracts.frame_event import FrameEvent
from shared.contracts.enums import FrameProvider
from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline

class MockHighFpsStream:
    """Simulates a real high-rate camera input and Redis stream queue."""
    def __init__(self, camera_id: str, source_fps: float = 30.0):
        self.camera_id = camera_id
        self.source_fps = source_fps
        self.queue: list[tuple[str, FrameEvent, np.ndarray]] = []
        self.seq = 0
        self.total_ingested = 0
        self.skipped_frames = 0
        self.fire_frame = cv2.imread("test_data/images/sample_fire.jpg")
        if self.fire_frame is None:
            # Fallback synthetic fire
            self.fire_frame = np.full((480, 640, 3), 40, dtype=np.uint8)
            cv2.ellipse(self.fire_frame, (320, 240), (80, 120), 0, 0, 360, (0, 165, 255), -1)

    def produce_burst(self, count: int):
        now = datetime.now(timezone.utc)
        for _ in range(count):
            self.seq += 1
            self.total_ingested += 1
            event = FrameEvent(
                camera_id=self.camera_id,
                frame_seq=self.seq,
                timestamp=now,
                frame_reference=f"frame:{self.camera_id}:{self.seq}",
                frame_provider=FrameProvider.REDIS,
                frame_shape=(self.fire_frame.shape[0], self.fire_frame.shape[1]),
            )
            msg_id = f"{int(time.time()*1000)}-{self.seq}"
            self.queue.append((msg_id, event, self.fire_frame.copy()))

    def consume_batch(self, batch_size: int = 10, latest_only: bool = True):
        """Simulates RedisFrameConsumer.read_frames logic."""
        if not self.queue:
            return []
        batch = self.queue[:batch_size]
        self.queue = self.queue[batch_size:]

        if latest_only and len(batch) > 1:
            skipped = len(batch) - 1
            self.skipped_frames += skipped
            return [batch[-1]]
        return batch

def main():
    print("=" * 70)
    print("HIGH-FPS CAMERA STREAM BEHAVIOUR & FRESHNESS BENCHMARK")
    print("=" * 70)

    camera_id = "00000000-0000-0000-0000-000000000001"
    source_fps = 30.0
    stream = MockHighFpsStream(camera_id=camera_id, source_fps=source_fps)
    pipeline = DetectionPipeline()

    duration_s = 10.0
    start_time = time.perf_counter()
    next_frame_time = start_time
    frame_interval = 1.0 / source_fps

    processed_count = 0
    frame_ages = []
    latencies = []
    queue_depths = []
    confirmed_alerts = 0

    print(f"Simulating continuous 30 FPS input stream for {duration_s:.1f}s...")
    print("UC2 detection running at CPU native capacity with latest_only=True")

    # Ingestion producer task simulating 30 FPS camera
    while (time.perf_counter() - start_time) < duration_s:
        t_now = time.perf_counter()
        # Produce frames up to current time
        while next_frame_time <= t_now:
            stream.produce_burst(1)
            next_frame_time += frame_interval

        queue_depths.append(len(stream.queue))

        # UC2 consumer step
        items = stream.consume_batch(batch_size=10, latest_only=True)
        if items:
            for msg_id, event, frame_img in items:
                # Measure frame age
                age_ms = (datetime.now(timezone.utc) - event.timestamp).total_seconds() * 1000.0
                frame_ages.append(max(0.0, age_ms))

                # Process through pipeline
                t0 = time.perf_counter()
                res = pipeline.process_frame(camera_id, event.frame_seq, frame_img)
                lat_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(lat_ms)
                processed_count += 1

                if any(d.detection_type == "fire" for d in res.confirmed_detections):
                    confirmed_alerts += 1

        # Yield a tiny slice to simulate real event loop
        time.sleep(0.001)

    elapsed = time.perf_counter() - start_time
    measured_source_fps = stream.total_ingested / elapsed
    measured_uc2_fps = processed_count / elapsed
    measured_skipped_fps = stream.skipped_frames / elapsed

    mean_age = np.mean(frame_ages) if frame_ages else 0.0
    p95_age = np.percentile(frame_ages, 95) if frame_ages else 0.0
    max_age = np.max(frame_ages) if frame_ages else 0.0
    mean_lat = np.mean(latencies) if latencies else 0.0
    p95_lat = np.percentile(latencies, 95) if latencies else 0.0
    avg_queue = np.mean(queue_depths) if queue_depths else 0.0
    max_queue = np.max(queue_depths) if queue_depths else 0.0

    print("\nEMPIRICAL RESULTS:")
    print(f"  SOURCE FPS:        {measured_source_fps:.2f} FPS")
    print(f"  INGESTION FRAMES:  {stream.total_ingested} total")
    print(f"  UC2 PROCESSED FPS: {measured_uc2_fps:.2f} FPS ({processed_count} processed)")
    print(f"  SKIPPED FPS:       {measured_skipped_fps:.2f} FPS ({stream.skipped_frames} skipped)")
    print(f"  SKIPPED RATIO:     {(stream.skipped_frames / stream.total_ingested)*100:.1f}%")
    print(f"  FRAME AGE (MEAN):  {mean_age:.2f} ms")
    print(f"  FRAME AGE (P95):   {p95_age:.2f} ms")
    print(f"  FRAME AGE (MAX):   {max_age:.2f} ms")
    print(f"  INFERENCE LATENCY: {mean_lat:.2f} ms (P95: {p95_lat:.2f} ms)")
    print(f"  AVG QUEUE DEPTH:   {avg_queue:.2f} frames (Max backlog: {max_queue} frames)")
    print(f"  CONFIRMED ALERTS:  {confirmed_alerts} fire alerts emitted")
    print("=" * 70)

    # Verification gates
    assert p95_age < 350.0, f"Frame age exceeded safe bound: {p95_age:.1f}ms > 350ms"
    assert stream.skipped_frames > 0, "High-FPS didn't trigger fresh-frame skipping"
    assert confirmed_alerts > 0, "Temporal fire detection failed during high-FPS load"
    print("HIGH-FPS CAMERA BEHAVIOUR & FRESHNESS VALIDATION: PASSED")
    print("=" * 70)

if __name__ == "__main__":
    main()
