import cv2
import numpy as np
from ultralytics import YOLO

def main():
    video_path = 'test_data/videos/uc4.mp4'
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Video: {total_frames} frames, {fps} FPS, {w}x{h}, duration: {total_frames/fps:.2f}s")

    model = YOLO('yolo11n.pt')
    dist_m = 15.0 # meters
    zone_h = 0.75 * h # 0.2 to 0.95 of height

    active_tracks = {}
    next_tid = 1
    moving_vehicles = {}

    for f_idx in range(total_frames):
        ret, frame = cap.read()
        if not ret:
            break

        # Inference
        res = model(frame, classes=[1, 2, 3, 5, 7], conf=0.25, verbose=False)[0]
        curr_detections = []
        for b in res.boxes:
            coords = [int(v) for v in b.xyxy[0].tolist()]
            cls_name = model.names[int(b.cls[0])]
            cx = (coords[0] + coords[2]) // 2
            cy = coords[3] # bottom edge
            curr_detections.append((coords, cx, cy, cls_name))

        # Match tracks
        matched_tids = set()
        for coords, cx, cy, cls_name in curr_detections:
            best_tid = None
            best_dist = 90
            for tid, tdata in active_tracks.items():
                if tid in matched_tids:
                    continue
                last_f, lx, ly = tdata['history'][-1]
                dist = np.hypot(cx - lx, cy - ly)
                if dist < best_dist:
                    best_dist = dist
                    best_tid = tid

            if best_tid is not None:
                active_tracks[best_tid]['history'].append((f_idx, cx, cy))
                matched_tids.add(best_tid)
            else:
                active_tracks[next_tid] = {
                    'history': [(f_idx, cx, cy)],
                    'type': cls_name,
                    'start_frame': f_idx
                }
                matched_tids.add(next_tid)
                next_tid += 1

        # Check stale tracks
        stale = [t for t, d in active_tracks.items() if f_idx - d['history'][-1][0] > 15]
        for t in stale:
            hist = active_tracks[t]['history']
            if len(hist) >= 8:
                first_f, fx, fy = hist[0]
                last_f, lx, ly = hist[-1]
                dy = abs(ly - fy)
                dt = (last_f - first_f) / fps
                if dy > 60 and dt > 0.3:
                    speed_kmh = (dy / zone_h * dist_m) / dt * 3.6
                    moving_vehicles[t] = {
                        'type': active_tracks[t]['type'],
                        'start_s': round(first_f / fps, 1),
                        'end_s': round(last_f / fps, 1),
                        'start_frame': first_f,
                        'end_frame': last_f,
                        'speed_kmh': round(speed_kmh, 1),
                        'lane': 'Right Lane (Moving)' if fx > w * 0.45 else 'Left Lane (Curb)'
                    }
            del active_tracks[t]

    # Flush remaining
    for t, d in active_tracks.items():
        hist = d['history']
        if len(hist) >= 8:
            first_f, fx, fy = hist[0]
            last_f, lx, ly = hist[-1]
            dy = abs(ly - fy)
            dt = (last_f - first_f) / fps
            if dy > 60 and dt > 0.3:
                speed_kmh = (dy / zone_h * dist_m) / dt * 3.6
                moving_vehicles[t] = {
                    'type': d['type'],
                    'start_s': round(first_f / fps, 1),
                    'end_s': round(last_f / fps, 1),
                    'start_frame': first_f,
                    'end_frame': last_f,
                    'speed_kmh': round(speed_kmh, 1),
                    'lane': 'Right Lane (Moving)' if fx > w * 0.45 else 'Left Lane (Curb)'
                }

    cap.release()

    print("\n================== FULL VIDEO VEHICLE ANALYSIS ==================")
    print(f"Total moving vehicles detected in video: {len(moving_vehicles)}")
    idx = 1
    for t, info in moving_vehicles.items():
        if info['lane'] == 'Right Lane (Moving)':
            print(f"Vehicle {idx}: {info['type'].upper()} | Frames {info['start_frame']}..{info['end_frame']} ({info['start_s']}s -> {info['end_s']}s) | Speed: {info['speed_kmh']} km/h")
            idx += 1

if __name__ == '__main__':
    main()
