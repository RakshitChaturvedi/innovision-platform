#!/usr/bin/env python3
"""
generate_uc3_demo.py — Generate fully annotated UC3 PPE demo video.
Burns actual PPE detections (Vest, Helmet, Person, Compliance status)
with bounding boxes, labels, and confidence tags onto real source frames.
Slows playback to 15 FPS for inspectability.
"""
import os
import sys
import time
import cv2
import numpy as np
from ultralytics import YOLO

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from stubs.uc3_stub.src import compliance, mannequin_gate

def generate():
    input_path = "/app/test_data/videos/uc3.mp4"
    if not os.path.exists(input_path):
        input_path = "test_data/videos/uc3.mp4"
    if not os.path.exists(input_path):
        print(f"ERROR: Input video not found at {input_path}")
        sys.exit(1)

    os.makedirs("/app/test_data/demos", exist_ok=True)
    os.makedirs("test_data/demos", exist_ok=True)
    output_path = "/app/test_data/demos/uc3_annotated.mp4"
    if not os.path.exists("/app/test_data"):
        output_path = "test_data/demos/uc3_annotated.mp4"

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {input_path}")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print(f"[UC3 Demo] Source video: {input_path} ({width}x{height}, {total_frames} frames @ {native_fps:.1f} fps)")

    demo_fps = 15.0
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, demo_fps, (width, height))
    if not writer.isOpened():
        print(f"ERROR: Cannot create VideoWriter at {output_path}")
        sys.exit(1)

    # Load real models
    ppe_model_path = "stubs/uc3_stub/models/best.pt"
    if not os.path.exists(ppe_model_path):
        ppe_model_path = "/app/stubs/uc3_stub/models/best.pt"
    person_model_path = "yolo11n.pt"
    if not os.path.exists(person_model_path):
        person_model_path = "/app/yolo11n.pt"

    ppe_model = YOLO(ppe_model_path)
    person_model = YOLO(person_model_path)
    worker_states = {}

    frame_seq = 0
    t_start = time.time()
    frames_with_detections = 0
    vest_total = 0
    helmet_total = 0
    person_total = 0

    print("[UC3 Demo] Processing frames through real PPE & Person Detection Models...")

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_seq += 1

        annotated = frame.copy()

        # 1. Person Gate
        p_res = person_model(frame, classes=[0], conf=0.35, verbose=False)
        person_boxes = []
        if p_res and p_res[0].boxes is not None:
            for b in p_res[0].boxes:
                person_boxes.append(list(map(int, b.xyxy[0])))

        # 2. PPE Detection
        ppe_res = ppe_model(frame, imgsz=640, conf=0.25, verbose=False)
        detections = []
        if ppe_res and ppe_res[0].boxes is not None:
            boxes = ppe_res[0].boxes
            names = ppe_model.names
            for i in range(len(boxes)):
                b_xyxy = list(map(int, boxes.xyxy[i]))
                c_val = float(boxes.conf[i])
                cls_id = int(boxes.cls[i])
                lbl = str(names.get(cls_id, cls_id))
                norm_b = [b_xyxy[0]/width, b_xyxy[1]/height, b_xyxy[2]/width, b_xyxy[3]/height]
                detections.append({
                    "label": lbl,
                    "conf": c_val,
                    "box": norm_b,
                    "pixel_box": b_xyxy,
                })

        # Add person detections into detections list
        for p_idx, pb in enumerate(person_boxes):
            norm_b = [pb[0]/width, pb[1]/height, pb[2]/width, pb[3]/height]
            detections.append({
                "label": "person",
                "conf": 0.85,
                "box": norm_b,
                "pixel_box": pb,
                "_track_id": p_idx + 1,
            })

        # Ensure head regions exist for helmet compliance check
        for pb in person_boxes:
            head_box = [pb[0]/width, pb[1]/height, pb[2]/width, (pb[1] + 0.25*(pb[3]-pb[1]))/height]
            detections.append({
                "label": "head",
                "conf": 0.85,
                "box": head_box,
            })

        # Compliance evaluation
        now_sec = time.monotonic()
        severity, unique_vio, worker_violations = compliance.evaluate_compliance(
            detections=detections,
            worker_states=worker_states,
            now=now_sec,
            required_ppe=frozenset({"helmet", "vest"}),
        )

        violating_tracks = {wv["worker_id"]: wv["ppe_type"] for wv in worker_violations} if worker_violations else {}

        if detections:
            frames_with_detections += 1

        # Draw PPE items first (Vest / Helmet)
        for d in detections:
            lbl = d["label"].lower()
            if lbl in ("head",):
                continue
            if "pixel_box" not in d:
                continue
            x1, y1, x2, y2 = d["pixel_box"]
            conf = d.get("conf", 0.8)

            if "vest" in lbl and "no" not in lbl:
                vest_total += 1
                color = (255, 176, 0)  # Cyan (BGR)
                badge = f"Vest {int(conf*100)}%"
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, badge, (x1, max(y1-5, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            elif "helmet" in lbl and "no" not in lbl:
                helmet_total += 1
                color = (0, 255, 255)  # Yellow
                badge = f"Helmet {int(conf*100)}%"
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, badge, (x1, max(y1-5, 15)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Draw Persons with compliance status
        for p_idx, pb in enumerate(person_boxes):
            person_total += 1
            tid = p_idx + 1
            x1, y1, x2, y2 = pb
            is_viol = tid in violating_tracks
            if is_viol:
                color = (50, 50, 255)  # Red
                text = f"Worker #{tid} [NO {violating_tracks[tid].upper()}]"
            else:
                color = (0, 230, 118)  # Green
                text = f"Worker #{tid} [Compliant]"

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)
            (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            by1 = max(0, y1 - th - 8)
            cv2.rectangle(annotated, (x1, by1), (min(width-1, x1 + tw + 10), y1), color, -1)
            cv2.putText(annotated, text, (x1 + 4, y1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)

        # Telemetry Banner
        status_text = f"UC3 PPE SAFETY | Workers: {len(person_boxes)} | Vests: {len([d for d in detections if 'vest' in d['label'].lower() and 'no' not in d['label'].lower()])} | Violations: {len(worker_violations)}"
        cv2.rectangle(annotated, (10, 10), (width - 10, 42), (20, 20, 20), -1)
        cv2.putText(annotated, status_text, (18, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1, cv2.LINE_AA)

        writer.write(annotated)

        if frame_seq % 50 == 0:
            print(f"  Frame {frame_seq}/{total_frames} ({frame_seq*100//total_frames}%) - Workers: {len(person_boxes)}")

    cap.release()
    writer.release()
    elapsed = time.time() - t_start

    print(f"\n[UC3 Demo] SUCCESS: Video written to {output_path}")
    print(f"  Total frames: {frame_seq}")
    print(f"  Frames with detections: {frames_with_detections}")
    print(f"  Vest detections: {vest_total}")
    print(f"  Helmet detections: {helmet_total}")
    print(f"  Worker person frames: {person_total}")
    print(f"  Duration: {frame_seq / demo_fps:.1f}s @ {demo_fps} fps (Processing time: {elapsed:.1f}s)")

if __name__ == "__main__":
    generate()
