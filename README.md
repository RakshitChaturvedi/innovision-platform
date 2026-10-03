# Innovision AI Surveillance & Incident Platform

Integrated Video Ingestion, Analytics (UC2 Fire/Smoke/Sparks, UC3/PART PPE Safety), Detection Module, Alert Management, and Incident Escalation Platform.

---

## 🚀 ONE-COMMAND FRESH SYSTEM STARTUP (Zero Host Dependencies)

A completely new machine with **only Git and Docker** can run the entire platform with a single command. **No host Python, Node.js, PostgreSQL, Redis, or MinIO required.**

### 1. Prerequisites
- [Git](https://git-scm.com/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows/macOS) or Docker Engine + Docker Compose v2 (Linux)

### 2. Clone & Start

```bash
# Step 1: Clone the repository (final branch)
git clone -b final https://github.com/RakshitChaturvedi/innovision-platform.git
cd innovision-platform

# Step 2: Create environment configuration
# Windows:
copy .env.example .env
# Linux / macOS:
cp .env.example .env

# Step 3: Run the One-Command Launcher
# Windows (cmd/PowerShell):
.\run.bat
# Linux / macOS:
chmod +x run.sh && ./run.sh
# Or directly with Docker Compose:
docker compose up -d --build
```

### 3. What Happens Automatically on First Run:
1. **Infrastructure Provisioning**: PostgreSQL 16 (pgvector), Redis 7, MinIO S3, Nginx, Prometheus, Grafana, and Loki start with healthchecks.
2. **Automated Platform Bootstrap (`platform_init`)**:
   - Runs Alembic migrations (`alembic upgrade head`) to create tables, indexes, and user schemas.
   - Reconciles seed cameras (pointing to built-in demo video files e.g. `/app/test_data/videos/uc2.mp4` for UC2).
   - Automatically provisions all MinIO buckets (`innovision-frames`, `innovision-snapshots`, `innovision-evidence`, `innovision-reports`).
   - Automatically initializes all Redis streams and consumer groups (`alerts:live`, `incidents:live`, `notifications:live`, `uc2_fire_smoke_cg`).
3. **Core Services**: `auth`, `camera_registry`, `ingestion`, `alert_management`, `incident_management`, `notification`, `audit`, and `reporting_worker` start.
4. **Active Analytics Engines**:
   - **UC1 / PART**: Worker Count & Person Detection (`uc1_worker`) on port **8021**.
   - **UC2**: Real Fire, Smoke, and Sparks YOLOv8 Analytics & Detection Module (`uc2_fire_smoke`) on port **8030**.
   - **UC3 / PART**: PPE Compliance & Industrial Safety Worker (`uc3_worker`) on port **8031**.
5. **Operator Dashboard**: React Web UI compiled in Docker and served on port **3000** with Detection Module UI and live hazard monitoring.

### 4. Service URL Cheat Sheet

| Service | Host URL | Description | Default Credentials |
| :--- | :--- | :--- | :--- |
| **Operator Dashboard** | `http://localhost:3000` | Unified React SOC Dashboard | `admin@innovision.com` / `changeme` |
| **Detection Module UI** | `http://localhost:3000/detection` | Interactive Image, Video & RTSP detection | None |
| **UC1 Person Counter UI** | `http://localhost:8021` | Live person bounding boxes & count | None |
| **UC2 Fire/Smoke API** | `http://localhost:8030/health` | Fire, Smoke, Sparks Status & Metrics | None |
| **UC2 Live Stream Preview** | `http://localhost:8030/preview/00000000-0000-0000-0000-000000000002` | Live OpenCV annotated visual feed | None |
| **UC3 / PART PPE Safety API** | `http://localhost:8031/health` | PPE Compliance inspection & stream | None |
| **Camera Ingestion API** | `http://localhost:8020/health` | Stream decoders & frame cache | None |
| **Camera Registry API** | `http://localhost:8011/docs` | Swagger API for cameras & RTSP URLs | Bearer JWT |
| **Alert Management API** | `http://localhost:8010/docs` | Alert ingestion & persistence API | Bearer JWT |
| **MinIO Console** | `http://localhost:9001` | S3 Object Storage Browser | `minioadmin` / `changeme` |
| **Grafana Dashboards** | `http://localhost:3001` | System telemetry & alerts | `admin` / `changeme` |
| **Prometheus Metrics** | `http://localhost:9090` | Time-series scraper | None |

---

# Architecture Overview

```text
Camera Registry (Port 8011)
      │
      │ camera configuration & RTSP URLs
      ▼
Ingestion Service (Port 8020)
      │
      ├── FFmpeg / Stream Decoder (640x480 Downsampling)
      ├── Frame Sampler & JPEG Encoder
      ├── Redis Frame Cache (frames:{camera_id})
      └── MinIO Frame Store (innovision-frames)
                │
         ┌──────┴────────────────────────────────┐
         ▼                                       ▼
   UC2 Fire/Smoke (Port 8030)              UC3 / PART (Port 8031)
   YOLO Fire/Smoke/Sparks + Detection       PPE Compliance & Safety
   (Image, Video, RTSP APIs)                     │
         │                                       │
         └───────────────────────┬───────────────┘
                                 │ AlertEvent JSON
                                 ▼
                     Redis Stream: alerts:live
                                 │
                                 ▼
                   Alert Management (Port 8010)
                                 │
                     ┌───────────┴───────────┐
                     ▼                       ▼
            PostgreSQL Database      WebSocket / Socket.IO
            (alerts, incidents)      (Namespace: /alerts)
```
                                             │
                                             ▼
                                  Operator Dashboard (Port 3000)
```

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
