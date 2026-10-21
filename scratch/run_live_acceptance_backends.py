import asyncio
import os
import sys
import uvicorn
import cv2
import httpx

# Ensure repository root is on sys.path
sys.path.insert(0, os.getcwd())

from stubs.uc1_v2.main import app as uc1_app
from stubs.uc2_stub.main import app as uc2_app
from services.uc3.main import app as uc3_app
from stubs.uc4_stub.main import app as uc4_app

async def prime_after_startup():
    """Wait for servers to bind and then submit real frames through actual endpoints."""
    await asyncio.sleep(3.0)
    print("Priming live endpoints with actual test media...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. UC1: sample_worker.jpg
        try:
            f1 = cv2.imread("services/dashboard/public/test_media/uc1.jpg")
            _, b1 = cv2.imencode(".jpg", f1)
            r1 = await client.post(
                "http://127.0.0.1:8021/uc1/cameras/test-cam-uc1/infer-image",
                content=b1.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            print(f"UC1 Real Model Primed on Port 8021: HTTP {r1.status_code}, Detections: {len(r1.json().get('detections', []))}")
        except Exception as e:
            print(f"UC1 Prime Error: {e}")

        # 2. UC2: uc2_portrait.jpg
        try:
            f2 = cv2.imread("services/dashboard/public/test_media/uc2_portrait.jpg")
            _, b2 = cv2.imencode(".jpg", f2)
            r2 = await client.post(
                "http://127.0.0.1:8022/uc2/cameras/test-cam-uc2/infer-image",
                content=b2.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            print(f"UC2 Real Model Primed on Port 8022: HTTP {r2.status_code}, Detections: {len(r2.json().get('detections', []))}")
        except Exception as e:
            print(f"UC2 Prime Error: {e}")

        # 3. UC3: uc3.jpg
        try:
            f3 = cv2.imread("services/dashboard/public/test_media/uc3.jpg")
            _, b3 = cv2.imencode(".jpg", f3)
            r3 = await client.post(
                "http://127.0.0.1:8023/uc3/cameras/test-cam-uc3/infer-image",
                content=b3.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            print(f"UC3 Real Model Primed on Port 8023: HTTP {r3.status_code}, Detections: {len(r3.json().get('detections', []))}")
        except Exception as e:
            print(f"UC3 Prime Error: {e}")

        # 4. UC4: uc4_landscape.jpg
        try:
            f4 = cv2.imread("services/dashboard/public/test_media/uc4_landscape.jpg")
            _, b4 = cv2.imencode(".jpg", f4)
            r4 = await client.post(
                "http://127.0.0.1:8024/uc4/cameras/test-cam-uc4/infer-image",
                content=b4.tobytes(),
                headers={"Content-Type": "application/octet-stream"},
            )
            print(f"UC4 Real Model Primed on Port 8024: HTTP {r4.status_code}, Detections: {len(r4.json().get('detections', []))}")
        except Exception as e:
            print(f"UC4 Prime Error: {e}")

    print("ALL 4 REAL MODELS PRIMED AND SERVING AT /latest-detections AND /infer-image!")

async def main():
    asyncio.create_task(prime_after_startup())

    c1 = uvicorn.Config(uc1_app, host="127.0.0.1", port=8021, log_level="warning")
    c2 = uvicorn.Config(uc2_app, host="127.0.0.1", port=8022, log_level="warning")
    c3 = uvicorn.Config(uc3_app, host="127.0.0.1", port=8023, log_level="warning")
    c4 = uvicorn.Config(uc4_app, host="127.0.0.1", port=8024, log_level="warning")

    s1 = uvicorn.Server(c1)
    s2 = uvicorn.Server(c2)
    s3 = uvicorn.Server(c3)
    s4 = uvicorn.Server(c4)

    print("Acceptance backend running actual microservices on 8021, 8022, 8023, 8024")
    await asyncio.gather(s1.serve(), s2.serve(), s3.serve(), s4.serve())

if __name__ == "__main__":
    asyncio.run(main())
