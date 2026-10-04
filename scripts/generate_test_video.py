import os
import cv2
import numpy as np

def generate_video():
    video_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "test_data", "videos")
    os.makedirs(video_dir, exist_ok=True)
    video_path = os.path.join(video_dir, "uc4.mp4")

    # 10 seconds at 10 FPS = 100 frames
    fps = 10
    total_frames = 150
    width, height = 1280, 720

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(video_path, fourcc, fps, (width, height))

    if not out.isOpened():
        print(f"Error: Could not open VideoWriter for {video_path}")
        return

    print(f"Creating sample video: {video_path} ...")

    for i in range(total_frames):
        # Asphalt background
        frame = np.ones((height, width, 3), dtype=np.uint8) * 85

        # Road surface
        road_pts = np.array([[250, 80], [1030, 80], [1200, 720], [80, 720]], dtype=np.int32)
        cv2.fillPoly(frame, [road_pts], (45, 45, 45))

        # Lane dividers
        cv2.line(frame, (640, 80), (640, 720), (220, 220, 220), 4)

        # Vehicle moving down the lane (approaching camera)
        progress = (i % 60) / 60.0
        y = int(90 + progress * 480)
        w = int(90 + progress * 260)
        h = int(55 + progress * 160)
        x = int(720 - w // 2)

        # Vehicle body (Blue car)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (180, 60, 30), -1)
        # Windshield
        windshield_y1 = y + int(h * 0.15)
        windshield_y2 = y + int(h * 0.45)
        cv2.rectangle(frame, (x + int(w * 0.15), windshield_y1), (x + int(w * 0.85), windshield_y2), (40, 40, 40), -1)

        # License plate block (White rectangle with black text TS08EX1234)
        plate_w = int(w * 0.55)
        plate_h = max(18, int(h * 0.22))
        plate_x = x + (w - plate_w) // 2
        plate_y = y + int(h * 0.68)

        cv2.rectangle(frame, (plate_x, plate_y), (plate_x + plate_w, plate_y + plate_h), (255, 255, 255), -1)
        cv2.rectangle(frame, (plate_x, plate_y), (plate_x + plate_w, plate_y + plate_h), (0, 0, 0), 1)

        font_scale = max(0.4, progress * 0.9)
        thickness = 1 if font_scale < 0.6 else 2
        cv2.putText(
            frame,
            "TS08EX1234",
            (plate_x + 4, plate_y + int(plate_h * 0.75)),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (0, 0, 0),
            thickness,
        )

        out.write(frame)

    out.release()
    print(f"Success! Video created at: {video_path}")
    print(f"Size: {os.path.getsize(video_path)} bytes")

if __name__ == "__main__":
    generate_video()
