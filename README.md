# Innovision — Ingestion Layer

## Overview

The ingestion layer is responsible for taking camera/video streams, processing them into sampled JPEG frames, caching/storing those frames, and publishing `FrameEvent`s for downstream use cases.

```text
Camera Registry
      │
      │ camera configuration
      ▼
Ingestion Service
      │
      ├── FFmpeg / Stream Decoder
      ├── Frame Sampler
      ├── JPEG Encoder
      ├── Redis Frame Cache
      ├── MinIO Frame Store
      └── Redis Stream Publisher
                │
                ▼
        frames:{camera_id}
                │
        ┌───────┴───────┐
        ▼               ▼
      UC1-v2          Other UCs
        │
        ▼
   YOLO Person Detection
        │
        ▼
     Demo Dashboard
```

---

# 1. Prerequisites

You need:

* Docker
* Docker Compose
* Git
* A `.env` file in the project root

The demo currently uses a test video rather than a physical RTSP camera.

---

# 2. Project structure

Relevant services:

```text
innovision-platform/
│
├── .env
│
├── infra/
│   ├── docker-compose.yml
│   └── docker-compose.stubs.yml
│
├── services/
│   ├── camera_registry/
│   ├── ingestion/
│   └── uc1_v2_stub/
│
└── test_data/
    └── videos/
        └── uc1.mp4
```

The exact paths may differ depending on the current repository layout.

---

# 3. Start the platform

From the project root:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  up -d
```

To watch ingestion logs:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  logs -f ingestion
```

You should see something similar to:

```text
ingestion_service_starting
redis_connected
camera_registry_client_initialized
camera_registry_active_cameras count=1
camera_ingestion_started
camera_manager_started
ingestion_service_started
stream_decoder_started
camera_stream_connected
```

---

# 4. Check service health

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  ps
```

The services should be running.

You can also check ingestion:

```bash
curl http://localhost:8020/health
```

Expected:

```json
{
  "status": "ok"
}
```

---

# 5. Camera Registry

Camera Registry provides the camera configuration used by ingestion.

Check registered cameras:

```bash
curl http://localhost:8011/cameras
```

For the UC1 demo, there should be a test camera similar to:

```text
00000000-0000-0000-0000-000000000001
```

The camera configuration determines:

* camera ID
* video/RTSP source
* FPS
* processing profile
* assigned use cases

---

# 6. Start/verify the UC1-v2 demo

The UC1-v2 stub consumes:

```text
frames:{camera_id}
```

from Redis Streams.

It then:

```text
FrameEvent
    ↓
Redis frame cache
    ↓
JPEG decode
    ↓
YOLOv8n
    ↓
person detection
```

Check its logs:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  logs -f uc1_v2_stub
```

A successful consumer should produce messages indicating that frames are being processed.

---

# 7. Verify Redis frame events

Get the latest frame event:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  exec redis redis-cli \
  XREVRANGE frames:00000000-0000-0000-0000-000000000001 + - COUNT 1
```

You should see a `FrameEvent` containing fields such as:

```json
{
  "camera_id": "00000000-0000-0000-0000-000000000001",
  "frame_seq": 2708,
  "frame_provider": "redis",
  "frame_reference": "frame:00000000-0000-0000-0000-000000000001:2708",
  "frame_shape": [1080, 1920]
}
```

---

# 8. Verify the actual frame exists in Redis

Take the `frame_seq` from the previous command.

For example:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  exec redis redis-cli \
  EXISTS frame:00000000-0000-0000-0000-000000000001:2708
```

Expected:

```text
(integer) 1
```

Check its TTL:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  exec redis redis-cli \
  TTL frame:00000000-0000-0000-0000-000000000001:2708
```

A positive value means the frame is currently in the Redis hot-path cache.

---

# 9. Check the Redis Stream length

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  exec redis redis-cli \
  XLEN frames:00000000-0000-0000-0000-000000000001
```

The stream is capped, so the number should remain around its configured maximum rather than growing indefinitely.

---

# 10. UC1-v2 Demo Dashboard

The UC1-v2 stub exposes the detection result through its demo interface.

Open the exposed UC1-v2 URL/port configured in:

```text
infra/docker-compose.stubs.yml
```

The dashboard should display information similar to:

```text
INNOVISION — UC1

PEOPLE DETECTED
       1

CAMERA
00000000-0000-0000-0000-000000000001

FRAME
1020

RESOLUTION
1920x1080

JPEG SIZE
209,247 bytes

CACHE
hit

CACHE FETCH
1.19 ms

YOLO DETECTION
99.99 ms

FRAMES PROCESSED
615

CACHE MISSES
910

STATUS
RUNNING
```

This demonstrates the complete ingestion → analytics path.

---

# 11. What the demo proves

The demo is not simply testing YOLO.

It demonstrates:

```text
Camera Registry
      ↓
Camera discovery
      ↓
Camera ingestion
      ↓
FFmpeg decoding
      ↓
Frame sampling
      ↓
JPEG encoding
      ↓
Redis frame cache
      ↓
FrameEvent
      ↓
Redis Stream
      ↓
UC1-v2 consumer
      ↓
Redis frame retrieval
      ↓
JPEG decoding
      ↓
YOLOv8n
      ↓
Person count
      ↓
Dashboard
```

---

# 12. Useful debugging commands

### Ingestion logs

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  logs -f ingestion
```

### UC1-v2 logs

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  logs -f uc1_v2_stub
```

### Camera Registry logs

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  logs -f camera_registry
```

### Redis CLI

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  exec redis redis-cli
```

---

# 13. Stopping the platform

To stop the containers **without deleting them**:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  stop
```

Start them again:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  start
```

This is preferable during development because you don't need to rebuild the images.

---

# 14. Rebuild only when code/dependencies require it

For normal source-code changes, if your services use bind mounts, you generally don't need to rebuild.

If you changed a `requirements.txt`:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  build <service>
```

For example:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  build uc1_v2_stub
```

Then:

```bash
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  up -d uc1_v2_stub
```

You do **not** need to rebuild unrelated services.

---

# 15. Quick demo procedure

For a presentation/demo, the shortest procedure is:

```bash
# 1. Start
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  up -d

# 2. Watch ingestion
docker compose \
  --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  logs -f ingestion
```

Wait for:

```text
camera_registry_active_cameras count=1
camera_stream_connected
```

Then open the **UC1-v2 dashboard**.

You should be able to show:

```text
Camera
  ↓
Ingestion
  ↓
Redis
  ↓
UC1-v2
  ↓
YOLO
  ↓
People detected
```

That is the intended end-to-end demo.
