import time
import json
import cv2
import numpy as np
import torch
from ultralytics import YOLO

# Verify hardware environment
device = "cpu"
threads = torch.get_num_threads()

models_info = [
    {
        "uc": "uc1",
        "name": "UC1 Intrusion (YOLOv8n)",
        "path": "yolov8n.pt",
        "sample": "services/dashboard/public/test_media/uc1.jpg",
        "imgsz": 640,
    },
    {
        "uc": "uc2",
        "name": "UC2 Fire/Sparks (YOLOv8s Custom)",
        "path": "stubs/uc2_stub/cv_engine/models/best.pt",
        "sample": "services/dashboard/public/test_media/uc2_portrait.jpg",
        "imgsz": 640,
    },
    {
        "uc": "uc3",
        "name": "UC3 PPE Compliance (YOLOv8n Custom)",
        "path": "services/uc3/models/best.pt",
        "sample": "services/dashboard/public/test_media/uc3.jpg",
        "imgsz": 640,
    },
    {
        "uc": "uc4",
        "name": "UC4 Traffic & ANPR (YOLO11n)",
        "path": "yolo11n.pt",
        "sample": "services/dashboard/public/test_media/uc4_landscape.jpg",
        "imgsz": 640,
    },
]

WARMUP = 5
ITERATIONS = 30

results = {
    "hardware": {
        "device": device,
        "cuda_available": torch.cuda.is_available(),
        "cpu_threads": threads,
        "warmup_iterations": WARMUP,
        "benchmark_iterations": ITERATIONS,
    },
    "benchmarks": {},
}

for m in models_info:
    uc = m["uc"]
    t0 = time.perf_counter()
    model = YOLO(m["path"])
    load_time_ms = round((time.perf_counter() - t0) * 1000, 2)

    frame = cv2.imread(m["sample"])
    _, buf = cv2.imencode(".jpg", frame)
    raw_bytes = buf.tobytes()

    # Warmup
    for _ in range(WARMUP):
        _ = model.predict(source=frame, imgsz=m["imgsz"], verbose=False)

    # 1. Raw Model Inference Latency
    raw_latencies = []
    for _ in range(ITERATIONS):
        t1 = time.perf_counter()
        _ = model.predict(source=frame, imgsz=m["imgsz"], verbose=False)
        raw_latencies.append((time.perf_counter() - t1) * 1000)

    # 2. Complete Production-Pipeline Latency (decode + infer + filter + format)
    pipeline_latencies = []
    for _ in range(ITERATIONS):
        t1 = time.perf_counter()
        # Step A: JPEG decode
        decoded = cv2.imdecode(np.frombuffer(raw_bytes, np.uint8), cv2.IMREAD_COLOR)
        # Step B: Model inference
        preds = model.predict(source=decoded, imgsz=m["imgsz"], verbose=False)
        # Step C: Domain output extraction
        if preds and len(preds) > 0:
            boxes = preds[0].boxes
            _ = [
                {
                    "cls": int(b.cls[0]),
                    "conf": float(b.conf[0]),
                    "box": b.xyxyn[0].tolist(),
                }
                for b in boxes
            ]
        pipeline_latencies.append((time.perf_counter() - t1) * 1000)

    raw_mean = round(float(np.mean(raw_latencies)), 2)
    raw_p95 = round(float(np.percentile(raw_latencies, 95)), 2)
    pipe_mean = round(float(np.mean(pipeline_latencies)), 2)
    pipe_p95 = round(float(np.percentile(pipeline_latencies, 95)), 2)

    single_stream_fps = round(1000.0 / pipe_mean, 1)

    results["benchmarks"][uc] = {
        "model_name": m["name"],
        "checkpoint_path": m["path"],
        "load_time_ms": load_time_ms,
        "raw_model_inference": {
            "mean_ms": raw_mean,
            "p95_ms": raw_p95,
            "min_ms": round(float(np.min(raw_latencies)), 2),
            "max_ms": round(float(np.max(raw_latencies)), 2),
        },
        "complete_production_pipeline": {
            "mean_ms": pipe_mean,
            "p95_ms": pipe_p95,
            "min_ms": round(float(np.min(pipeline_latencies)), 2),
            "max_ms": round(float(np.max(pipeline_latencies)), 2),
            "overhead_ms": round(pipe_mean - raw_mean, 2),
        },
        "single_stream_throughput_fps": single_stream_fps,
        "meets_30fps_target": single_stream_fps >= 30.0,
    }

with open("scratch/evidence/cpu_benchmarks_reconciled.json", "w") as f:
    json.dump(results, f, indent=2)

print("Benchmarks finished. Summary:")
for k, v in results["benchmarks"].items():
    print(f"{k.upper()}: Raw={v['raw_model_inference']['mean_ms']}ms, Pipeline={v['complete_production_pipeline']['mean_ms']}ms (P95={v['complete_production_pipeline']['p95_ms']}ms), SingleStream={v['single_stream_throughput_fps']} FPS")
