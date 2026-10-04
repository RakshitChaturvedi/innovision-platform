import os
os.environ["OMP_NUM_THREADS"] = "1"
# Force low-latency TCP transport and zero-buffering for OpenCV RTSP / Network Streams
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
    "rtsp_transport;tcp|"
    "fflags;nobuffer|"
    "flags;low_delay|"
    "max_delay;100000|"
    "reorder_queue_size;0|"
    "stimeout;3000000|"
    "buffer_size;1024000"
)
import cv2
import time
import numpy as np
import threading
import queue
from datetime import datetime, timezone
import torch
import uvicorn
from fastapi import FastAPI, HTTPException, Request, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import supervision as sv
from ultralytics import YOLO
from deep_sort_realtime.deepsort_tracker import DeepSort
from paddleocr import PaddleOCR

from database import SessionLocal
from models import Camera, CameraRole
from speed_estimator import SpeedEstimator
from utils import YOLO_CLASS_MAP, clean_plate, enhance_plate, extract_plate_candidates, get_mode, flush_session_to_db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

device_is_gpu = torch.cuda.is_available() or (hasattr(torch.backends, "mps") and torch.backends.mps.is_available())
if not device_is_gpu:
    # Maximize CPU parallelism for real-time inference
    cpu_cores = min(os.cpu_count() or 4, 8)
    torch.set_num_threads(cpu_cores)
    print(f"⚡ CPU mode enabled: allocated {cpu_cores} threads for PyTorch")

# Globals
model = None
lp_model = None
reader = None
models_loaded = False
models_lock = threading.Lock()

def load_models_background():
    global model, lp_model, reader, models_loaded
    with models_lock:
        if models_loaded:
            return
            
        while not models_loaded:
            try:
                print("⚡ Loading Global ML Models in background...")
                if torch.cuda.is_available() and os.path.exists("yolo11m.engine"):
                    model = YOLO("yolo11m.engine", task="detect")
                elif torch.cuda.is_available():
                    model = YOLO("yolo11m.pt")
                else:
                    # Best-in-class real-time CPU model (30-60+ FPS)
                    model = YOLO("yolo11n.pt")

                if os.path.exists("models/yolov8n_license_plate.pt"):
                    try:
                        lp_model = YOLO("models/yolov8n_license_plate.pt")
                    except Exception:
                        lp_model = None
                else:
                    lp_model = None

                # Initialize optimized PaddleOCR on CPU (disable MKLDNN collision with PyTorch OpenMP)
                reader = PaddleOCR(use_angle_cls=False, lang='en', show_log=False, enable_mkldnn=False)
                models_loaded = True
                print("✅ ML Models (YOLO + PaddleOCR) fully loaded!")
            except Exception as e:
                print(f"❌ Error loading models: {e}. Retrying in 4 seconds...")
                time.sleep(4)

# Trigger background load immediately on import
threading.Thread(target=load_models_background, daemon=True).start()

# Global OCR Queue (Throttled for CPU efficiency)
ocr_queue = queue.Queue(maxsize=12)
paddle_lock = threading.Lock()

def ocr_worker_loop():
    global lp_model, reader, models_loaded
    while True:
        try:
            item = ocr_queue.get()
            if item is None:
                break
            tid, crop, active_sessions = item
            
            # Fast discard: If vehicle disappeared or already reached confident consensus, skip OCR
            if tid not in active_sessions or len(active_sessions[tid].get("plate_reads", [])) >= 8:
                ocr_queue.task_done()
                continue
            
            if not models_loaded or reader is None:
                ocr_queue.task_done()
                continue
                
            plate_crops = []
            if lp_model:
                try:
                    lp_results = lp_model(crop, conf=0.25, verbose=False)
                    for r in lp_results:
                        for box in r.boxes:
                            px1, py1, px2, py2 = box.xyxy[0].tolist()
                            w, h = px2 - px1, py2 - py1
                            pad_x, pad_y = int(w * 0.1), int(h * 0.1)
                            px1 = max(0, int(px1) - pad_x)
                            py1 = max(0, int(py1) - pad_y)
                            px2 = min(crop.shape[1], int(px2) + pad_x)
                            py2 = min(crop.shape[0], int(py2) + pad_y)
                            p_crop = crop[py1:py2, px1:px2]
                            if p_crop.size > 0:
                                plate_crops.append(p_crop)
                except Exception:
                    pass

            # If deep LP detector did not find plate, use high-speed morphological localizer
            if not plate_crops:
                plate_crops = extract_plate_candidates(crop)

            for p_crop in plate_crops:
                if p_crop is None or p_crop.size == 0:
                    continue
                enhanced = enhance_plate(p_crop)
                with paddle_lock:
                    result = reader.ocr(enhanced, cls=False)
                if result and result[0]:
                    for line in result[0]:
                        text = line[1][0]
                        prob = line[1][1]
                        if prob > 0.30:
                            cleaned = clean_plate(text)
                            if cleaned and tid in active_sessions:
                                active_sessions[tid]["plate_reads"].append(cleaned)
                                active_sessions[tid]["plate_confidences"].append(float(prob * 100))
                                
            ocr_queue.task_done()
        except Exception as e:
            print(f"OCR Worker Error: {e}")

# Start OCR worker thread
threading.Thread(target=ocr_worker_loop, daemon=True).start()

def create_text_frame(text, width=1280, height=720):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.0
    thickness = 2
    (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)
    x = (width - tw) // 2
    y = (height + th) // 2
    cv2.putText(frame, text, (x, y), font, font_scale, (0, 0, 255), thickness, cv2.LINE_AA)
    ret, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
    return (b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

# Global lock for single-instance pipeline
pipeline_lock = threading.Lock()
# Event to signal the running stream to stop
stop_signal = threading.Event()

class PushBuffer:
    """Holds the most recent frame pushed via WebSocket or HTTP POST by a mobile device."""
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.last_rx = 0.0
        self.frame_count = 0
        self.dropped_count = 0
        self.fps_calc = 0.0
        self._fps_window = []

    def put_jpeg(self, jpeg_bytes: bytes) -> bool:
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            with self.lock:
                self.dropped_count += 1
            return False
        
        now = time.time()
        with self.lock:
            self.frame = frame
            self.last_rx = now
            self.frame_count += 1
            self._fps_window.append(now)
            cutoff = now - 2.0
            self._fps_window = [t for t in self._fps_window if t > cutoff]
            if len(self._fps_window) > 1:
                self.fps_calc = len(self._fps_window) / (self._fps_window[-1] - self._fps_window[0])
        return True

    def read(self):
        with self.lock:
            if self.frame is None or not self.alive:
                return False, None
            return True, self.frame.copy()

    @property
    def alive(self):
        return (time.time() - self.last_rx) < 5.0

    def isOpened(self):
        return True

    def get(self, prop):
        with self.lock:
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return self.frame.shape[1] if self.frame is not None else 1280
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return self.frame.shape[0] if self.frame is not None else 720
            if prop == cv2.CAP_PROP_FPS:
                return self.fps_calc if self.fps_calc > 0 else 30.0
        return 0

    def release(self):
        pass

push_buffer = PushBuffer()

@app.websocket("/api/camera/ws-push")
async def websocket_camera_push(websocket: WebSocket):
    """Ultra-low latency (<30ms) WebSocket stream receiver for mobile phones."""
    await websocket.accept()
    print("📱 Mobile WebSocket camera streaming connected!")
    try:
        while True:
            data = await websocket.receive_bytes()
            if data:
                push_buffer.put_jpeg(data)
                # Send ack so client can synchronize backpressure
                await websocket.send_text("ack")
    except WebSocketDisconnect:
        print("📱 Mobile WebSocket camera disconnected.")
    except Exception as e:
        print(f"📱 WebSocket stream error: {e}")

@app.post("/api/camera/push")
async def camera_push(request: Request):
    """HTTP Fallback push endpoint for mobile frames."""
    if request.headers.get("content-type", "").startswith("multipart/form-data"):
        form = await request.form()
        if "frame" in form:
            data = await form["frame"].read()
        else:
            return {"error": "empty frame"}
    else:
        data = await request.body()
        
    if not data:
        return {"error": "empty frame"}
        
    if not push_buffer.put_jpeg(data):
        return {"error": "could not decode frame"}
    return {"ok": True}

@app.get("/api/camera/push/status")
def camera_push_status():
    return {
        "alive": push_buffer.alive,
        "fps": round(push_buffer.fps_calc, 1),
        "total_frames": push_buffer.frame_count,
        "dropped_frames": push_buffer.dropped_count
    }

class FreshFrameReader:
    """Ultra-low latency, zero-frame-drop non-blocking video reader with auto-reconnect watchdog and RTSP/HLS fallback."""
    def __init__(self, src: str):
        self.src = src
        self.resolved_src = src
        # Auto-convert RTSP corp8 URLs to HTTPS HLS if needed
        if "live.corp8.cloud:8554/stream/" in src:
            stream_id = src.split("/stream/")[-1].split("/")[0]
            self.fallback_src = f"https://live.corp8.cloud/live/stream/{stream_id}/index.m3u8"
        else:
            self.fallback_src = None
            
        self.lock = threading.Lock()
        self.cap_lock = threading.Lock()
        self.frame = None
        self.ret = False
        self.running = True
        self.last_frame_time = time.time()
        self.width = 1280
        self.height = 720
        self.fps = 30.0
        self.frame_count = 0
        self.reconnect_count = 0
        self.status = "connecting"
        
        self.cap = None
        self._init_cap()
        
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()

    def _init_cap(self):
        with self.cap_lock:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None
            
            target = self.resolved_src
            print(f"[FreshFrameReader] 🔌 Connecting to {target}...")
            cap = cv2.VideoCapture(target, cv2.CAP_FFMPEG if hasattr(cv2, "CAP_FFMPEG") else cv2.CAP_ANY)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.cap = cap

    def _reader_loop(self):
        consecutive_fails = 0
        while self.running:
            with self.cap_lock:
                if not self.running:
                    break
                if self.cap is None or not self.cap.isOpened():
                    needs_reconnect = True
                    ret, frame = False, None
                else:
                    needs_reconnect = False
                    try:
                        # Rapid grab to drain internal FFmpeg packet buffer (guarantees zero lag)
                        ret = self.cap.grab()
                        if ret:
                            ret, frame = self.cap.retrieve()
                        else:
                            frame = None
                    except Exception:
                        ret, frame = False, None

            if needs_reconnect:
                self.status = "reconnecting"
                time.sleep(1.0)
                if self.reconnect_count > 1 and self.fallback_src and self.resolved_src != self.fallback_src:
                    print(f"[FreshFrameReader] 🔄 Switching to HLS stream fallback: {self.fallback_src}")
                    self.resolved_src = self.fallback_src
                self._init_cap()
                self.reconnect_count += 1
                continue

            now = time.time()

            if ret and frame is not None and frame.size > 0:
                consecutive_fails = 0
                h, w = frame.shape[:2]
                with self.lock:
                    self.ret = True
                    self.frame = frame
                    self.last_frame_time = now
                    self.width = w
                    self.height = h
                    self.frame_count += 1
                    self.status = "connected"
            else:
                consecutive_fails += 1
                if consecutive_fails > 25 or (now - self.last_frame_time > 4.0):
                    print(f"[FreshFrameReader] ⚠️ Stream stall on {self.resolved_src}. Reconnecting (attempt {self.reconnect_count + 1})...")
                    if self.fallback_src and self.resolved_src != self.fallback_src:
                        print(f"[FreshFrameReader] 🔄 Switching to HLS stream fallback: {self.fallback_src}")
                        self.resolved_src = self.fallback_src
                    self.status = "reconnecting"
                    self.reconnect_count += 1
                    self._init_cap()
                    consecutive_fails = 0
                    time.sleep(0.5)
                else:
                    time.sleep(0.005)

    def read(self):
        with self.lock:
            if not self.ret or self.frame is None:
                return False, None
            return True, self.frame.copy()

    def isOpened(self):
        with self.lock:
            return self.running and (self.frame is not None or (time.time() - self.last_frame_time < 15.0))

    def get(self, prop):
        with self.lock:
            if prop == cv2.CAP_PROP_FRAME_WIDTH:
                return self.width
            if prop == cv2.CAP_PROP_FRAME_HEIGHT:
                return self.height
            if prop == cv2.CAP_PROP_FPS:
                return self.fps
        return 0

    def release(self):
        self.running = False
        with self.cap_lock:
            if self.cap is not None:
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

def generate_frames(cam_id: str):
    # Enforce single instance
    if not pipeline_lock.acquire(blocking=False):
        # Signal the currently running stream to stop
        print("🛑 Another stream is running. Signaling it to stop...")
        stop_signal.set()
        # Wait up to 5 seconds for it to release the lock
        acquired = pipeline_lock.acquire(timeout=5.0)
        if not acquired:
            print("❌ Timeout waiting for previous stream to stop.")
            yield create_text_frame("ERROR: Another stream is currently running")
            return
            
    stop_signal.clear()
    
    db = SessionLocal()
    cam = db.query(Camera).filter(Camera.id == cam_id).first()
    if not cam:
        db.close()
        pipeline_lock.release()
        return

    name = cam.name
    video_source = cam.video_source
    role = cam.camera_role
    entry_line_norm = cam.entry_line_normalized
    exit_line_norm = cam.exit_line_normalized
    speed_polygon_normalized = cam.speed_polygon_normalized
    calibration_polygon_normalized = cam.calibration_polygon_normalized
    distance_between_lines_meters = cam.distance_between_lines_meters
    speed_limit = cam.speed_limit_kmh or 30
    db.close()

    is_network_stream = str(video_source).startswith(("http://", "https://", "rtsp://", "rtmp://"))
    if video_source == "push":
        cap = push_buffer
    elif is_network_stream:
        cap = FreshFrameReader(video_source)
    else:
        cap = cv2.VideoCapture(video_source)

    # Wait for first frame on network / push streams before evaluating isOpened
    if is_network_stream or video_source == "push":
        yield create_text_frame(f"Connecting to live stream: {name}...")
        for _ in range(120): # Wait up to 6 seconds for initial frames
            if stop_signal.is_set():
                break
            has_frame, _ = cap.read()
            if has_frame:
                break
            time.sleep(0.05)

    if not cap.isOpened():
        print(f"[{name}] ⚠️ Cannot open video source: {video_source}")
        if hasattr(cap, 'release'):
            cap.release()
        pipeline_lock.release()
        for _ in range(5):
            yield create_text_frame(f"ERROR: Cannot open video source: {video_source}")
            time.sleep(1.0)
        return

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    target_frame_time = 1.0 / (fps if fps and fps > 0 else 30.0)

    # Inference resolution downscaling for 4x CPU speedup (~25ms per frame)
    infer_w, infer_h = 640, 360
    scale_x = width / float(infer_w)
    scale_y = height / float(infer_h)

    speed_estimator = None
    cal_poly = calibration_polygon_normalized
    if not cal_poly and speed_polygon_normalized and len(speed_polygon_normalized) >= 3:
        xs = [p['x'] for p in speed_polygon_normalized]
        ys = [p['y'] for p in speed_polygon_normalized]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        cal_poly = [
            {"x": min_x, "y": min_y},
            {"x": max_x, "y": min_y},
            {"x": max_x, "y": max_y},
            {"x": min_x, "y": max_y}
        ]
        
    if cal_poly and len(cal_poly) == 4:
        speed_estimator = SpeedEstimator(
            polygon_normalized=cal_poly,
            distance_meters=distance_between_lines_meters or 15.0,
            frame_width=width,
            frame_height=height
        )
        
    speed_zone = None
    if speed_polygon_normalized and len(speed_polygon_normalized) >= 3:
        pts = np.array([[int(p['x']*width), int(p['y']*height)] for p in speed_polygon_normalized], dtype=np.int32)
        speed_zone = sv.PolygonZone(polygon=pts)

    entry_line = None
    if entry_line_norm:
        entry_line = sv.LineZone(
            start=sv.Point(x=int(entry_line_norm["x1"] * width), y=int(entry_line_norm["y1"] * height)),
            end=sv.Point(x=int(entry_line_norm["x2"] * width), y=int(entry_line_norm["y2"] * height)),
            triggering_anchors=[sv.Position.BOTTOM_CENTER]
        )
        
    exit_line = None
    if exit_line_norm:
        exit_line = sv.LineZone(
            start=sv.Point(x=int(exit_line_norm["x1"] * width), y=int(exit_line_norm["y1"] * height)),
            end=sv.Point(x=int(exit_line_norm["x2"] * width), y=int(exit_line_norm["y2"] * height)),
            triggering_anchors=[sv.Position.BOTTOM_CENTER]
        )

    # Ultra-fast real-time CPU ByteTracker (< 1ms per frame)
    tracker = sv.ByteTrack()
    active_sessions = {}
    frame_counter = 0

    # Detection frequency optimization: Run YOLO every 2nd frame on downscaled resolution
    DETECTION_INTERVAL = 2
    cached_detections = sv.Detections.empty()

    # Annotators
    box_annotator = sv.BoxAnnotator(color_lookup=sv.ColorLookup.TRACK)
    label_annotator = sv.LabelAnnotator(text_scale=0.5, text_padding=5, color_lookup=sv.ColorLookup.TRACK)
    zone_annotator = sv.PolygonZoneAnnotator(zone=speed_zone, color=sv.Color.YELLOW) if speed_zone else None

    try:
        # Wait for models to load, yield loading frames to keep stream alive
        while not models_loaded:
            if stop_signal.is_set():
                break
            yield create_text_frame("Loading AI Models... Please wait (3-5 mins on first run)")
            time.sleep(1.0)
            
        while cap.isOpened():
            t_frame_start = time.time()
            if stop_signal.is_set():
                print(f"[{name}] 🛑 Stop signal received. Exiting generator.")
                break

            ret, frame = cap.read()
            if not ret or frame is None:
                if is_network_stream or video_source == "push":
                    yield create_text_frame("📱 Waiting for live phone / RTSP stream... (Ensure camera is online)")
                    time.sleep(0.3)
                    continue
                else:
                    break

            frame_counter += 1

            # 1. Detection every Nth frame on CPU (or when tracks are empty)
            should_detect = (frame_counter % DETECTION_INTERVAL == 0) or (cached_detections.tracker_id is None or len(cached_detections.tracker_id) == 0)
            
            if should_detect:
                # Fast downscaled inference on 640x360
                infer_frame = cv2.resize(frame, (infer_w, infer_h), interpolation=cv2.INTER_LINEAR)
                results = model(infer_frame, classes=[1, 2, 3, 5, 7], conf=0.28, imgsz=640, verbose=False)
                raw_detections = sv.Detections.from_ultralytics(results[0])
                # Scale bounding boxes back to full native frame dimensions
                if raw_detections.xyxy is not None and len(raw_detections.xyxy) > 0:
                    raw_detections.xyxy[:, 0] *= scale_x
                    raw_detections.xyxy[:, 1] *= scale_y
                    raw_detections.xyxy[:, 2] *= scale_x
                    raw_detections.xyxy[:, 3] *= scale_y
                detections = tracker.update_with_detections(raw_detections)
                cached_detections = detections
            else:
                # Reuse active tracker state on intermediate frames (0 ms!)
                detections = cached_detections

            valid_tracks = []
            if detections.tracker_id is not None and len(detections.tracker_id) > 0:
                for idx, tid in enumerate(detections.tracker_id):
                    x1, y1, x2, y2 = detections.xyxy[idx]
                    x1, y1 = max(0, int(x1)), max(0, int(y1))
                    x2, y2 = min(width, int(x2)), min(height, int(y2))
                    cls_id = int(detections.class_id[idx]) if detections.class_id is not None else 2
                    v_type = YOLO_CLASS_MAP.get(cls_id, "Car")
                    valid_tracks.append((int(tid), x1, y1, x2, y2, v_type, idx))

            # 2. Update Speeds and OCR Queues
            ocr_jobs = []
            for tid, x1, y1, x2, y2, v_type, det_idx in valid_tracks:
                inst_speed = 0.0
                bottom_center = (int((x1 + x2) / 2), int(y2))
                
                # Check if inside speed zone
                in_zone = True
                if speed_zone:
                    in_zone = cv2.pointPolygonTest(speed_zone.polygon, bottom_center, False) >= 0

                if speed_estimator and in_zone:
                    safe_fps = fps if fps and fps > 0 else 30.0
                    inst_speed = speed_estimator.update_and_get_speed(tid, bottom_center, current_time=frame_counter / safe_fps)
                    
                if tid not in active_sessions:
                    active_sessions[tid] = {
                        "plate_reads": [], "plate_confidences": [], "vehicle_type": v_type,
                        "last_seen": frame_counter, "crossed_entry": False, "crossed_exit": False,
                        "entry_time": None, "exit_time": None, "max_speed_kmh": inst_speed,
                        "distance_between_lines_meters": distance_between_lines_meters or 15.0
                    }
                else:
                    active_sessions[tid]["last_seen"] = frame_counter
                    active_sessions[tid]["vehicle_type"] = v_type
                    if inst_speed > active_sessions[tid].get("max_speed_kmh", 0):
                        active_sessions[tid]["max_speed_kmh"] = inst_speed

                # Quality-based OCR queuing:
                # Only queue when a new detection occurs and vehicle has < 8 reads
                if should_detect and len(active_sessions[tid]["plate_reads"]) < 8:
                    w_box, h_box = x2 - x1, y2 - y1
                    if w_box >= 40 and h_box >= 30:
                        crop = frame[y1:y2, x1:x2]
                        if crop.size > 0:
                            gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                            sharpness = cv2.Laplacian(gray_crop, cv2.CV_64F).var()
                            if sharpness > 10.0:
                                ocr_jobs.append((tid, crop.copy(), sharpness, w_box * h_box))
            
            # Sort OCR jobs by sharpness and area, pick top 2 sharpest vehicles
            if ocr_jobs:
                ocr_jobs.sort(key=lambda j: (j[2], j[3]), reverse=True)
                for tid, crop, _, _ in ocr_jobs[:2]:
                    if tid in active_sessions and len(active_sessions[tid]["plate_reads"]) < 8:
                        try:
                            ocr_queue.put_nowait((tid, crop, active_sessions))
                        except queue.Full:
                            pass

            # 3. Database Flush (Stale Trackers)
            stale_tids = [t for t, data in active_sessions.items() if frame_counter - data["last_seen"] > 45]
            if stale_tids:
                for t in stale_tids:
                    flush_session_to_db(cam_id, t, dict(active_sessions.pop(t, {})), name, speed_limit)
                if speed_estimator:
                    speed_estimator.clean_stale_trackers(active_sessions.keys())

            # 4. Annotations and Line Zone Triggering
            if detections.tracker_id is not None and len(detections.tracker_id) > 0:
                labels = []
                for tid in detections.tracker_id:
                    tid = int(tid)
                    v_type = active_sessions.get(tid, {}).get("vehicle_type", "Vehicle")
                    max_speed = active_sessions.get(tid, {}).get("max_speed_kmh", 0.0)
                    reads = active_sessions.get(tid, {}).get("plate_reads", [])
                    confs = active_sessions.get(tid, {}).get("plate_confidences", [])
                    best_plate = get_mode(reads, confs) if reads else "---"
                    labels.append(f"#{tid} {v_type} | {max_speed:.1f} km/h | {best_plate}")
                
                frame = box_annotator.annotate(scene=frame, detections=detections)
                frame = label_annotator.annotate(scene=frame, detections=detections, labels=labels)

                if role in [CameraRole.entrance, CameraRole.bidirectional] and entry_line:
                    crossed_in, crossed_out = entry_line.trigger(detections)
                    for idx, tid in enumerate(detections.tracker_id):
                        tid = int(tid)
                        if (crossed_in[idx] or crossed_out[idx]):
                            if tid in active_sessions and not active_sessions[tid]["crossed_entry"]:
                                active_sessions[tid]["crossed_entry"] = True
                                active_sessions[tid]["entry_time"] = datetime.now(timezone.utc)
                    cv2.line(frame, (int(entry_line_norm["x1"] * width), int(entry_line_norm["y1"] * height)),
                             (int(entry_line_norm["x2"] * width), int(entry_line_norm["y2"] * height)), (0, 255, 0), 2)
                            
                if role in [CameraRole.exit, CameraRole.bidirectional] and exit_line:
                    crossed_in, crossed_out = exit_line.trigger(detections)
                    for idx, tid in enumerate(detections.tracker_id):
                        tid = int(tid)
                        if (crossed_in[idx] or crossed_out[idx]):
                            if tid in active_sessions and not active_sessions[tid]["crossed_exit"]:
                                active_sessions[tid]["crossed_exit"] = True
                                active_sessions[tid]["exit_time"] = datetime.now(timezone.utc)
                    cv2.line(frame, (int(exit_line_norm["x1"] * width), int(exit_line_norm["y1"] * height)),
                             (int(exit_line_norm["x2"] * width), int(exit_line_norm["y2"] * height)), (0, 0, 255), 2)

                if speed_polygon_normalized:
                    pts = np.array([[int(p['x'] * width), int(p['y'] * height)] for p in speed_polygon_normalized], np.int32)
                    cv2.polylines(frame, [pts], isClosed=True, color=(255, 255, 0), thickness=2)

            # 5. Playback Pacing for local video files
            if not is_network_stream and video_source != "push":
                elapsed = time.time() - t_frame_start
                delay = target_frame_time - elapsed
                if delay > 0.002:
                    time.sleep(delay)

            # 6. Stream Optimization: Resize display frame to 1280x720 max for silky smooth MJPEG browser decoding
            out_frame = frame
            if width > 1280 or height > 720:
                out_frame = cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_LINEAR)

            ret, buffer = cv2.imencode('.jpg', out_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

    except GeneratorExit:
        print(f"[{name}] 🛑 Client disconnected! Shutting down stream.")
    except Exception as e:
        print(f"[{name}] ❌ Stream Error: {e}")
    finally:
        print(f"[{name}] Cleaning up resources...")
        cap.release()
        for t, session_data in list(active_sessions.items()):
            flush_session_to_db(cam_id, t, session_data, name, speed_limit)
        active_sessions.clear()
        pipeline_lock.release()

@app.get("/api/stream/{cam_id}")
def stream_camera(cam_id: str, request: Request):
    return StreamingResponse(generate_frames(cam_id), media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/api/camera/frame")
def get_camera_frame():
    ret, frame = push_buffer.read()
    if ret and frame is not None:
        ret_enc, buffer = cv2.imencode('.jpg', frame)
        if ret_enc:
            from fastapi.responses import Response
            return Response(content=buffer.tobytes(), media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="No push frame available")

@app.get("/api/camera/stream-info")
def get_stream_info():
    return {
        "push_buffer": {
            "alive": push_buffer.alive,
            "fps": round(push_buffer.fps_calc, 1),
            "total_frames": push_buffer.frame_count,
            "dropped_frames": push_buffer.dropped_count,
            "resolution": f"{push_buffer.get(cv2.CAP_PROP_FRAME_WIDTH)}x{push_buffer.get(cv2.CAP_PROP_FRAME_HEIGHT)}" if push_buffer.alive else None
        }
    }


@app.post("/api/cameras/{cam_id}/source")
def update_camera_source(cam_id: str, url: str = Body(..., embed=True)):
    """
    Update the video source (e.g., to a mobile stream URL) for a camera.
    Example body: {"url": "http://192.168.1.100:8080/video"}
    """
    db = SessionLocal()
    try:
        cam = db.query(Camera).filter(Camera.id == cam_id).first()
        if not cam:
            raise HTTPException(status_code=404, detail="Camera not found")
        
        old_source = cam.video_source
        cam.video_source = url
        db.commit()
        
        # If the stream is running, stop it so it restarts with the new source
        if pipeline_lock.acquire(blocking=False):
            pipeline_lock.release()
        else:
            stop_signal.set()
            
        return {"message": "Camera source updated successfully", "old_source": old_source, "new_source": url}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.close()

