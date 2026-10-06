#!/usr/bin/env python3
"""
generate_annotated_demos.py — Master orchestrator for generating and verifying
annotated demo videos for UC2, UC3, and UC4.
"""
import os
import sys
import subprocess
import time
import cv2

DEMO_DIR = os.path.abspath("test_data/demos")

def run_uc2():
    print("\n" + "="*60)
    print(">>> 1. GENERATING UC2 ANNOTATED DEMO VIDEO")
    print("="*60)
    # Run in UC2 container where pydantic, torch, and CV engine are installed
    subprocess.run(["docker", "cp", "test_data/videos/uc2.mp4", "innovision-platform-uc2_stub-1:/app/test_data/videos/"], check=True)
    subprocess.run(["docker", "cp", "scripts/generate_uc2_demo.py", "innovision-platform-uc2_stub-1:/app/scripts/"], check=True)
    subprocess.run(["docker", "exec", "innovision-platform-uc2_stub-1", "python3", "/app/scripts/generate_uc2_demo.py"], check=True)
    subprocess.run(["docker", "cp", "innovision-platform-uc2_stub-1:/app/test_data/demos/uc2_annotated.mp4", f"{DEMO_DIR}/uc2_annotated.mp4"], check=True)

def run_uc3():
    print("\n" + "="*60)
    print(">>> 2. GENERATING UC3 ANNOTATED DEMO VIDEO")
    print("="*60)
    subprocess.run(["docker", "cp", "test_data/videos/uc3.mp4", "innovision-platform-uc3_stub-1:/app/test_data/videos/"], check=True)
    subprocess.run(["docker", "cp", "scripts/generate_uc3_demo.py", "innovision-platform-uc3_stub-1:/app/scripts/"], check=True)
    subprocess.run(["docker", "exec", "innovision-platform-uc3_stub-1", "python3", "/app/scripts/generate_uc3_demo.py"], check=True)
    subprocess.run(["docker", "cp", "innovision-platform-uc3_stub-1:/app/test_data/demos/uc3_annotated.mp4", f"{DEMO_DIR}/uc3_annotated.mp4"], check=True)

def run_uc4():
    print("\n" + "="*60)
    print(">>> 3. GENERATING UC4 ANNOTATED DEMO VIDEO")
    print("="*60)
    subprocess.run(["docker", "cp", "test_data/videos/uc4.mp4", "innovision-platform-uc4_stub-1:/app/test_data/videos/"], check=True)
    subprocess.run(["docker", "cp", "scripts/generate_uc4_demo.py", "innovision-platform-uc4_stub-1:/app/scripts/"], check=True)
    subprocess.run(["docker", "exec", "innovision-platform-uc4_stub-1", "python3", "/app/scripts/generate_uc4_demo.py"], check=True)
    subprocess.run(["docker", "cp", "innovision-platform-uc4_stub-1:/app/test_data/demos/uc4_annotated.mp4", f"{DEMO_DIR}/uc4_annotated.mp4"], check=True)

def verify_video(name, path):
    print(f"\n--- Verifying {name} at {path} ---")
    if not os.path.exists(path):
        print(f"FAILED: File {path} does not exist!")
        return False
    size_mb = os.path.getsize(path) / (1024 * 1024)
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"FAILED: Cannot open {path} with cv2.VideoCapture!")
        return False
    fps = cap.get(cv2.CAP_PROP_FPS)
    frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    # Read first and middle frames to check valid pixel content
    ret1, f1 = cap.read()
    cap.set(cv2.CAP_PROP_POS_FRAMES, frames // 2)
    ret2, f2 = cap.read()
    cap.release()

    if not ret1 or f1 is None or f1.mean() < 5:
        print(f"FAILED: Frame 1 is empty or dark (mean brightness: {f1.mean() if f1 is not None else 0})")
        return False
    if not ret2 or f2 is None or f2.mean() < 5:
        print(f"FAILED: Middle frame is empty or dark")
        return False

    print(f"PASSED: {name}")
    print(f"  File size: {size_mb:.2f} MB")
    print(f"  Resolution: {w}x{h}")
    print(f"  Frames: {frames} @ {fps:.1f} fps")
    print(f"  Mean brightness: Frame 1={f1.mean():.1f}, Mid={f2.mean():.1f}")
    return True

def main():
    os.makedirs(DEMO_DIR, exist_ok=True)
    
    run_uc2()
    run_uc3()
    run_uc4()

    print("\n" + "="*60)
    print(">>> 4. FINAL VERIFICATION OF ANNOTATED DEMO VIDEOS")
    print("="*60)
    v2 = verify_video("UC2 Annotated Demo", f"{DEMO_DIR}/uc2_annotated.mp4")
    v3 = verify_video("UC3 Annotated Demo", f"{DEMO_DIR}/uc3_annotated.mp4")
    v4 = verify_video("UC4 Annotated Demo", f"{DEMO_DIR}/uc4_annotated.mp4")

    if v2 and v3 and v4:
        print("\nALL ANNOTATED DEMO VIDEOS GENERATED AND VERIFIED SUCCESSFULLY!")
    else:
        print("\nSOME DEMO VIDEOS FAILED VERIFICATION!")
        sys.exit(1)

if __name__ == "__main__":
    main()
