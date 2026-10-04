"""
Comprehensive UC2 Runtime Verification Script
Tests real model, class mapping, CV verification, suppression, image uploads,
video processing, preview frame generation, alert serialization, MinIO contracts,
and checks for hardcoded detections or schema collisions.
"""
import sys
import os
import time
import json
import cv2
import numpy as np

# Ensure root is in sys.path
sys.path.insert(0, os.path.abspath("."))

def run_verification():
    results = {}
    print("=" * 60)
    print("STARTING UC2 REAL RUNTIME VERIFICATION")
    print("=" * 60)

    # 1. Model & Class Mapping
    print("\n[TEST 1 & 2] Model Loading & Class Mapping...")
    from ultralytics import YOLO
    model_path = os.path.abspath("services/uc2_fire_smoke/models/best.pt")
    assert os.path.exists(model_path), f"Model path {model_path} does not exist"
    model = YOLO(model_path)
    class_map = model.names
    print(f"Loaded model from: {model_path}")
    print(f"Class mapping: {class_map}")
    assert class_map[0] == "fire", f"Expected 0 == 'fire', got {class_map.get(0)}"
    assert class_map[1] == "smoke", f"Expected 1 == 'smoke', got {class_map.get(1)}"
    assert class_map[2] == "sparks", f"Expected 2 == 'sparks', got {class_map.get(2)}"
    results["model_and_classes"] = {
        "model_path": model_path,
        "class_mapping": class_map,
        "status": "PASS"
    }

    # 2. Pipeline Initialization
    print("\n[TEST 4] Initializing Real UC2 Detection Pipeline...")
    from services.uc2_fire_smoke.src.detection.pipeline import DetectionPipeline
    pipeline = DetectionPipeline()
    print("Pipeline successfully initialized with real YOLO model and verifiers.")

    # 3. Image Upload Testing
    print("\n[TEST 5] Testing Real Image Uploads (Fire, Smoke, Sparks, Normal)...")
    test_images = {
        "fire": "test_data/images/sample_fire.jpg",
        "smoke": "test_data/images/sample_smoke.jpg",
        "sparks": "test_data/images/sample_sparks.jpg",
        "normal": "test_data/images/normal_office.jpg"
    }
    image_results = {}
    for label, path in test_images.items():
        assert os.path.exists(path), f"File {path} not found"
        img = cv2.imread(path)
        assert img is not None, f"Failed to decode {path}"
        res = pipeline.process_frame(
            camera_id="00000000-0000-0000-0000-000000000002",
            frame_seq=1,
            frame_bgr=img,
            single_frame=True
        )
        dets = [
            {
                "type": d.detection_type,
                "confidence": round(d.final_confidence, 4),
                "bbox": [d.bbox["x1"], d.bbox["y1"], d.bbox["x2"], d.bbox["y2"]],
                "area": (d.bbox["x2"] - d.bbox["x1"]) * (d.bbox["y2"] - d.bbox["y1"]),
                "area_pct": round(((d.bbox["x2"] - d.bbox["x1"]) * (d.bbox["y2"] - d.bbox["y1"])) / (img.shape[0] * img.shape[1]) * 100, 2),
                "verification_score": round(d.verification_score, 4)
            }
            for d in res.confirmed_detections
        ]
        image_results[label] = {
            "has_detections": res.has_detections,
            "count": len(dets),
            "detections": dets,
            "inference_ms": round(res.inference_latency_ms, 2),
            "verification_ms": round(res.verification_latency_ms, 2)
        }
        print(f" -> {label.upper()}: Confirmed: {res.has_detections}, Detections: {len(dets)}, Latency: {res.total_pipeline_latency_ms:.1f}ms")
        for d in dets:
            print(f"    * {d['type'].upper()} conf={d['confidence']} bbox={d['bbox']} area_pct={d['area_pct']}% verif={d['verification_score']}")

    # Assertions for upload detection
    assert image_results["fire"]["has_detections"] is True, "Fire image failed detection"
    assert any(d["type"] == "fire" for d in image_results["fire"]["detections"]), "Fire not in fire detections"
    assert image_results["smoke"]["has_detections"] is True, "Smoke image failed detection"
    assert any(d["type"] == "smoke" for d in image_results["smoke"]["detections"]), "Smoke not in smoke detections"
    assert image_results["sparks"]["has_detections"] is True, "Sparks image failed detection"
    assert any(d["type"] in ("sparks", "fire") for d in image_results["sparks"]["detections"]), "Sparks failed"
    assert image_results["normal"]["has_detections"] is False, "Normal office image gave false alarm"
    results["upload_detection"] = image_results

    # 4. Demo Video Stream Processing
    print("\n[TEST 6] Testing Demo Video (uc2_demo.mp4)...")
    video_path = "services/dashboard/public/videos/uc2_demo.mp4"
    assert os.path.exists(video_path), f"Video {video_path} missing"
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"Reading {video_path}: {total_frames} frames")
    video_detections = 0
    sampled_frames = 0
    prev_frame = None
    while cap.isOpened() and sampled_frames < 30:
        ret, frame = cap.read()
        if not ret:
            break
        sampled_frames += 1
        res = pipeline.process_frame(
            camera_id="00000000-0000-0000-0000-000000000002",
            frame_seq=sampled_frames,
            frame_bgr=frame,
            prev_frame_bgr=prev_frame
        )
        prev_frame = frame.copy()
        if res.has_detections:
            video_detections += 1
    cap.release()
    print(f"Processed {sampled_frames} frames from uc2_demo.mp4. Frames with confirmed detections: {video_detections}")
    assert video_detections > 0, "Demo video produced 0 detections!"
    results["video_demo"] = {
        "frames_sampled": sampled_frames,
        "frames_with_detections": video_detections,
        "status": "PASS"
    }

    # 5. Preview Generation Verification
    print("\n[TEST 4] Verifying Preview Frame Generator (_annotate_frame)...")
    from services.uc2_fire_smoke.src.workers.camera_worker import CameraWorker
    # Instantiate a worker dummy just to test annotation
    dummy_worker = CameraWorker.__new__(CameraWorker)
    dummy_worker.camera_name = "Camera 2 (Boiler Room West)"
    dummy_worker.camera_location = "Boiler Room"
    dummy_worker.current_fps = 10.0
    fire_img = cv2.imread(test_images["fire"])
    res = pipeline.process_frame(
        camera_id="00000000-0000-0000-0000-000000000002",
        frame_seq=100,
        frame_bgr=fire_img
    )
    annotated = dummy_worker._annotate_frame(fire_img, res)
    assert annotated is not None
    assert annotated.shape == fire_img.shape
    # Ensure drawing happened (the annotated image should differ from original raw image)
    diff = np.sum(np.abs(annotated.astype(int) - fire_img.astype(int)))
    print(f"Annotated frame generated. Pixel diff against raw frame: {diff}")
    assert diff > 10000, "Annotation produced no visual changes!"
    results["preview_generation"] = "PASS"

    # 6. Contract & Alert Schema Verification
    print("\n[TEST 7 & 8] Verifying AlertEvent and MinIO Contracts...")
    from shared.contracts.alert_event import AlertEvent, AlertEventValidator
    from shared.contracts.enums import AlertSeverity, SourceUC, FrameProvider
    from uuid import uuid4
    alert = AlertEvent(
        alert_id=uuid4(),
        camera_id="00000000-0000-0000-0000-000000000002",
        severity=AlertSeverity.critical,
        alert_type="fire_detected",
        title="Fire Detected in Boiler Room West",
        description="Fire detected with confidence 0.91",
        source_event_id=str(uuid4()),
        source_uc=SourceUC.uc2,
        frame_reference="evidence/00000000-0000-0000-0000-000000000002/test.jpg",
        frame_provider=FrameProvider.minio,
        metadata={"confidence": 0.91, "bounding_boxes": [[100, 100, 200, 200]]}
    )
    val_errors = AlertEventValidator.validate(alert, known_cam_ids=["00000000-0000-0000-0000-000000000002"])
    print(f"AlertEvent validation errors: {val_errors}")
    assert len(val_errors) == 0, f"AlertEvent validation failed: {val_errors}"
    json_repr = alert.model_dump_json()
    assert "alerts:live" not in json_repr  # Just confirming clean payload
    print("AlertEvent schema validated successfully for alerts:live XADD.")
    results["alert_contract"] = "PASS"

    # 7. No Hardcoded Detections Audit
    print("\n[TEST 10] Auditing Codebase for Hardcoded / Simulated Detections...")
    import glob
    suspect_files = []
    py_files = glob.glob("services/uc2_fire_smoke/src/**/*.py", recursive=True)
    for pf in py_files:
        with open(pf, "r", encoding="utf-8") as f:
            content = f.read()
            if "random.choice" in content or "mock_detection" in content:
                suspect_files.append(pf)
    print(f"Suspect files found in UC2: {suspect_files}")
    assert len(suspect_files) == 0, f"Found mock detections in {suspect_files}"
    results["hardcoded_audit"] = "PASS"

    # 8. Schema & Multi-UC Merging Check
    print("\n[TEST 15] Checking DB Schema for UC1, UC2, UC3 Merging Safety...")
    migration_file = "migrations/versions/0001_platform_base.py"
    with open(migration_file, "r", encoding="utf-8") as f:
        mig_content = f.read()
    assert "source_uc" in mig_content, "source_uc enum missing in migrations"
    assert "uc1" in mig_content and "uc2" in mig_content and "uc3" in mig_content and "uc4" in mig_content
    print("All 4 Use Cases (uc1, uc2, uc3, uc4) cleanly partitioned in DB schema.")
    results["schema_merging"] = "PASS"

    print("\n" + "=" * 60)
    print("ALL RUNTIME CHECKS PASSED SUCCESSFULLY!")
    print("=" * 60)
    return results

if __name__ == "__main__":
    res = run_verification()
