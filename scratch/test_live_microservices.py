import httpx

for p, uc, cam in [
    (8021, "uc1", "test-cam-uc1"),
    (8022, "uc2", "test-cam-uc2"),
    (8023, "uc3", "test-cam-uc3"),
    (8024, "uc4", "test-cam-uc4"),
]:
    url = f"http://127.0.0.1:{p}/{uc}/cameras/{cam}/latest-detections"
    try:
        r = httpx.get(url, timeout=5.0)
        dets = r.json().get("detections", [])
        print(f"Port {p} ({uc.upper()}): HTTP {r.status_code}, Detections Count = {len(dets)}")
        if len(dets) > 0:
            print(f"   Sample detection: {dets[0].get('label')} (bbox: {dets[0].get('bbox')})")
    except Exception as e:
        print(f"Port {p} ({uc.upper()}) Error: {e}")
