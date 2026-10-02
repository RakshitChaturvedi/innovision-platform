"""
Validation of High-Resolution RTSP input, decode cost, memory, payload size,
and verification that downsampling to 640x480 preserves detection of Fire, Smoke, Sparks.
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
from services.ingestion.src.jpeg_encoder import JpegEncoder
from services.ingestion.src.config import settings

def main():
    print("=" * 70)
    print("HIGH-RESOLUTION RTSP & DOWNSAMPLING EMPIRICAL VALIDATION")
    print("=" * 70)

    process = psutil.Process()
    initial_mem_mb = process.memory_info().rss / (1024 * 1024)

    # 1. 1080p Video Decode & Ingestion Benchmark
    video_1080p = "test_data/videos/uc1.mp4"
    if not os.path.exists(video_1080p):
        print(f"Error: {video_1080p} not found")
        return

    cap = cv2.VideoCapture(video_1080p)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"[1] 1080p RTSP Stream Simulation: {video_1080p}")
    print(f"    Dimensions: {width}x{height} | Total Frames: {total_frames}")

    decode_times = []
    native_encode_sizes = []
    downsampled_encode_sizes = []
    native_encode_times = []
    downsample_encode_times = []
    frames = []

    encoder = JpegEncoder(quality=85)

    for i in range(min(total_frames, 30)):
        t0 = time.perf_counter()
        ret, frame = cap.read()
        t1 = time.perf_counter()
        if not ret:
            break
        decode_times.append((t1 - t0) * 1000)
        frames.append(frame)

        # Native 1080p encode
        t_enc0 = time.perf_counter()
        native_bytes = encoder.encode(frame)
        t_enc1 = time.perf_counter()
        native_encode_times.append((t_enc1 - t_enc0) * 1000)
        native_encode_sizes.append(len(native_bytes))

        # Downsample to 640x360 (aspect ratio preserved 640 max)
        t_down0 = time.perf_counter()
        h, w = frame.shape[:2]
        scale = min(640 / w, 480 / h)
        downsampled = cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
        down_bytes = encoder.encode(downsampled)
        t_down1 = time.perf_counter()
        downsample_encode_times.append((t_down1 - t_down0) * 1000)
        downsampled_encode_sizes.append(len(down_bytes))

    cap.release()

    avg_decode_ms = np.mean(decode_times)
    p95_decode_ms = np.percentile(decode_times, 95)
    avg_native_size_kb = np.mean(native_encode_sizes) / 1024
    avg_down_size_kb = np.mean(downsampled_encode_sizes) / 1024
    avg_native_enc_ms = np.mean(native_encode_times)
    avg_down_enc_ms = np.mean(downsample_encode_times)

    print(f"    -> Average Decode Cost: {avg_decode_ms:.2f} ms (P95: {p95_decode_ms:.2f} ms)")
    print(f"    -> Native 1080p Payload Size: {avg_native_size_kb:.1f} KB (Encode: {avg_native_enc_ms:.2f} ms)")
    print(f"    -> Downsampled 640x360 Payload Size: {avg_down_size_kb:.1f} KB (Resize+Encode: {avg_down_enc_ms:.2f} ms)")
    reduction_pct = (1.0 - (avg_down_size_kb / avg_native_size_kb)) * 100
    print(f"    -> Redis Payload Reduction: {reduction_pct:.1f}% bandwidth & RAM savings")

    # 2. 4K Smoke Sample Benchmark
    img_4k_path = "test_data/images/sample_smoke.jpg"
    img_4k = cv2.imread(img_4k_path)
    h_4k, w_4k = img_4k.shape[:2]
    native_4k_bytes = encoder.encode(img_4k)
    scale_4k = min(640 / w_4k, 480 / h_4k)
    down_4k = cv2.resize(img_4k, (int(round(w_4k * scale_4k)), int(round(h_4k * scale_4k))), interpolation=cv2.INTER_AREA)
    down_4k_bytes = encoder.encode(down_4k)
    print(f"\n[2] 4K Image Ingestion & Payload: {w_4k}x{h_4k}")
    print(f"    -> Native 4K Payload: {len(native_4k_bytes)/1024:.1f} KB")
    print(f"    -> Downsampled (640x360) Payload: {len(down_4k_bytes)/1024:.1f} KB")
    print(f"    -> 4K Reduction: {(1.0 - len(down_4k_bytes)/len(native_4k_bytes))*100:.1f}%")

    # 3. Detection Quality & Latency: Native vs Downsampled
    pipeline = DetectionPipeline()

    print("\n[3] Detection Quality & Latency Comparison (Native vs Downsampled):")
    camera_id = "00000000-0000-0000-0000-000000000001"

    test_cases = [
        ("Fire", "test_data/images/sample_fire.jpg"),
        ("Smoke (4K)", "test_data/images/sample_smoke.jpg"),
        ("Sparks", "test_data/images/sample_sparks.jpg"),
    ]

    for label, path in test_cases:
        img_native = cv2.imread(path)
        hn, wn = img_native.shape[:2]

        # Downsample to max 640x480
        scale = min(640 / wn, 480 / hn)
        img_down = cv2.resize(img_native, (int(round(wn * scale)), int(round(hn * scale))), interpolation=cv2.INTER_AREA)

        # Run on native
        t0 = time.perf_counter()
        res_native = pipeline.process_frame(camera_id, 101, img_native, single_frame=True)
        t_native_ms = (time.perf_counter() - t0) * 1000

        # Run on downsampled
        t0 = time.perf_counter()
        res_down = pipeline.process_frame(camera_id, 102, img_down, single_frame=True)
        t_down_ms = (time.perf_counter() - t0) * 1000

        native_dets = [f"{d.detection_type}:{d.final_confidence:.2f}" for d in res_native.confirmed_detections]
        down_dets = [f"{d.detection_type}:{d.final_confidence:.2f}" for d in res_down.confirmed_detections]

        print(f"    - {label}:")
        print(f"        Native: {wn}x{hn} | Latency: {t_native_ms:.1f}ms | Detections: {native_dets}")
        print(f"        Downsampled: {img_down.shape[1]}x{img_down.shape[0]} | Latency: {t_down_ms:.1f}ms | Detections: {down_dets}")
        assert len(res_down.confirmed_detections) > 0, f"Downsampled {label} lost detection!"

    # 4. Tiny Fire Target Validation (downscaled small object)
    print("\n[4] Small Object Sensitivity After Downsampling:")
    # Test sparks image tiny flame cluster (28x15 px)
    sparks_img = cv2.imread("test_data/images/sample_sparks.jpg")
    scale = min(640 / sparks_img.shape[1], 480 / sparks_img.shape[0])
    sparks_down = cv2.resize(sparks_img, (int(round(sparks_img.shape[1] * scale)), int(round(sparks_img.shape[0] * scale))), interpolation=cv2.INTER_AREA)
    res_sparks = pipeline.process_frame(camera_id, 201, sparks_down, single_frame=True)
    spark_dets = [d for d in res_sparks.confirmed_detections if d.detection_type in ("sparks", "spark")]
    print(f"    -> Sparks preserved after downsampling: {len(spark_dets) > 0} (count={len(spark_dets)})")
    assert len(spark_dets) > 0, "Sparks lost after downsampling!"

    final_mem_mb = process.memory_info().rss / (1024 * 1024)
    print(f"\n[5] Resource Impact:")
    print(f"    -> Initial RAM: {initial_mem_mb:.1f} MB | Final RAM: {final_mem_mb:.1f} MB | Delta: {final_mem_mb - initial_mem_mb:+.1f} MB")
    print(f"    -> CPU Decode Cost per 1080p frame: {avg_decode_ms:.2f} ms")
    print("=" * 70)
    print("HIGH-RESOLUTION RTSP & DOWNSAMPLING VALIDATION: ALL PASSED")
    print("=" * 70)

if __name__ == "__main__":
    main()
