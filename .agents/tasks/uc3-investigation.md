# UC3 PPE Detection Pipeline — Investigation Report

## Executive Summary

The UC3 PPE Detection pipeline **is fully implemented and correctly wired** in the
innovision-platform. The intended flow —

```
Camera → Ingestion → Redis frames:{camera_id} → UC3 PPE Detection
       → AlertEvent → Redis alerts:live → Alert Management
       → PostgreSQL → Alerts API → Frontend Alerts page
```

— exists end-to-end. However, **the platform currently has no `uc3_stub` (the UC3
service) in the main `docker-compose.yml`**. It only exists in
`docker-compose.stubs.yml`. Running `make setup` alone will therefore leave the
UC3 detection stage silent. You must run `make up-stubs` (or `make setup2`) to
bring the UC3 service online alongside the rest of the platform. There is also
one missing frontend env-var (`VITE_UC3_API_URL`) and a missing compliance
endpoint (`/uc3/compliance/ppe-summary`) that affects reporting but not
alert delivery.

---

## 1. Services Inventory

| Service | Location | Role |
|---------|----------|------|
| `ingestion` | `services/ingestion/` | Reads cameras from Camera Registry, decodes RTSP streams, encodes frames as JPEG, stores them in Redis (`frame:{camera_id}:{seq}`) and MinIO, publishes `FrameEvent` to `frames:{camera_id}` Redis Stream |
| `camera_registry` | `services/camera_registry/` | PostgreSQL-backed registry of cameras; exposes `/cameras` REST API and `/cameras/by-uc/{uc_id}` for UC service discovery |
| `alert_management` | `services/alert_management/` | Consumes `alerts:live` Redis Stream (consumer group `alert_management_group`), persists to PostgreSQL `alerts` table, pushes real-time updates over Socket.IO, exposes `/alerts` REST API |
| `auth` | `services/auth/` | JWT-based auth service; issues access/refresh tokens; RBAC enforcement |
| `audit` | `services/audit/` | Append-only audit log writer to PostgreSQL |
| `incident_management` | `services/incident_management/` | Manages incidents triggered from high/critical alerts |
| `notification` | `services/notification/` | Email/push notifications via SMTP; consumes `notifications:live` stream |
| `reporting` | `services/reporting/` | Celery-based async PDF report generation; calls per-UC compliance endpoints |
| `dashboard` | `services/dashboard/` | React/Vite frontend (TypeScript). Has Alerts page, Camera Detail with live feed + detection overlay |
| **`uc3_stub`** | **`stubs/uc3_stub/`** | **UC3 real PPE detection service** — reads frames, runs YOLO inference, publishes `AlertEvent` to `alerts:live` |

---

## 2. UC3 PPE Detection Service

### Location
`stubs/uc3_stub/main.py` — despite being in the `stubs/` folder, this is the
**real, full ML inference service** (uses a trained `best.pt` YOLO model,
ByteTrack, multi-stage presence cascade). The name is historical.

### Redis Input
- Subscribes to **`frames:{camera_id}`** Redis Streams via consumer group
  `uc3_compliance_group` / consumer `uc3_worker_1`.
- Camera IDs are discovered at startup from Camera Registry:
  `GET {CAMERA_REGISTRY_URL}/by-uc/uc3`
  (falls back to `TEST_CAMERA_ID` = `00000000-0000-0000-0000-000000000003`).
- Each `frames:{camera_id}` message contains a JSON `FrameEvent`; the service
  fetches the actual JPEG bytes from `frame:{camera_id}:{frame_seq}` (Redis key
  written by `FrameCache.put`).

**Evidence:** `stubs/uc3_stub/main.py` lines `run_uc3_pipeline()`:
```python
stream_names = [f"frames:{cid}" for cid in camera_ids]
response = await redis_client.xreadgroup(
    groupname=REDIS_CONSUMER_GROUP,
    consumername=REDIS_CONSUMER_NAME,
    streams=stream_dict, count=10, block=1000,
)
```
And frame fetch:
```python
jpeg_bytes = await redis_client.get(frame_event.frame_reference)
```

### Redis Output on Violation
- Publishes **`AlertEvent`** to **`alerts:live`** Redis Stream via
  `shared/platform_client/alert_publisher.py`:
  ```python
  await self._redis.xadd(ALERTS_LIVE_STREAM, {"data": payload})
  # ALERTS_LIVE_STREAM = "alerts:live"
  ```
- Also dead-letters failed publishes to `alerts:dead_letter`.

### AlertEvent Structure
`shared/contracts/alert_event.py` — fields include:
- `alert_type = "ppe_violation"`
- `source_uc = SourceUC.UC3`
- `severity` = `HIGH` (multiple violations) or `MEDIUM` (single)
- `source_event_id` = the originating `FrameEvent.event_id`
- `frame_reference` = the Redis cache key (e.g. `frame:{camera_id}:{seq}`)
- `metadata.missing_ppe`, `metadata.track_id`, `metadata.confidence`

### Detection Logic
- **Model**: `stubs/uc3_stub/models/best.pt` (custom trained YOLO for PPE classes)
- **Presence Cascade**: Motion Gate → Person Gate (`yolo11n.pt`) → Mannequin Gate → Primary YOLO+ByteTrack
- **Compliance Engine**: `stubs/uc3_stub/src/compliance.py` — hybrid spatial
  association (distance + IoU + vertical position), temporal sliding-window
  hysteresis (3-second window, 60% raise / 30% clear thresholds).
- Runs inference in a thread pool (`asyncio.to_thread`) to not block the event loop.

---

## 3. Ingestion Service

### Location
`services/ingestion/`

### What it does
1. Fetches active cameras from Camera Registry on startup.
2. For each camera, starts a `CameraIngestionTask` (RTSP → `StreamDecoder` → `FrameSampler` → `JpegEncoder`).
3. **Redis cache**: `FrameCache.put()` writes JPEG bytes to key `frame:{camera_id}:{frame_seq}` with a 20-second TTL (`FRAME_CACHE_TTL_S=20`).
4. **MinIO store**: uploads the same JPEG to `innovision-frames/{camera_id}/{frame_seq:08d}.jpg`.
5. **Redis Stream**: `FramePublisher.publish()` writes a `FrameEvent` JSON to **`frames:{camera_id}`** (XADD, MAXLEN 1000).

**Evidence:** `services/ingestion/src/publisher.py`:
```python
stream_key = f"frames:{camera_id}"
msg_id = await self._redis.xadd(stream_key, {"data": payload}, maxlen=settings.stream_maxlen, ...)
```

**Key match confirmed**: UC3 reads `frames:{camera_id}` → Ingestion writes `frames:{camera_id}` ✅  
**Frame reference match**: UC3 fetches `frame_event.frame_reference` (the Redis key returned by `FrameCache.put`) → Ingestion sets `frame_reference = cache_key = f"frame:{camera_id}:{frame_seq}"` ✅

---

## 4. Alert Management Service

### Redis Consumption
- Subscribes to **`alerts:live`** stream via consumer group `alert_management_group`.
  
**Evidence:** `services/alert_management/src/config.py`:
```python
alerts_stream: str = "alerts:live"
consumer_group: str = "alert_management_group"
```
`services/alert_management/src/consumer.py` — `xreadgroup` loop with full
dead-letter, XAUTOCLAIM retry (idle > 60s), and MAX_DELIVERY_COUNT=5.

### PostgreSQL Persistence
- `services/alert_management/src/persistence.py` — `insert_alert()` writes to the
  `alerts` table with `ON CONFLICT (alert_id) DO NOTHING` (deduplication).
- Schema defined in `migrations/versions/0001_platform_base.py` —
  `alerts` table has all required columns: `alert_id`, `camera_id`, `source_uc`,
  `alert_type`, `severity`, `title`, `description`, `source_event_id`,
  `frame_reference`, `frame_provider`, `status`, `metadata`, `created_at`.

### Alerts API
`services/alert_management/src/router.py` — `/alerts` REST endpoints:
- `GET /alerts` — paginated, filterable by `source_uc`, `severity`, `status`, `camera_id`
- `PATCH /alerts/{id}/acknowledge` and `PATCH /alerts/{id}/resolve`
- `GET /alerts/{id}/snapshot` — presigned MinIO URL for evidence image
- `GET /alerts/status-counts`, `/alerts/unacknowledged`, `/alerts/count`
- Socket.IO on `/alerts` namespace — real-time push of `alert:new` and `alert:updated` events

---

## 5. Docker Compose Analysis

### Main Compose (`infra/docker-compose.yml`)

Services defined: `postgres`, `redis`, `minio`, `nginx`, `prometheus`, `grafana`,
`loki`, `alert_management`, `camera_registry`, `ingestion`, `auth`,
`alert_management_worker`, `audit`, `incident_management`, `notification`,
`mailhog` (dev profile), `reporting_worker`.

**❌ UC3 (`uc3_stub`) is NOT in `docker-compose.yml`.**

### Stubs Compose (`infra/docker-compose.stubs.yml`)

Defines: `uc1_stub`, `uc2_stub`, **`uc3_stub`**, `uc4_stub`, `uc1_v2_stub`.

UC3 stub configuration:
```yaml
uc3_stub:
  build:
    context: ..
    dockerfile: stubs/uc3_stub/Dockerfile
  ports:
    - "8023:8023"
  env_file: ../.env
  environment:
    UC_ID: uc3
    REDIS_HOST: redis
    REDIS_PORT: 6379
    CAMERA_REGISTRY_URL: http://camera_registry:8011
    TEST_CAMERA_ID: "00000000-0000-0000-0000-000000000003"
    REDIS_CONSUMER_GROUP: uc3_compliance_group
    REDIS_CONSUMER_NAME: uc3_worker_1
    PPE_CONF_THRESHOLD: "0.35"
    PPE_IOU_THRESHOLD: "0.45"
    PPE_VIOLATION_WINDOW_SECONDS: "3.0"
  depends_on:
    - redis, postgres, camera_registry, ingestion
  healthcheck:
    test: curl -f http://localhost:8023/health
```

### Nginx (`infra/nginx/nginx.conf`)
```nginx
location /uc3 { set $u http://uc3_stub:8023; proxy_pass $u; }
```
The nginx config already routes `/uc3` to `uc3_stub:8023` ✅ — this works when
both compose files are used together.

### Wiring Assessment
All environment variables are correctly matched:
- `REDIS_HOST=redis`, `REDIS_PORT=6379` ✅
- `DATABASE_URL` uses `postgres` hostname ✅
- `CAMERA_REGISTRY_URL=http://camera_registry:8011` ✅
- `alerts:live` stream name consistent across UC3 publisher and alert_management consumer ✅

---

## 6. Gaps and Issues

### Issue 1: UC3 not started by `make setup` (BLOCKER for pipeline)

**Problem**: `make setup` runs `docker compose -f infra/docker-compose.yml` only.
This brings up everything **except** UC3. With no UC3 running, no PPE detections
happen and no alerts are generated.

**Fix**: Run `make up-stubs` after `make setup` (or use `make setup2` which does
both). The Makefile already defines this — it just isn't the default path.

### Issue 2: `VITE_UC3_API_URL` missing from `services/dashboard/.env`

**Problem**: `services/dashboard/src/api/detections.ts` uses
`import.meta.env.VITE_UC3_API_URL ?? ""`. The dashboard's `.env` file
(`services/dashboard/.env`) does **not** set this variable:
```
VITE_AUTH_API_URL=http://localhost:8000
VITE_CAMERA_API_URL=http://localhost:8011
VITE_ALERTS_API_URL=http://localhost:8010
VITE_API_BASE_URL=
VITE_SOCKET_URL=http://localhost:8010
VITE_INGESTION_API_URL=http://localhost:8020
# VITE_UC3_API_URL is MISSING
```
With an empty base URL, `DetectionOverlay` calls
`/uc3/cameras/{camera_id}/latest-detections` against the current origin, which
works when the frontend is served through nginx (port 80) since nginx proxies
`/uc3` → `uc3_stub:8023`. But in local dev (`vite dev`, port 5173),
CORS/routing will fail.

**Fix**: Add `VITE_UC3_API_URL=http://localhost:8023` to
`services/dashboard/.env`.

### Issue 3: `/uc3/compliance/ppe-summary` endpoint is missing (affects reporting only)

**Problem**: `UC3_PPE_METRICS_URL` in both `.env` and `.env.example` points to
`http://host.docker.internal:8030/uc3/compliance/ppe-summary`, but this endpoint
does not exist in `stubs/uc3_stub/main.py`. The UC3 stub only exposes:
- `GET /health`
- `GET /cameras/{camera_id}/latest-detections`
- `GET /uc3/cameras/{camera_id}/latest-detections`

The reporting service (`generate_compliance_summary`) will log a warning and
return `{"error": "UC3 PPE data unavailable"}` when generating compliance
reports. Alert delivery is unaffected.

**Fix**: Add a `GET /uc3/compliance/ppe-summary` endpoint to
`stubs/uc3_stub/main.py` that returns aggregated violation counts from the
in-memory `_latest_detections` or from the PostgreSQL `alerts` table.

### Issue 4: Frame cache TTL vs. inference latency (potential missed frames)

**Problem**: Ingestion sets `FRAME_CACHE_TTL_S=20` (20-second TTL on
`frame:{camera_id}:{seq}` keys). UC3 processes messages from the stream with a
consumer group, so if the consumer falls behind by more than 20 seconds (e.g.,
during GPU inference on a slow machine), cached frames will expire before UC3
fetches them, resulting in `frame_cache_miss` and silently dropped detections.

**Note**: This is a tuning concern, not a code bug. Increase
`FRAME_CACHE_TTL_S` if needed, or rely on MinIO for fallback frame retrieval
(the frame is also stored there).

### Issue 5: `SMTP_USE_TLS` env var in `.env.example` but missing from `.env`

The `.env.example` has `SMTP_USE_TLS=false` but it is not in `.env`. The
notification service sets `SMTP_USE_TLS=${SMTP_USE_TLS:-false}` in
docker-compose so this falls back correctly. Low severity.

---

## 7. Frontend

### Dashboard Service
`services/dashboard/` — React/Vite/TypeScript SPA.

**Alerts page**: `services/dashboard/src/pages/Alerts.tsx`
- Displays a filterable alert feed via `AlertList` component.
- Filters: Camera ID, Use Case (UC1/UC2/**UC3**/UC4), Severity, Status.
- Calls `GET /alerts` on the alert management API (`VITE_ALERTS_API_URL=http://localhost:8010`).
- Real-time updates via Socket.IO (`VITE_SOCKET_URL=http://localhost:8010`).

**Camera detail with live feed + detection overlay**:
`services/dashboard/src/pages/CameraDetail.tsx`
- `LiveFeed` component streams MJPEG from `VITE_INGESTION_API_URL/stream/{cameraId}`.
- `DetectionOverlay` polls `GET /uc3/cameras/{cameraId}/latest-detections`
  every 2 seconds and draws bounding boxes on a canvas overlay.
- UC3 camera (ID `00000000-0000-0000-0000-000000000003`) will show PPE detection
  boxes in real time when `uc3_stub` is running.

---

## 8. Configuration

### `.env` (current)
All required secrets are set (non-empty):
- `POSTGRES_PASSWORD`, `DATABASE_URL` ✅
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_URL` ✅
- `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` (InnovisionMinIO_2026) ✅
- `JWT_SECRET` (set to a long random key) ✅
- `INTERNAL_SERVICE_KEY` (set) ✅
- `CAMERA_REGISTRY_URL` ✅

### Missing / Inconsistent
| Variable | Status | Impact |
|----------|--------|--------|
| `UC3_PPE_METRICS_URL` | Set in `.env` as `http://host.docker.internal:8030/...` but endpoint doesn't exist | Reporting compliance summary fails gracefully |
| `VITE_UC3_API_URL` | Missing from `services/dashboard/.env` | Detection overlay broken in dev mode |
| `SMTP_USE_TLS` | In `.env.example` but not in `.env` | Harmless (docker-compose default is `false`) |

---

## 9. End-to-End Pipeline Trace

```
1. Ingestion connects to Camera Registry:
   GET http://camera_registry:8011/cameras
   → discovers UC3 camera: 00000000-0000-0000-0000-000000000003

2. Ingestion decodes RTSP stream → encodes JPEG
   Redis SET frame:00000000-0000-0000-0000-000000000003:{seq}  (20s TTL)
   MinIO PUT innovision-frames/00000000-0000-0000-0000-000000000003/{seq:08d}.jpg
   Redis XADD frames:00000000-0000-0000-0000-000000000003 {data: <FrameEvent JSON>}

3. UC3 stub (uc3_stub service) discovers camera via:
   GET http://camera_registry:8011/by-uc/uc3
   → ["00000000-0000-0000-0000-000000000003"]
   Creates consumer group uc3_compliance_group on stream frames:...

4. UC3 xreadgroup polls frames:00000000-0000-0000-0000-000000000003
   → reads FrameEvent → GET frame:...:{seq} from Redis
   → Motion Gate → Person Gate → YOLO best.pt inference → ByteTrack
   → compliance.evaluate_compliance() → worker_violations list

5. On violation:
   AlertPublisher.publish(AlertEvent) →
   Redis XADD alerts:live {data: <AlertEvent JSON>}
   (source_uc=uc3, alert_type=ppe_violation, severity=medium/high)

6. alert_management xreadgroup polls alerts:live
   → validates AlertEvent schema + camera membership
   → INSERT INTO alerts (...) ON CONFLICT DO NOTHING
   → Socket.IO emit alert:new to camera room
   → Celery escalation task (if high/critical)

7. Frontend Alerts page:
   GET http://localhost:8010/alerts?source_uc=uc3
   → lists persisted PPE violation alerts from PostgreSQL

8. Camera Detail page:
   MJPEG stream from http://localhost:8020/stream/00000000-0000-0000-0000-000000000003
   + GET http://localhost:8023/uc3/cameras/00000000-0000-0000-0000-000000000003/latest-detections
   → bounding boxes rendered by DetectionOverlay canvas component
```

---

## 10. Recommendations (Priority Order)

### P0 — Required to run the pipeline

1. **Use `make setup2` or run `make up-stubs` after `make setup`** to start
   `uc3_stub` alongside the platform services. Without this, no PPE detections
   happen.

2. **Run DB migrations** (`make migrate`) before starting services to create the
   `alerts`, `cameras`, and related tables.

3. **Create MinIO buckets and Redis streams** (`make buckets && make streams`).

### P1 — Fix detection overlay in dev mode

4. **Add `VITE_UC3_API_URL=http://localhost:8023`** to
   `services/dashboard/.env`. Without it, the detection overlay falls back to
   an empty base URL (works through nginx on port 80, broken in `vite dev`).

### P2 — Fix reporting compliance endpoint

5. **Add `/uc3/compliance/ppe-summary` endpoint** to `stubs/uc3_stub/main.py`.
   Return aggregated statistics (total violations, per-camera counts, detection
   rate) from the in-memory `_latest_detections` dict. This unblocks the
   compliance summary report type in the reporting service.

### P3 — Optional tuning

6. **Consider increasing `FRAME_CACHE_TTL_S`** (currently 20s) if inference is
   slow on CPU. The frame disappears from Redis before UC3 processes it when the
   consumer is more than 20 seconds behind.

7. **`best.pt` model path** — `stubs/uc3_stub/models/best.pt` must exist. The
   directory contains the file but Docker build copies from `stubs/uc3_stub`
   which includes `models/`. Confirm the model is committed/present in the repo.
