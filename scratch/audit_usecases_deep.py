import sys
import json
import os
sys.path.insert(0, os.getcwd())
import cv2
import numpy as np
import torch
from ultralytics import YOLO

results = {}

# ─── UC1 AUDIT ──────────────────────────────────────────────
print("Auditing UC1...")
uc1_model = YOLO("yolov8n.pt")
uc1_classes = uc1_model.names

# Test frame: sample_worker.jpg (1200x896)
img_worker = cv2.imread("services/uc3/sample_worker.jpg")
h1, w1 = img_worker.shape[:2]

res_uc1 = uc1_model.predict(source=img_worker, classes=[0], conf=0.25, verbose=False)
uc1_boxes = []
if res_uc1 and len(res_uc1) > 0 and res_uc1[0].boxes is not None:
    for b in res_uc1[0].boxes:
        xyxy = b.xyxy[0].tolist()
        xyxyn = b.xyxyn[0].tolist()
        conf = float(b.conf[0])
        # Foot contact point
        foot_x = (xyxyn[0] + xyxyn[2]) / 2.0
        foot_y = xyxyn[3]
        # Polygon: [0.70, 0.25] to [0.98, 0.50]
        in_zone = (0.70 <= foot_x <= 0.98) and (0.25 <= foot_y <= 0.50)
        uc1_boxes.append({
            "cls_id": int(b.cls[0]),
            "cls_name": uc1_classes.get(int(b.cls[0])),
            "conf": round(conf, 3),
            "xyxy_pixels": [round(v, 1) for v in xyxy],
            "xyxyn_normalized": [round(v, 4) for v in xyxyn],
            "foot_contact": [round(foot_x, 4), round(foot_y, 4)],
            "inside_restricted_zone": in_zone,
        })

results["uc1"] = {
    "checkpoint": "yolov8n.pt",
    "total_coco_classes": len(uc1_classes),
    "person_class_id": 0,
    "person_class_name": uc1_classes.get(0),
    "input_dims": [w1, h1],
    "detections_count": len(uc1_boxes),
    "inside_zone_count": sum(1 for b in uc1_boxes if b["inside_restricted_zone"]),
    "outside_zone_count": sum(1 for b in uc1_boxes if not b["inside_restricted_zone"]),
    "detections": uc1_boxes,
}

# ─── UC2 AUDIT ──────────────────────────────────────────────
print("Auditing UC2...")
uc2_model_path = "stubs/uc2_stub/cv_engine/models/best.pt"
uc2_model = YOLO(uc2_model_path)
uc2_classes = uc2_model.names

# Positive frame: uc2.mp4 frame 85
cap2 = cv2.VideoCapture("test_data/videos/uc2.mp4")
cap2.set(cv2.CAP_PROP_POS_FRAMES, 85)
ret2, f_fire = cap2.read()
cap2.release()
h2, w2 = f_fire.shape[:2]

res_uc2_pos = uc2_model.predict(source=f_fire, conf=0.25, verbose=False)
uc2_pos_boxes = []
if res_uc2_pos and len(res_uc2_pos) > 0 and res_uc2_pos[0].boxes is not None:
    for b in res_uc2_pos[0].boxes:
        xyxy = b.xyxy[0].tolist()
        xyxyn = b.xyxyn[0].tolist()
        uc2_pos_boxes.append({
            "cls_id": int(b.cls[0]),
            "cls_name": uc2_classes.get(int(b.cls[0])),
            "conf": round(float(b.conf[0]), 3),
            "xyxy_pixels": [round(v, 1) for v in xyxy],
            "xyxyn_normalized": [round(v, 4) for v in xyxyn],
            "coord_invariant_valid": (0 <= xyxy[0] < xyxy[2] <= w2) and (0 <= xyxy[1] < xyxy[3] <= h2),
        })

# Negative frame: solid wall/blank
blank_frame = np.full((h2, w2, 3), 128, dtype=np.uint8)
res_uc2_neg = uc2_model.predict(source=blank_frame, conf=0.25, verbose=False)
uc2_neg_count = len(res_uc2_neg[0].boxes) if (res_uc2_neg and res_uc2_neg[0].boxes is not None) else 0

results["uc2"] = {
    "checkpoint": uc2_model_path,
    "classes": uc2_classes,
    "input_dims": [w2, h2],
    "orientation": "portrait" if h2 > w2 else "landscape",
    "positive_detections_count": len(uc2_pos_boxes),
    "negative_blank_detections_count": uc2_neg_count,
    "all_coords_valid": all(b["coord_invariant_valid"] for b in uc2_pos_boxes),
    "sample_sparks_boxes": uc2_pos_boxes[:5],
}

# ─── UC3 AUDIT ──────────────────────────────────────────────
print("Auditing UC3...")
uc3_model_path = "services/uc3/models/best.pt"
uc3_model = YOLO(uc3_model_path)
uc3_classes = uc3_model.names

res_uc3 = uc3_model.predict(source=img_worker, conf=0.25, verbose=False)
uc3_boxes = []
if res_uc3 and len(res_uc3) > 0 and res_uc3[0].boxes is not None:
    for b in res_uc3[0].boxes:
        cid = int(b.cls[0])
        lbl = uc3_classes.get(cid, f"class_{cid}")
        uc3_boxes.append({
            "cls_id": cid,
            "label": lbl,
            "conf": round(float(b.conf[0]), 3),
            "box": [round(v, 4) for v in b.xyxyn[0].tolist()],
            "is_violation": lbl.lower().startswith("no-"),
        })

results["uc3"] = {
    "checkpoint": uc3_model_path,
    "classes_count": len(uc3_classes),
    "class_map": uc3_classes,
    "positive_detections_count": len(uc3_boxes),
    "violations_count": sum(1 for b in uc3_boxes if b["is_violation"]),
    "compliant_count": sum(1 for b in uc3_boxes if not b["is_violation"]),
    "detections": uc3_boxes,
}

# ─── UC4 AUDIT ──────────────────────────────────────────────
print("Auditing UC4...")
uc4_model = YOLO("yolo11n.pt")
uc4_all_classes = uc4_model.names

from stubs.uc4_stub.cv_engine.utils import YOLO_CLASS_MAP, YOLO_COCO_NAMES, YOLO_CATEGORY_MAP

cap4 = cv2.VideoCapture("test_data/videos/uc4.mp4")
cap4.set(cv2.CAP_PROP_POS_FRAMES, 30)
ret4, f_traffic = cap4.read()
cap4.release()
h4, w4 = f_traffic.shape[:2]

res_uc4 = uc4_model.predict(source=f_traffic, classes=[1, 2, 3, 5, 7], conf=0.25, verbose=False)
uc4_boxes = []
if res_uc4 and len(res_uc4) > 0 and res_uc4[0].boxes is not None:
    for b in res_uc4[0].boxes:
        cid = int(b.cls[0])
        uc4_boxes.append({
            "coco_cls_id": cid,
            "coco_name": YOLO_COCO_NAMES.get(cid, "unknown"),
            "vehicle_type": YOLO_CLASS_MAP.get(cid, "Vehicle"),
            "vehicle_category": YOLO_CATEGORY_MAP.get(cid, "vehicle"),
            "conf": round(float(b.conf[0]), 3),
            "box": [round(v, 4) for v in b.xyxyn[0].tolist()],
        })

results["uc4"] = {
    "checkpoint": "yolo11n.pt",
    "distinct_vehicle_classes_mapped": YOLO_CLASS_MAP,
    "input_dims": [w4, h4],
    "detections_count": len(uc4_boxes),
    "detections": uc4_boxes,
    "speed_calibrated_without_homography": False,
    "default_uncalibrated_speed_kmh": 0.0,
}

with open("scratch/audit_usecases_deep_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("UC1-UC4 DEEP AUDIT COMPLETE: scratch/audit_usecases_deep_results.json written.")
