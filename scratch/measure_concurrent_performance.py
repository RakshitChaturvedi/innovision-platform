import asyncio
import time
import json
import httpx
import cv2
import psutil

# Prepare payloads
frames = {
    8021: ("uc1", "services/dashboard/public/test_media/uc1.jpg"),
    8022: ("uc2", "services/dashboard/public/test_media/uc2_portrait.jpg"),
    8023: ("uc3", "services/dashboard/public/test_media/uc3.jpg"),
    8024: ("uc4", "services/dashboard/public/test_media/uc4_landscape.jpg"),
}

encoded_bytes = {}
for port, (uc, path) in frames.items():
    img = cv2.imread(path)
    _, buf = cv2.imencode(".jpg", img)
    encoded_bytes[port] = buf.tobytes()

results = {
    "system_baseline": {
        "logical_cpu_cores": psutil.cpu_count(logical=True),
        "physical_cpu_cores": psutil.cpu_count(logical=False),
        "total_ram_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "initial_available_ram_gb": round(psutil.virtual_memory().available / (1024**3), 2),
        "initial_cpu_percent": psutil.cpu_percent(interval=0.5),
    },
    "individual_pipelines": {},
    "concurrent_run": {},
}

# 1. Individual Pipeline Benchmarks (5 requests per service sequentially)
for port, (uc, path) in frames.items():
    latencies = []
    url = f"http://127.0.0.1:{port}/{uc}/cameras/bench-cam/infer-image"
    payload = encoded_bytes[port]
    with httpx.Client(timeout=30.0) as client:
        # warm-up
        _ = client.post(url, content=payload, headers={"Content-Type": "application/octet-stream"})
        for _ in range(5):
            t0 = time.perf_counter()
            r = client.post(url, content=payload, headers={"Content-Type": "application/octet-stream"})
            latencies.append((time.perf_counter() - t0) * 1000)

    import numpy as np
    mean_lat = round(float(np.mean(latencies)), 2)
    p95_lat = round(float(np.percentile(latencies, 95)), 2)
    fps = round(1000.0 / mean_lat, 1) if mean_lat > 0 else 0
    results["individual_pipelines"][uc] = {
        "port": port,
        "mean_latency_ms": mean_lat,
        "p95_latency_ms": p95_lat,
        "throughput_fps": fps,
        "meets_30fps": fps >= 30.0,
    }

# 2. Concurrent 4-Pipeline Run (All 4 services invoked simultaneously)
async def invoke_pipeline(client: httpx.AsyncClient, port: int, uc: str, payload: bytes):
    url = f"http://127.0.0.1:{port}/{uc}/cameras/concurrent-cam/infer-image"
    t0 = time.perf_counter()
    r = await client.post(url, content=payload, headers={"Content-Type": "application/octet-stream"})
    lat = (time.perf_counter() - t0) * 1000
    return port, uc, r.status_code, lat

async def run_concurrent_bench():
    cpu_measurements = []
    concurrent_latencies = {8021: [], 8022: [], 8023: [], 8024: []}
    t_start = time.perf_counter()

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Run 5 concurrent rounds of all 4 pipelines
        for _ in range(5):
            cpu_measurements.append(psutil.cpu_percent(interval=None))
            tasks = [
                invoke_pipeline(client, port, uc, encoded_bytes[port])
                for port, (uc, _) in frames.items()
            ]
            round_results = await asyncio.gather(*tasks)
            for port, uc, status, lat in round_results:
                concurrent_latencies[port].append(lat)

    t_total = time.perf_counter() - t_start
    total_inferences = 5 * 4
    agg_throughput = round(total_inferences / t_total, 2)

    import numpy as np
    results["concurrent_run"] = {
        "total_requests": total_inferences,
        "total_time_seconds": round(t_total, 2),
        "aggregate_throughput_fps": agg_throughput,
        "peak_cpu_percent": max(cpu_measurements) if cpu_measurements else 0,
        "per_pipeline_concurrent_latency": {
            frames[p][0]: {
                "mean_ms": round(float(np.mean(concurrent_latencies[p])), 2),
                "p95_ms": round(float(np.percentile(concurrent_latencies[p], 95)), 2),
                "fps": round(1000.0 / float(np.mean(concurrent_latencies[p])), 2),
            }
            for p in [8021, 8022, 8023, 8024]
        },
        "per_stream_meets_30fps": False,
    }

asyncio.run(run_concurrent_bench())

with open("scratch/evidence/concurrent_performance_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("CONCURRENT BENCHMARK COMPLETE: scratch/evidence/concurrent_performance_results.json written.")
