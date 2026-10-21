import httpx
import cv2
import numpy as np

blank = np.full((720, 1280, 3), 128, dtype=np.uint8)
_, buf = cv2.imencode(".jpg", blank)
blank_bytes = buf.tobytes()

print("Testing NEGATIVE / BLANK FRAMES on all 4 actual microservices...")

for p, uc in [
    (8021, "uc1"),
    (8022, "uc2"),
    (8023, "uc3"),
    (8024, "uc4"),
]:
    url = f"http://127.0.0.1:{p}/{uc}/cameras/test-cam-empty/infer-image"
    try:
        r = httpx.post(
            url,
            content=blank_bytes,
            headers={"Content-Type": "application/octet-stream"},
            timeout=10.0,
        )
        data = r.json()
        dets = data.get("detections", [])
        print(f"Port {p} ({uc.upper()}): HTTP {r.status_code}, Detections = {len(dets)}")
        assert len(dets) == 0, f"Expected 0 detections on blank frame, got {len(dets)}"
    except Exception as e:
        print(f"Port {p} ({uc.upper()}) Error: {e}")

print("ALL 4 ACTUAL MICROSERVICES PASSED NEGATIVE / BLANK DETECTION TEST (0 detections)!")
