"""
scratch/verify_production_endpoints_and_rendering.py

Submits real media and negative frames through actual production FastAPI endpoints for UC1-UC4.
Simulates frontend CameraOverlay.tsx canvas rendering (handling letterbox/pillarbox offsets).
Saves rendered frames and full JSON report into scratch/evidence/.
"""

import asyncio
import os
import sys
import json
import uuid
import cv2
import numpy as np

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

from httpx import ASGITransport, AsyncClient
from fastapi import FastAPI

from stubs.uc1_v2.main import app as uc1_app
from stubs.uc2_stub.main import app as uc2_app
from services.uc3.src.router import router as uc3_router
from stubs.uc4_stub.main import app as uc4_app

uc3_test_app = FastAPI()
uc3_test_app.include_router(uc3_router)

os.makedirs("scratch/evidence", exist_ok=True)
report = {}


async def run_production_rendering_audit():
    print("=== PRODUCTION ENDPOINT INFERENCE & RENDERING AUDIT ===")

    # Load representative media
    f_worker = cv2.imread("services/uc3/sample_worker.jpg")
    h_w, w_w = f_worker.shape[:2]
    _, buf_worker = cv2.imencode(".jpg", f_worker)
    bytes_worker = buf_worker.tobytes()

    v2 = cv2.VideoCapture("test_data/videos/uc2.mp4")
    v2.set(cv2.CAP_PROP_POS_FRAMES, 85)
    _, f_fire = v2.read()
    v2.release()
    h_f, w_f = f_fire.shape[:2]
    _, buf_fire = cv2.imencode(".jpg", f_fire)
    bytes_fire = buf_fire.tobytes()

    v4 = cv2.VideoCapture("test_data/videos/uc4.mp4")
    v4.set(cv2.CAP_PROP_POS_FRAMES, 30)
    _, f_traffic = v4.read()
    v4.release()
    h_t, w_t = f_traffic.shape[:2]
    _, buf_traffic = cv2.imencode(".jpg", f_traffic)
    bytes_traffic = buf_traffic.tobytes()

    blank = np.full((720, 1280, 3), 120, dtype=np.uint8)
    _, buf_blank = cv2.imencode(".jpg", blank)
    bytes_blank = buf_blank.tobytes()

    # 1. UC1 Production Endpoint Test
    t1 = ASGITransport(app=uc1_app)
    async with AsyncClient(transport=t1, base_url="http://uc1") as c1:
        cam_id = str(uuid.uuid4())
        r1_pos = await c1.post(
            f"/uc1/cameras/{cam_id}/infer-image",
            content=bytes_worker,
            headers={"Content-Type": "application/octet-stream"},
        )
        r1_neg = await c1.post(
            f"/uc1/cameras/{cam_id}/infer-image",
            content=bytes_blank,
            headers={"Content-Type": "application/octet-stream"},
        )
        d1 = r1_pos.json()
        pos_dets_1 = d1.get("detections", [])
        neg_dets_1 = r1_neg.json().get("detections", [])
        print(f"UC1 Endpoint: Status={r1_pos.status_code}, PosDets={len(pos_dets_1)}, NegDets={len(neg_dets_1)}")
        report["uc1_production_endpoint"] = {
            "endpoint": f"/uc1/cameras/{cam_id}/infer-image",
            "status_code": r1_pos.status_code,
            "input_dims": [w_w, h_w],
            "checkpoint": "yolov8n.pt",
            "positive_detections_count": len(pos_dets_1),
            "negative_blank_detections_count": len(neg_dets_1),
            "detections": pos_dets_1,
        }

    # 2. UC2 Production Endpoint Test
    t2 = ASGITransport(app=uc2_app)
    async with AsyncClient(transport=t2, base_url="http://uc2") as c2:
        cam_id = str(uuid.uuid4())
        r2_pos = await c2.post(
            f"/uc2/cameras/{cam_id}/infer-image",
            content=bytes_fire,
            headers={"Content-Type": "application/octet-stream"},
        )
        r2_neg = await c2.post(
            f"/uc2/cameras/{cam_id}/infer-image",
            content=bytes_blank,
            headers={"Content-Type": "application/octet-stream"},
        )
        d2 = r2_pos.json()
        pos_dets_2 = d2.get("detections", [])
        neg_dets_2 = r2_neg.json().get("detections", [])
        print(f"UC2 Endpoint: Status={r2_pos.status_code}, PosDets={len(pos_dets_2)}, NegDets={len(neg_dets_2)}")
        report["uc2_production_endpoint"] = {
            "endpoint": f"/uc2/cameras/{cam_id}/infer-image",
            "status_code": r2_pos.status_code,
            "input_dims": [w_f, h_f],
            "checkpoint": "stubs/uc2_stub/cv_engine/models/best.pt",
            "positive_detections_count": len(pos_dets_2),
            "negative_blank_detections_count": len(neg_dets_2),
            "hazard_flags": {
                "fire_detected": d2.get("fire_detected"),
                "smoke_detected": d2.get("smoke_detected"),
                "sparks_detected": d2.get("sparks_detected"),
            },
            "detections": pos_dets_2,
        }

    # 3. UC3 Production Endpoint Test
    t3 = ASGITransport(app=uc3_test_app)
    async with AsyncClient(transport=t3, base_url="http://uc3") as c3:
        cam_id = str(uuid.uuid4())
        r3_pos = await c3.post(
            f"/uc3/cameras/{cam_id}/infer-image",
            content=bytes_worker,
            headers={"Content-Type": "application/octet-stream"},
        )
        r3_neg = await c3.post(
            f"/uc3/cameras/{cam_id}/infer-image",
            content=bytes_blank,
            headers={"Content-Type": "application/octet-stream"},
        )
        d3 = r3_pos.json()
        pos_dets_3 = d3.get("detections", [])
        neg_dets_3 = r3_neg.json().get("detections", [])
        print(f"UC3 Endpoint: Status={r3_pos.status_code}, PosDets={len(pos_dets_3)}, NegDets={len(neg_dets_3)}")
        report["uc3_production_endpoint"] = {
            "endpoint": f"/uc3/cameras/{cam_id}/infer-image",
            "status_code": r3_pos.status_code,
            "input_dims": [w_w, h_w],
            "checkpoint": "services/uc3/models/best.pt",
            "positive_detections_count": len(pos_dets_3),
            "negative_blank_detections_count": len(neg_dets_3),
            "severity": d3.get("severity"),
            "violations": d3.get("violations"),
            "detections": pos_dets_3,
        }

    # 4. UC4 Production Endpoint Test
    t4 = ASGITransport(app=uc4_app)
    async with AsyncClient(transport=t4, base_url="http://uc4") as c4:
        cam_id = str(uuid.uuid4())
        r4_pos = await c4.post(
            f"/uc4/cameras/{cam_id}/infer-image",
            content=bytes_traffic,
            headers={"Content-Type": "application/octet-stream"},
        )
        r4_neg = await c4.post(
            f"/uc4/cameras/{cam_id}/infer-image",
            content=bytes_blank,
            headers={"Content-Type": "application/octet-stream"},
        )
        d4 = r4_pos.json()
        pos_dets_4 = d4.get("detections", [])
        neg_dets_4 = r4_neg.json().get("detections", [])
        print(f"UC4 Endpoint: Status={r4_pos.status_code}, PosDets={len(pos_dets_4)}, NegDets={len(neg_dets_4)}")
        report["uc4_production_endpoint"] = {
            "endpoint": f"/uc4/cameras/{cam_id}/infer-image",
            "status_code": r4_pos.status_code,
            "input_dims": [w_t, h_t],
            "checkpoint": "yolo11n.pt",
            "positive_detections_count": len(pos_dets_4),
            "negative_blank_detections_count": len(neg_dets_4),
            "temporal_tracking_available": d4.get("temporal_tracking_available"),
            "speed_estimation_available": d4.get("speed_estimation_available"),
            "detections": pos_dets_4,
        }

    # 5. Frontend Canvas Rendering Simulation (CameraOverlay.tsx line 198-364)
    def render_canvas_overlay(frame, detections, output_path, container_w=1280, container_h=720):
        src_h, src_w = frame.shape[:2]
        video_aspect = src_w / float(src_h)
        container_aspect = container_w / float(container_h)

        if container_aspect > video_aspect:
            # Pillarboxed (vertical bars left/right)
            disp_w = container_h * video_aspect
            disp_h = container_h
            off_x = (container_w - disp_w) / 2.0
            off_y = 0.0
        else:
            # Letterboxed (horizontal bars top/bottom)
            disp_w = container_w
            disp_h = container_w / video_aspect
            off_x = 0.0
            off_y = (container_h - disp_h) / 2.0

        canvas = np.zeros((container_h, container_w, 3), dtype=np.uint8)
        resized = cv2.resize(frame, (int(disp_w), int(disp_h)))
        rh, rw = resized.shape[:2]
        oy = int(off_y)
        ox = int(off_x)
        canvas[oy : oy + rh, ox : ox + rw] = resized

        for d in detections:
            bb = d.get("bbox")
            if not bb:
                continue
            if isinstance(bb, dict):
                bx1, by1, bx2, by2 = bb["x1"], bb["y1"], bb["x2"], bb["y2"]
            elif isinstance(bb, list):
                bx1, by1, bx2, by2 = bb
            else:
                continue

            cx1 = int(off_x + bx1 * disp_w)
            cy1 = int(off_y + by1 * disp_h)
            cx2 = int(off_x + bx2 * disp_w)
            cy2 = int(off_y + by2 * disp_h)

            label = d.get("label", "OBJ")
            is_vio = d.get("is_violation") or d.get("compliant") is False
            color = (0, 0, 255) if is_vio else (255, 200, 0)
            cv2.rectangle(canvas, (cx1, cy1), (cx2, cy2), color, 2)
            cv2.putText(
                canvas,
                label,
                (cx1, max(20, cy1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                1,
            )

        cv2.imwrite(output_path, canvas)

    render_canvas_overlay(f_worker, pos_dets_1, "scratch/evidence/production_rendered_uc1.jpg")
    render_canvas_overlay(f_fire, pos_dets_2, "scratch/evidence/production_rendered_uc2.jpg")
    render_canvas_overlay(f_worker, pos_dets_3, "scratch/evidence/production_rendered_uc3.jpg")
    render_canvas_overlay(f_traffic, pos_dets_4, "scratch/evidence/production_rendered_uc4.jpg")
    print("Saved rendered canvas frames to scratch/evidence/production_rendered_uc*.jpg")

    with open("scratch/evidence/production_endpoint_vs_direct_model.json", "w") as f:
        json.dump(report, f, indent=2)
    print("Saved scratch/evidence/production_endpoint_vs_direct_model.json")


if __name__ == "__main__":
    asyncio.run(run_production_rendering_audit())
