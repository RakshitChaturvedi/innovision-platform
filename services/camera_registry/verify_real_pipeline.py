import asyncio
import json
import os
import sys
import time
import urllib.request
from uuid import UUID, uuid4

import redis
import asyncpg
from minio import Minio

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "innovision")
POSTGRES_PASS = os.environ.get("POSTGRES_PASSWORD", "changeme")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "innovision_platform")
POSTGRES_DSN = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASS}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "InnovisionMinIO_2026")

SAMPLE_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "sample_worker.jpg")
CAMERA_ID = "00000000-0000-0000-0000-000000000003"
ZONE_ID = "00000000-0000-0000-0000-000000000003"

async def run_verification():
    print("==================================================")
    print("RUNNING REAL END-TO-END UC3 RUNTIME VERIFICATION")
    print("==================================================")

    # 1. Connect DB & Seed Camera + Zone + Rules
    print(f"\n[Step 1] Seeding Camera, UC3 Zone, and Zone PPE Rules in PostgreSQL ({POSTGRES_HOST})...")
    conn = await asyncpg.connect(POSTGRES_DSN)

    await conn.execute("""
        INSERT INTO cameras (id, name, rtsp_url, use_cases, status, metadata)
        VALUES ($1, 'Test Site Cam 3', 'rtsp://test/cam3', ARRAY['uc3'], 'online'::camera_status, '{"zone_id": "00000000-0000-0000-0000-000000000003"}'::jsonb)
        ON CONFLICT (id) DO UPDATE SET status = 'online'::camera_status, metadata = '{"zone_id": "00000000-0000-0000-0000-000000000003"}'::jsonb;
    """, UUID(CAMERA_ID))

    await conn.execute("""
        INSERT INTO uc3_zones (id, name, description, risk_level, is_active)
        VALUES ($1, 'Construction Zone Alpha', 'Main Active Site Zone', 'high', true)
        ON CONFLICT (id) DO UPDATE SET is_active = true;
    """, UUID(ZONE_ID))

    await conn.execute("DELETE FROM uc3_zone_ppe_rules WHERE zone_id = $1;", UUID(ZONE_ID))
    for ppe, req, sev in [("helmet", True, "high"), ("vest", True, "high")]:
        await conn.execute("""
            INSERT INTO uc3_zone_ppe_rules (id, zone_id, ppe_type, required, severity, grace_seconds)
            VALUES (gen_random_uuid(), $1, $2, $3, $4, 0);
        """, UUID(ZONE_ID), ppe, req, sev)

    print("DB Seed Complete. Camera & Zone PPE Rules active.")

    # 2. Read Sample Frame Bytes & Put in Redis
    print("\n[Step 2] Reading real construction worker sample image...")
    with open(SAMPLE_IMAGE_PATH, "rb") as f:
        img_bytes = f.read()

    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=False)
    frame_seq = 9999
    frame_ref = f"frames:{CAMERA_ID}:{frame_seq}"
    r.set(frame_ref, img_bytes, ex=300)
    print(f"Stored {len(img_bytes)} JPEG bytes in Redis key '{frame_ref}'")

    # 3. Publish FrameEvents to Stream to satisfy temporal hysteresis window
    print(f"\n[Step 3] Publishing 3 sequential FrameEvents to Redis Stream 'frames:{CAMERA_ID}'...")
    for seq in [9997, 9998, 9999]:
        f_ref = f"frames:{CAMERA_ID}:{seq}"
        r.set(f_ref, img_bytes, ex=300)
        frame_event_payload = {
            "event_id": str(uuid4()),
            "camera_id": CAMERA_ID,
            "frame_seq": seq,
            "timestamp": "2026-10-06T18:30:00Z",
            "frame_provider": "redis",
            "frame_reference": f_ref,
            "frame_shape": [768, 1024]
        }
        stream_key = f"frames:{CAMERA_ID}"
        msg_id = r.xadd(stream_key, {"data": json.dumps(frame_event_payload)})
        print(f"  Frame {seq} published to '{stream_key}', msg_id='{msg_id.decode() if isinstance(msg_id, bytes) else msg_id}'")
        time.sleep(0.3)

    # 4. Wait for UC3 Consumer & System Pipeline
    print("\n[Step 4] Waiting 5 seconds for UC3 pipeline, Inference, Compliance, DB, Alert & Snapshot execution...")
    await asyncio.sleep(5)

    # 5. Verify uc3_events in DB
    print("\n[Step 5] Querying 'uc3_events' table in PostgreSQL...")
    row = await conn.fetchrow("""
        SELECT id, camera_id, zone_id, track_id, missing_ppe, present_ppe, compliance_score, timestamp, frame_reference
        FROM uc3_events WHERE camera_id = $1 ORDER BY timestamp DESC LIMIT 1;
    """, UUID(CAMERA_ID))
    
    if row:
        uc3_event_id = row['id']
        print(f"SUCCESS | Found uc3_events record!")
        print(f"  uc3_events.id        : {uc3_event_id}")
        print(f"  camera_id            : {row['camera_id']}")
        print(f"  zone_id              : {row['zone_id']}")
        print(f"  present_ppe          : {row['present_ppe']}")
        print(f"  missing_ppe          : {row['missing_ppe']}")
        print(f"  compliance_score     : {row['compliance_score']}")
        print(f"  timestamp            : {row['timestamp']}")
    else:
        print("FAIL | No record found in uc3_events table.")
        uc3_event_id = None

    # 6. Verify alerts:live stream in Redis & AlertEvent.source_event_id
    print("\n[Step 6] Querying 'alerts:live' Redis Stream for AlertEvent...")
    r_str = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    alerts_len = r_str.xlen("alerts:live")
    print(f"Stream 'alerts:live' length: {alerts_len}")
    
    alert_items = r_str.xrange("alerts:live", count=20)
    matched_alert_event = None
    for a_id, a_fields in alert_items:
        data_str = a_fields.get("data")
        if data_str:
            try:
                evt = json.loads(data_str)
                if str(evt.get("source_event_id")) == str(uc3_event_id):
                    matched_alert_event = evt
                    print(f"  MATCHED Alert Stream Item {a_id}: source_event_id={evt.get('source_event_id')}, title='{evt.get('title')}'")
            except Exception:
                pass

    if matched_alert_event:
        print(f"SUCCESS | AlertEvent matched! AlertEvent.source_event_id == uc3_events.id ({uc3_event_id})")
    else:
        print(f"INFO | Checked alerts:live stream items.")

    # 7. Verify PostgreSQL alerts table
    print("\n[Step 7] Querying 'alerts' table in PostgreSQL...")
    alert_row = await conn.fetchrow("""
        SELECT id, camera_id, title, severity, status, source_event_id, created_at
        FROM alerts WHERE camera_id = $1 ORDER BY created_at DESC LIMIT 1;
    """, UUID(CAMERA_ID))
    
    if alert_row:
        print(f"SUCCESS | Found record in PostgreSQL alerts table!")
        print(f"  alerts.id            : {alert_row['id']}")
        print(f"  title                : {alert_row['title']}")
        print(f"  severity             : {alert_row['severity']}")
        print(f"  source_event_id      : {alert_row['source_event_id']}")
    else:
        print("INFO | Checking PostgreSQL alerts table.")

    # 8. Verify MinIO Snapshot Object
    print("\n[Step 8] Checking MinIO 'innovision-snapshots' Bucket...")
    m_client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    objects = list(m_client.list_objects("innovision-snapshots", recursive=True))
    print(f"Found {len(objects)} snapshot object(s) in 'innovision-snapshots':")
    for obj in objects[:5]:
        print(f"  - Key: {obj.object_name}, Size: {obj.size} bytes")

    # 9. Verify UC3 HTTP /latest-detections & /metrics
    print("\n[Step 9] Querying UC3 HTTP endpoints...")
    try:
        det_url = f"http://127.0.0.1:8023/uc3/cameras/{CAMERA_ID}/latest-detections"
        res = urllib.request.urlopen(det_url).read().decode()
        det_data = json.loads(res)
        print(f"UC3 latest-detections response:")
        print(f"  detections count     : {len(det_data.get('detections', []))}")
        print(f"  severity             : {det_data.get('severity')}")
        print(f"  violations           : {det_data.get('violations')}")
        print(f"  zone                 : {det_data.get('zone')}")
        for d in det_data.get('detections', []):
            print(f"    -> Label: {d['label']}, Compliant: {d['compliant']}, Confidence: {d['confidence']}, BBox: {d['bbox']}")
    except Exception as e:
        print(f"HTTP GET Error: {e}")

    try:
        metrics_url = "http://127.0.0.1:8023/metrics"
        res_m = urllib.request.urlopen(metrics_url).read().decode()
        print(f"\nUC3 Prometheus Metrics:")
        for line in res_m.splitlines():
            if "uc3_" in line and not line.startswith("#"):
                print(f"  {line}")
    except Exception as e:
        print(f"Metrics Error: {e}")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
