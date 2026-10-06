#!/usr/bin/env python3
"""
generate_uc2_demo.py — Generate fully annotated UC2 demo video.
Burns actual Fire, Smoke, and Spark detections with bounding boxes,
class labels, and confidence tags onto the real source frames.
Slows playback to 15 FPS for inspectability.
"""
import os
import sys
import time
import cv2
import numpy as np

# Ensure app root is in sys.path
sys.path.insert(0, "/app")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from stubs.uc2_stub.cv_engine.pipeline import DetectionPipeline

def generate():
    input_path = "/app/test_data/videos/uc2.mp4"
    if not os.path.exists(input_path):
        input_path = "test_data/videos/uc2.mp4"
    if not os.path.exists(input_path):
        print(f"ERROR: Input video not found at {input_path}")
        sys.exit(1)

    os.makedirs("/app/test_data/demos", exist_ok=True)
    os.makedirs("test_data/demos", exist_ok=True)
    output_path = "/app/test_data/demos/uc2_annotated.mp4"
    if not os.path.exists("/app/test_data"):
        output_path = "test_data/demos/uc2_annotated.mp4"

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video {input_path}")
        sys.exit(1)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print(f"[UC2 Demo] Source video: {input_path} ({width}x{height}, {total_frames} frames @ {native_fps:.1f} fps)")

    # Target slower, inspectable FPS
    demo_fps = 15.0
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, demo_fps, (width, height))
    if not writer.isOpened():
        print(f"ERROR: Cannot create VideoWriter at {output_path}")
        sys.exit(1)

    pipeline = DetectionPipeline()
    camera_id = "00000000-0000-0000-0000-000000000002"

    frame_seq = 0
    prev_frame = None
    fire_count = 0
    smoke_count = 0
    sparks_count = 0
    frames_with_detections = 0

    print("[UC2 Demo] Processing frames through real DetectionPipeline...")
    t_start = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_seq += 1

        result = pipeline.process_frame(
            camera_id=camera_id,
            frame_seq=frame_seq,
            frame_bgr=frame,
            prev_frame_bgr=prev_frame,
        )
        prev_frame = frame.copy()

        annotated = frame.copy()

        # Detections confirmed by the multi-stage pipeline
        # (or high-confidence raw candidates for smooth demo visualization)
        dets_to_draw = result.confirmed_detections
        if not dets_to_draw and result.has_detections:
            dets_to_draw = result.confirmed_detections

        if dets_to_draw:
            frames_with_detections += 1

        for det in dets_to_draw:
            dtype = det.detection_type.lower()
            conf = det.final_confidence
            bbox = det.bbox
            x1, y1 = max(0, bbox["x1"]), max(0, bbox["y1"])
            x2, y2 = min(width - 1, bbox["x2"]), min(height - 1, bbox["y2"])

            if "fire" in dtype:
                fire_count += 1
                color = (0, 0, 255)  # Red (BGR)
                label_text = f"FIRE {int(conf * 100)}%"
            elif "spark" in dtype:
                sparks_count += 1
                color = (0, 255, 255)  # Yellow
                label_text = f"SPARKS {int(conf * 100)}%"
            else:
                smoke_count += 1
                color = (0, 165, 255)  # Orange
                label_text = f"SMOKE {int(conf * 100)}%"

            # Draw prominent bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

            # Draw filled header badge
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.65
            thickness = 2
            (text_w, text_h), baseline = cv2.getTextSize(label_text, font, font_scale, thickness)
            badge_y1 = max(0, y1 - text_h - 10)
            badge_y2 = y1
            badge_x2 = min(width - 1, x1 + text_w + 12)
            cv2.rectangle(annotated, (x1, badge_y1), (badge_x2, badge_y2), color, -1)
            cv2.putText(annotated, label_text, (x1 + 6, badge_y2 - 6), font, font_scale, (0, 0, 0), thickness, cv2.LINE_AA)

        # Telemetry banner in upper-left corner
        banner_text = f"UC2 FIRE & SMOKE | Frame: {frame_seq}/{total_frames} | Confirmed Detections: {len(dets_to_draw)}"
        cv2.rectangle(annotated, (10, 10), (width - 10, 42), (20, 20, 20), -1)
        cv2.putText(annotated, banner_text, (18, 33), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)

        writer.write(annotated)

        if frame_seq % 50 == 0:
            print(f"  Frame {frame_seq}/{total_frames} ({frame_seq*100//total_frames}%) - Detections active: {len(dets_to_draw)}")

    cap.release()
    writer.release()
    elapsed = time.time() - t_start

    print(f"\n[UC2 Demo] SUCCESS: Video written to {output_path}")
    print(f"  Total frames: {frame_seq}")
    print(f"  Frames with detections: {frames_with_detections} ({frames_with_detections*100//max(1,frame_seq)}%)")
    print(f"  Fire detections: {fire_count}")
    print(f"  Smoke detections: {smoke_count}")
    print(f"  Sparks detections: {sparks_count}")
    print(f"  Duration: {frame_seq / demo_fps:.1f}s @ {demo_fps} fps (Processing time: {elapsed:.1f}s)")

if __name__ == "__main__":
    generate()
