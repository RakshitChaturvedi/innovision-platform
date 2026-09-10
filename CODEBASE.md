# Innovision Platform — Codebase Guide

This document explains the **entire** Innovision repository: what it is, how data moves, what every meaningful file does, inputs/outputs, and how Docker Compose wires it together.

Innovision is a **video-analytics operations platform**. Cameras (or test video files) are ingested into JPEG frames. Independent **use-case (UC) analytics** services consume those frames, publish typed **alerts**, and platform services persist alerts, open incidents, notify operators, audit actions, and generate reports. A React dashboard is the operator UI (partially implemented). A separate UC1-v2 stub ships a live YOLO demo UI.

---

## 1. Big picture

```text
Cameras / test video
        │
        ▼
 Camera Registry (Postgres + Redis pub/sub)
        │  HTTP camera list / config
        ▼
 Ingestion (FFmpeg → sample → JPEG)
        │
        ├── Redis cache   key: frame:{camera_id}:{seq}
        ├── MinIO         key: frames/{camera_id}/{seq}.jpg
        └── Redis Stream  frames:{camera_id}   ← FrameEvent JSON
                │
                ▼
        UC analytics (stubs + UC1-v2 YOLO)
                │
                └── Redis Stream  alerts:live   ← AlertEvent JSON
                        │
                        ▼
              Alert Management
                ├── Postgres alerts (+ incidents if high/critical)
                ├── Socket.IO  /alerts
                ├── Celery escalation → notifications:live
                └── alerts:dead_letter on invalid payloads
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
 Incident Mgmt    Notification        Audit (library + HTTP)
 (HTTP workflow)  (email + log)       (append-only audit_log)
        │
        ▼
 Reporting (HTTP enqueue + Celery PDF → MinIO)
        │
        ▼
 Dashboard (Vite/React)  and  UC1-v2 demo HTML
```

**Design rules visible in the code**

- Use cases do **not** write to Postgres. They publish `AlertEvent`s to Redis.
- Platform services own persistence, RBAC, audit, notifications, and reports.
- Frames are **referenced**, not embedded in events. Hot path is Redis (short TTL); cold path is MinIO.
- JWT access tokens carry `sub`, `role`, and `camera_ids`. Role ranks: viewer < operator < admin < superadmin.

---

## 2. Repository layout

```text
innovision-platform/
├── pyproject.toml              Root Python project (3.13+ locally; images use 3.11/3.12)
├── .env / .env.example         Compose + service environment
├── .dockerignore               Excludes git, venv, videos, models, node_modules
├── README.md                   Ingestion + UC1-v2 demo runbook
├── infra/                      Docker Compose, nginx
├── migrations/                 Alembic schema
├── shared/                     Contracts + DB helpers used by many services
├── services/                   Backend microservices + dashboard
├── stubs/                      Fake / demo use-case workers
├── scripts/                    Bucket/stream bootstrap + smoke tests
├── tests/                      Contract unit tests
└── test_data/videos/           Demo video bind-mounted into ingestion
```

---

## 3. How it all fits together (runtime)

### 3.1 Camera → frames

1. Alembic seeds four test cameras (`…0001`–`…0004`) assigned to `uc1`–`uc4`. Seeded rows have **no `rtsp_url`**, so ingestion will skip them until a URL (or file path) is set.
2. **Camera Registry** reads `cameras` from Postgres and exposes HTTP. On create/update/soft-delete it publishes Redis channels `camera:added:{id}`, `camera:updated:{id}`, `camera:removed:{id}`.
3. **Ingestion** on startup calls `GET /cameras`, starts one worker per camera with an `rtsp_url`. It also psubscribes those Redis channels and periodically reconciles.
4. Each worker: FFmpeg decode → FPS sampler → JPEG encode → Redis `SET` with TTL → MinIO upload → `XADD` `FrameEvent` to `frames:{camera_id}` (capped length).
5. A heartbeat publishes to `heartbeat:ingestion:{camera_id}`. **OfflineMonitor** marks cameras offline via Camera Registry HTTP if heartbeats stop.

### 3.2 Frames → alerts

- **UC1–UC4 stubs** ignore frames. They periodically construct `AlertEvent`s and `XADD` them to `alerts:live` via `AlertPublisher`.
- **UC1-v2** consumes `frames:{TEST_CAMERA_ID}`, loads JPEG from Redis, runs YOLOv8n person detection, and if count ≥ threshold publishes a JSON alert to `alerts:live`. It also serves a live MJPEG demo page on port **8021**.

### 3.3 Alerts → operators

1. **Alert Management** consumer (consumer group `alert_management_group`) reads `alerts:live`.
2. Schema + camera-id validation; failures go to `alerts:dead_letter` then ACK.
3. Insert `alerts` row. For severity `high`/`critical`, insert `incidents` in the **same transaction**.
4. Push Socket.IO `alert:new` to room `camera:{camera_id}`.
5. Schedule Celery `escalation_check` (Redis DB 1). If still `pending`, write to `notifications:live` and schedule next level (2 min / 3 min / 5 min).
6. **Notification** consumes that stream, emails users by role map (L1 operator, L2 admin, L3 superadmin) who have that camera, logs `notification_log`.
7. Operators **acknowledge/resolve** via HTTP; Socket.IO emits `alert:updated`. Incidents move through a strict state machine via Incident Management HTTP.

### 3.4 Dashboard vs UC1 demo

| UI | Where | Role |
|----|--------|------|
| `services/dashboard` | Local Vite (not in Compose). Intended host port **3000**. | Login, camera grid, RBAC shell. Alerts/incidents/reports pages are placeholders. |
| UC1-v2 HTML | Container port **8021** | End-to-end ingestion → YOLO → platform poll demo. |
| Grafana | Host **3001** → container 3000 | Observability (Compose mounts provisioning dirs that may not exist yet). |

---

## 4. Backend

Python services are FastAPI apps (plus Celery workers). They share Postgres (`innovision_platform`), Redis, and MinIO. SQL is mostly raw `sqlalchemy.text`, not ORM models (except an empty `Base`).

### 4.1 Shared library (`shared/`)

#### `shared/contracts/enums.py`

**Role:** Canonical string enums used in events and conceptually in the DB.

| Name | Values |
|------|--------|
| `FrameProvider` | `minio`, `redis` |
| `AlertSeverity` | `low`, `medium`, `high`, `critical` |
| `AlertStatus` | `pending`, `acknowledged`, `in_progress`, `resolved`, `closed` |
| `IncidentStatus` | `active`, `acknowledged`, `in_progress`, `resolved`, `closed` |
| `SourceUC` | `uc1`–`uc4` |
| `CameraStatus` | `online`, `offline`, `reconnecting`, `disabled` |
| `OperatorRole` | `superadmin`, `admin`, `operator`, `viewer` |

**Inputs/outputs:** None at runtime; imported by contracts and validators.

#### `shared/contracts/frame_event.py`

**Role:** Pydantic `FrameEvent` published by ingestion.

**Inputs (fields):** `event_id` (UUID, default new), `camera_id`, `frame_seq`, `timestamp`, `frame_provider`, `frame_reference`, `frame_shape` `(height, width)`. Frozen model.

**Outputs:** JSON via `model_dump_json()`. `FrameEventSchema.validated_reference_format` returns a list of error strings (MinIO keys must start with `frames/`; shape must be positive).

#### `shared/contracts/alert_event.py`

**Role:** Pydantic `AlertEvent` published by UCs.

**Inputs:** `alert_id`, `camera_id`, `timestamp`, `severity`, `alert_type`, `title`, `description`, `source_event_id`, `source_uc`, optional `frame_reference`/`frame_provider` (both or neither), `status` default `pending`, `metadata` dict.

**Outputs:** JSON for Redis. `AlertEventValidator.validate(event, known_cam_ids)` → list of errors (unknown camera, whitespace title/description).

#### `shared/contracts/base_analytics_event.py`

Placeholder comment only (“base class for all UC-internal events”). No types yet.

#### `shared/platform_client/alert_publisher.py`

**Role:** UC helper: validate JSON round-trip, `XADD` to `alerts:live` field `data`. On failure, `XADD` to `alerts:dead_letter`.

**Inputs:** `AlertEvent`, Redis client. **Outputs:** `bool` success.

#### `shared/platform_client/db.py`

**Inputs:** `database_url`. **Outputs:** cached async engine (`pool_size=10`) and `async_sessionmaker`. Used by auth, alerts, incidents, audit, notification, reporting HTTP.

#### `shared/database/base.py`

Empty SQLAlchemy `DeclarativeBase`. Alembic `target_metadata` points here; the real schema is written in the migration with `op.create_table`, not models.

---

### 4.2 Database (`migrations/`)

#### `migrations/alembic.ini`

Alembic config. `script_location` is this folder; `prepend_sys_path = .` so `shared` imports work.

#### `migrations/env.py`

**Inputs:** `DATABASE_URL` from `.env`. If the URL uses hostname `postgres`, it is rewritten to `localhost` so migrations can run on the host against published port 5432.

**Outputs:** Offline or async online migration run.

#### `migrations/script.py.mako`

Template for new revision files.

#### `migrations/versions/0001_platform_base.py`

**Inputs:** Alembic `upgrade()`. **Outputs:** Postgres schema + seed data.

Creates extensions `uuid-ossp` and `vector` (pgvector image). Enums: `camera_status`, `alert_severity`, `alert_status`, `incident_status`, `operator_role`, `source_uc`.

| Table | Purpose |
|-------|---------|
| `cameras` | id, name, location, rtsp_url, status, use_cases[], fps, metadata, timestamps |
| `users` | name, email unique, password_hash, role, camera_ids[] |
| `sessions` | refresh_token_hash, expires_at, revoked_at |
| `alerts` | business `alert_id` unique, camera FK, UC, type, severity, text, frame refs, status, ack/resolve audit columns |
| `incidents` | FK to `alerts.id`, title, status, assigned_to, notes |
| `incident_timeline` | append-only history of incident actions |
| `audit_log` | platform audit; **DB rules block UPDATE and DELETE** |
| `notification_log` | per-delivery email/push attempt |

**Seed:** four test cameras and a superadmin `admin@innovision.com` with a placeholder bcrypt hash (not a real password).

**Gap:** Reporting HTTP inserts into table `reports`, which this migration does **not** create.

---

### 4.3 Auth service (`services/auth/`) — host port **8000**

JWT login for operators. Other services import `rbac.py` / `jwt.py` as a **library** (they do not HTTP-call auth for every request; they decode the same secret).

#### `main.py`

FastAPI app. Mounts `/auth` router. `GET /health` → `{status, service}`.

#### `src/config.py`

**Inputs (env):** `DATABASE_URL`, `JWT_SECRET`, `JWT_ALGORITHM` (default HS256), `ACCESS_TOKEN_EXPIRE_MINUTES` (default 15; Compose sets 30 via `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` which this field does **not** alias — expiry may ignore Compose unless names match), `REFRESH_TOKEN_EXPIRE_DATS` (typo in alias vs `.env` `JWT_REFRESH_TOKEN_EXPIRE_DAYS`).

#### `src/jwt.py`

| Function | Input | Output |
|----------|--------|--------|
| `hash_password` / `verify_password` | plaintext, hash | bcrypt |
| `create_access_token` | user_id, role, camera_ids | JWT string |
| `decode_access_token` | JWT | payload dict |
| `create_refresh_token` | DB session, user_id | raw UUID string; stores bcrypt hash in `sessions` |
| `rotate_refresh_token` | old raw token, session_id | `(access, new_refresh, user_id)` or `None` |

#### `src/rbac.py`

**Inputs:** `Authorization: Bearer …` header. **Outputs:** JWT payload or 401/403.

- `get_current_user`
- `require_role(minimum)` — rank gate
- `require_camera_access(camera_id)` — admins bypass; others need id in `camera_ids`

#### `src/router.py` prefix `/auth`

| Method | Path | Input | Output |
|--------|------|--------|--------|
| POST | `/login` | query `email`, `password` | `{access_token, token_type}`; httponly `refresh_token` cookie |
| POST | `/refresh` | `session_id`, `refresh_token` | new access + refresh |
| POST | `/logout` | Bearer user | revokes all open sessions; `{status: logged_out}` |

**Note:** login uses `user.password_has` (typo; column is `password_hash`) — this will fail at runtime until fixed.

#### `Dockerfile`

Python 3.12-slim, `PYTHONPATH=/app`, copies whole repo, uvicorn port **8000**.

---

### 4.4 Camera Registry (`services/camera_registry/`) — host **8011**

Source of truth for camera config. Ingestion and UCs discover cameras here.

#### `main.py`

Creates async engine + Redis. Instantiates `CameraRegistryService`. Overrides FastAPI `get_service`. Lifespan closes Redis/engine. `GET /health`.

#### `src/schemas.py`

- **CameraCreate** in: name, location?, rtsp_url, use_cases[], fps 1–60 default 15.
- **CameraConfigUpdate** in: use_cases?, fps?.
- **CameraResponse** out: id, name, location, status, use_cases, fps, created_at.

#### `src/service.py`

| Method | Input | Side effects / output |
|--------|--------|------------------------|
| `create_camera` | CameraCreate | INSERT status `offline`; Redis publish `camera:added:{id}`; returns `{id, ...fields}` |
| `update_config` | id, CameraConfigUpdate | dynamic UPDATE; publish `camera:updated:{id}` |
| `delete_camera` | id | sets status `disabled`; publish `camera:removed:{id}` |
| `get_cameras_for_uc` | uc_id | list of camera UUID strings |
| `get_active_cameras` | — | list of dicts `id, name, rtsp_url, fps, use_cases` where status ≠ disabled |
| `update_status` | id, status | UPDATE cameras.status |

**Gap:** `router.get_status` and ingestion client call `get_camera` / `GET /cameras/{id}`, but **`get_camera` is not implemented** and there is no `GET /cameras/{id}` or `PATCH /cameras/{id}/status` route.

#### `src/router.py` prefix `/cameras`

| Method | Path | Auth | Input | Output |
|--------|------|------|--------|--------|
| POST | `` | ADMIN+ | CameraCreate | 201 created camera |
| GET | `` | none | — | active cameras list |
| PUT | `/{id}/config` | ADMIN+ | CameraConfigUpdate | `{status: updated}` |
| GET | `/{id}/status` | none | — | `{camera_id, status, profile, use_cases}` (`profile` is not a DB column; will KeyError unless added) |
| DELETE | `/{id}` | SUPERADMIN | — | 204 soft-disable |
| GET | `/by-uc/{uc_id}` | none (internal) | — | `{uc_id, camera_ids}` |

#### `Dockerfile`

Python 3.11-slim + curl for healthcheck. Copies `shared` and `services`. Port **8011**.

---

### 4.5 Ingestion (`services/ingestion/`) — host **8020**

Turns video into cached JPEGs + `FrameEvent`s.

#### `main.py`

Lifespan: Redis ping → registry client → FramePublisher, FrameCache, FrameStore → `CameraManager.start()` → `OfflineMonitor` background task. FastAPI includes health router. Shutdown cancels monitor, stops cameras, closes HTTP/Redis.

**Inputs:** env via `IngestionConfig`. **Outputs:** `/health` JSON; Redis/MinIO side effects.

#### `src/config.py`

| Env / field | Default | Meaning |
|-------------|---------|---------|
| REDIS_HOST/PORT | redis:6379 | Streams, cache, pub/sub |
| DATABASE_URL | | Present but unused by ingestion workers |
| MINIO_* | minio:9000 | Frame store |
| INGESTION_TEST_MODE / TEST_VIDEO_PATH | True / "" | Declared; decoder uses camera `rtsp_url` (file path works as FFmpeg `-i`) |
| DEFAULT_FPS | 10 | Fallback if camera fps missing |
| JPEG_QUALITY | 85 | OpenCV encode |
| HEARTBEAT_INTERVAL_S | 5 | |
| STREAM_MAXLEN | 1000 | Redis stream cap |
| CAMERA_OFFLINE_TIMEOUT_S | 10 | Offline monitor |
| FRAME_CACHE_TTL_S | 20 | Redis JPEG TTL |
| RECONNECT_* | 1s–30s exponential | Stream drop retry |
| CAMERA_REGISTRY_URL | http://camera_registry:8011 | |
| CAMERA_REFRESH_INTERVAL_S | 60 | Manager reconcile |
| minio_frames_bucket | innovision-frames | |

#### `src/camera_registry_client.py`

HTTP client.

| Method | Calls | Output |
|--------|--------|--------|
| `get_active_cameras` | GET `/cameras` | list (filters disabled again) |
| `get_camera` | GET `/cameras/{id}` | dict or None on 404 |
| `update_status` | PATCH `/cameras/{id}/status` JSON `{status}` | none |
| `close` | — | closes httpx |

Failures raise `CameraRegistryError`.

#### `src/camera_manager.py`

**Inputs:** registry client, Redis, publisher, cache, store.

**Behavior:** start all active cameras; psubscribe `camera:added|updated|removed:*`; every `camera_refresh_interval_s` start missing / stop extra.

**Outputs:** running `CameraIngestionTask`s; `active_camera_ids` / `active_camera_count`.

#### `src/camera_task.py`

Per-camera loop.

**Inputs:** camera_id, rtsp_url, fps, Redis, publisher, cache, store.

**Outputs:** for each sampled frame: Redis JPEG, MinIO object, FrameEvent. Heartbeat task in parallel. Exponential reconnect on decoder failure. `stop()` sets flag for graceful exit.

If **cache or MinIO fails, the frame is not published** (hot+cold both required).

#### `src/stream_decoder.py`

**Input:** `source` string (RTSP or file), width×height default 1920×1080.

**Output:** numpy BGR frames. RTSP uses TCP + timeout; files `-stream_loop -1`. Raises `StreamDropError` on EOF. Redacts credentials in logs.

#### `src/frame_sampler.py`

**Input:** `target_fps`. **Output:** `should_sample()` bool; `frame_seq` increments only on accepted samples and is **not** reset on reconnect.

#### `src/jpeg_encoder.py`

**Input:** BGR ndarray, quality. **Output:** JPEG bytes; `object_key` → `frames/{camera_id}/{seq:08d}.jpg`.

#### `src/frame_cache.py`

**Input:** camera_id, seq, bytes. **Output:** Redis key `frame:{camera_id}:{seq}` with TTL; `get`/`delete` helpers.

#### `src/frame_store.py`

**Input:** object_key, jpeg bytes. **Output:** MinIO `put_object` on `innovision-frames` (sync SDK via `asyncio.to_thread`). Does not create the bucket.

#### `src/publisher.py`

**Input:** camera_id, seq, frame_reference (Redis key), shape. **Output:** Redis message id. Stream `frames:{camera_id}`, field `data` = FrameEvent JSON, `frame_provider=redis`.

#### `src/heartbeat.py`

**Input:** Redis, camera_id, interval. **Output:** pub/sub JSON `{camera_id, timestamp, status: online}` on `heartbeat:ingestion:{id}`.

#### `src/offline_monitor.py`

**Input:** Redis psubscribe `heartbeat:ingestion:*`, registry client.

**Output:** PATCH camera online when heartbeat resumes; after timeout, PATCH offline and publish `camera:offline:{id}`.

#### `src/health.py`

`GET /health` → `{status, service, phase: "2", active_cameras, camera_ids}` using the live worker dict registered from `main.py`.

#### `Dockerfile`

Python 3.11-slim, **ffmpeg**, libgl, curl. Copies `pyproject.toml`/`uv.lock` then `requirements.txt`. Port **8020**. Compose bind-mounts `test_data/videos`.

---

### 4.6 Alert Management (`services/alert_management/`)

HTTP + Socket.IO + Redis consumer. Compose maps host **8010**. Image default uvicorn is **8000** (see Docker section). Celery worker is a second container.

#### `main.py`

Starts `AlertConsumer` in lifespan. Includes `/alerts` router. Mounts Socket.IO at `/socket.io`. `GET /health`.

#### `src/config.py`

Streams: `alerts:live`, `alerts:dead_letter`, `notifications:live`. Group `alert_management_group`. Incident severities `{high, critical}`. Escalation delays 120/180/300s. Celery broker `redis://redis:6379/1`. JWT for Socket.IO.

#### `src/consumer.py`

**Input:** Redis XREADGROUP on `alerts:live`.

**Pipeline:** parse `AlertEvent` → `validate_alert` against all camera UUIDs in DB → insert alert → maybe incident → audit `alert_created` → `push_alert` → schedule escalation → XACK. Persist failure: **no ACK** (retry). Schema/validation failure: dead letter + ACK.

#### `src/validator.py`

Delegates to `AlertEventValidator`.

#### `src/persistence.py`

`insert_alert` ON CONFLICT `alert_id` DO NOTHING. `fetch_alert_row` / `fetch_alert_by_alert_id`.

#### `src/incident_trigger.py`

If severity in config set, INSERT `incidents` status `active` with `alert_id` = **alerts table PK** (`row_id`), title from alert.

#### `src/websocket.py`

Namespace `/alerts`. Connect requires JWT in `auth.token`. `join` with `{camera_ids, last_seen_timestamp?}`: rooms `camera:{id}`; non-admins cannot join unassigned cameras; missed pending alerts emitted as `alert:missed`. `push_alert` / `push_alert_update` emit `alert:new` / `alert:updated`.

#### `src/reconnect.py`

**Input:** camera_ids, ISO `since`. **Output:** pending alerts created after `since`.

#### `src/escalation.py`

Celery app `alert_escalation`. Task `escalation_check(alert_row_id, level)`: if still `pending`, XADD `notifications:live` `{alert_id, camera_id, level, severity}`; chain level 2 then 3.

#### `src/router.py` prefix `/alerts`

| Method | Path | Auth | Input | Output |
|--------|------|------|--------|--------|
| GET | `` | optional Bearer | filters source_uc, severity, status, camera_id, limit, offset | alert rows; non-admin filtered by camera_ids |
| PATCH | `/{alert_id}/acknowledge` | OPERATOR+ | — | status acknowledged; audit; socket update |
| PATCH | `/{alert_id}/resolve` | OPERATOR+ | — | resolved |
| GET | `/unacknowledged` | required | — | pending alerts |
| GET | `/count` | required | — | `{count}` pending |

`alert_id` in paths is the **business UUID**, not table PK.

#### `Dockerfile`

Same pattern as auth: copy repo, uvicorn **8000**. Worker container overrides CMD to Celery.

---

### 4.7 Incident Management (`services/incident_management/`) — host **8003** → container 8000

Incidents are **created by Alert Management**, not this service. This service is the operator workflow API.

#### `main.py`

FastAPI + `/incidents` + `/health`. Does **not** start `IncidentAutoResolveConsumer`.

#### `src/config.py`

`DATABASE_URL` only.

#### `src/workflow.py`

Allowed transitions: `active → acknowledged → in_progress → resolved → closed`. Resolved may go back to `in_progress`. Closed is terminal.

#### `src/timeline.py`

`append_entry` INSERT `incident_timeline`. `fetch_timeline` ordered by timestamp.

#### `src/consumer.py`

Documented no-op placeholder for future auto-resolve.

#### `src/router.py` prefix `/incidents`

| Method | Path | Auth | Input | Output |
|--------|------|------|--------|--------|
| GET | `` | optional | status, assigned_to | incident list |
| GET | `/{id}` | required | — | incident + timeline + valid_next_states |
| PATCH | `/{id}/status` | OPERATOR+ | `new_status` | 400 if illegal; else update + timeline + audit |
| PATCH | `/{id}/assign` | OPERATOR+ | `assignee_id` | assigned |
| POST | `/{id}/notes` | OPERATOR+ | `note` | timeline note |

---

### 4.8 Notification (`services/notification/`) — host **8004**

#### `main.py`

Lifespan starts `NotificationConsumer`. Health only (no public notify API).

#### `src/config.py`

Stream `notifications:live`, group `notification_group`. SMTP_*. `escalation_role_map` 1→operator, 2→admin, 3→superadmin.

#### `src/consumer.py`

**Input:** stream fields `alert_id` (table PK), `camera_id`, `level`.

Loads alert title/description and camera name. Selects users with mapped role **and** that camera in `camera_ids`. Sends email per recipient; `log_delivery`. ACK only after success; otherwise retry.

#### `src/email.py`

**Input:** to, title, description, camera_name, level. **Output:** bool. SMTP STARTTLS + login. Subject `[ESCALATION Ln] …`.

#### `src/push.py`

Stub: logs and returns True (no Firebase).

#### `src/logger.py`

INSERT `notification_log` (`sent`/`failed`).

---

### 4.9 Audit (`services/audit/`) — host **8002**

#### `src/writer.py`

**Library** imported by alert/incident routers and consumer. INSERT `audit_log`. Optional existing `session` to join an open transaction.

#### `src/router.py` prefix `/audit`

`GET /audit` ADMIN+: filters service, entity_type, source_uc, limit/offset. Returns rows newest first.

#### `src/consumer.py`

No-op placeholder for future event-sourced audit.

#### `main.py`

HTTP API + health.

---

### 4.10 Reporting (`services/reporting/`)

HTTP API exists; **only the Celery worker is in Compose**, not the FastAPI process. Worker broker Redis DB **2**.

#### `main.py`

Would serve `/reports` on container 8000 if started.

#### `src/router.py`

| Method | Path | Auth | Input | Output |
|--------|------|------|--------|--------|
| POST | `/generate` | OPERATOR+ | report_type, date_start, date_end, camera_ids? | `{report_id, status: pending}` + INSERT `reports` + Celery |
| GET | `/{id}/status` | — | — | reports row |
| GET | `/{id}/download` | — | — | `{download_url}` 24h presigned if complete |
| GET | `` | required | — | last 50 reports |

`report_type` values: `incident_summary`, `alert_volume`, `camera_health`, `compliance_summary`.

#### `src/tasks.py`

Celery `generate_report_task`: pick generator → PDF → MinIO `innovision-reports` key `{YYYY-MM}/{report_id}.pdf` → status complete/failed.

#### `src/aggregator.py`

Shared queries `alerts_in_range`, `incidents_in_range`.

#### `src/generators/*.py`

Each returns a dict of metrics. Compliance generator HTTP-GETs `UC1_COMPLIANCE_URL` and `UC3_PPE_METRICS_URL` (Compose points at `uc1_api` / `uc3_api`, which are **not** defined in Compose — calls fail soft with error dicts).

#### `src/pdf_writer.py`

ReportLab A4 table of scalar fields. Title “IntelliWatch — …”. Nested dicts/lists are omitted from the table.

#### `src/storage.py`

MinIO upload + presigned GET.

**Gap:** `reports` table missing from migration; HTTP service not composed.

---

### 4.11 Use-case stubs (`stubs/`)

#### `uc1_stub` … `uc4_stub` (`main.py` each)

**Inputs:** REDIS_HOST/PORT, TEST_CAMERA_ID, ALERT_INTERVAL_SECONDS, UC_ID (Compose only).

**Outputs:** looping `AlertPublisher.publish` of scenario alerts (intruder/fire/PPE/speed, etc.) tagged `[STUB]`.

UC1 Dockerfile copies `shared/` and runs `python stubs/uc1_stub/main.py`. UC2–4 Dockerfiles follow the same pattern.

#### `stubs/uc1_v2/main.py`

Real consumer + YOLO + demo UI.

**Inputs:** REDIS_URL, TEST_CAMERA_ID, consumer group/name, YOLO_MODEL/CONFIDENCE, PEOPLE_THRESHOLD (default 3), ALERT_COOLDOWN_SECONDS, ALERT_MGMT_URL (default `http://alert_management:8000`), INCIDENT_MGMT_URL.

**Outputs:**

| Path | Output |
|------|--------|
| GET `/` | HTML dashboard |
| GET `/api/latest` | people count, timings, cache stats |
| GET `/api/pipeline` | stage flags |
| GET `/api/platform` | polled alerts/incidents |
| GET `/api/video` | MJPEG annotated frames |
| GET `/health` | healthy + camera_id |
| Redis | `alerts:live` JSON (not via AlertPublisher; raw dict) |

Background: consume frames, poll platform every 3s.

#### `stubs/uc1_v2/Dockerfile`

Python 3.11 + OpenCV libs. Port **8021**. Depends on healthy ingestion in Compose.

---

### 4.12 Scripts and tests

#### `scripts/create_buckets.py`

**Input:** MinIO host credentials from env (`MINIO_HOST_ENDPOINT` default localhost:9000). **Output:** buckets `innovision-frames`, `innovision-snapshots`, `innovision-evidence`, `innovision-reports`.

#### `scripts/create_platform_streams.py`

**Input:** `REDIS_LOCAL_URL`. **Output:** Redis streams + consumer groups for alerts, dead letter, incidents, notifications. (Services also `XGROUP CREATE` lazily.)

#### `scripts/smoke_test_p1.py`

Host-side: health of alert management at localhost:8010, wait until each UC has ≥1 alert in Postgres, check dead-letter length and stream lag.

#### `scripts/smoke_test_phase2.py`

Phase-2 ingestion/frame-path smoke (file exists in repo; same purpose as README Redis checks).

#### `tests/contracts/test_frame_event.py` / `test_alert_event.py`

Pytest for Pydantic contracts (MinIO key prefix, shape, JSON round-trip, etc.).

---

## 5. Frontend

The operator UI is `services/dashboard`: **React 19 + TypeScript + Vite 8 + TanStack Query + Axios + React Router 7**. It is **not** in Docker Compose. Run with `npm run dev` after setting `.env`.

Intended API base: `VITE_API_BASE_URL` (must reverse-proxy or point at individual services; nginx currently only returns a static 200). `VITE_SOCKET_URL` is reserved for Socket.IO; no client code uses it yet.

### 5.1 Bootstrap and config

| File | Role |
|------|------|
| `index.html` | Vite HTML shell, `#root` |
| `src/main.tsx` | React root: QueryClientProvider → AuthProvider → App |
| `src/App.tsx` | Renders `AppRoutes` |
| `src/index.css` / `App.css` | Global styles |
| `vite.config.ts` | `@vitejs/plugin-react`, alias `@` → `src/` |
| `tsconfig*.json` | TS project split app/node |
| `eslint.config.js` | Lint |
| `package.json` | Scripts `dev`, `build`, `preview`, `lint` |
| `.env.example` | `VITE_API_BASE_URL`, `VITE_SOCKET_URL` |

### 5.2 API layer

#### `src/api/client.ts`

Axios instance. **Input:** `VITE_API_BASE_URL`. Request interceptor attaches `Authorization: Bearer` from `localStorage` key `innovision_access_token`.

#### `src/api/auth.ts`

| Function | HTTP | Input | Output |
|----------|------|--------|--------|
| `login` | POST `/auth/login` query email/password | credentials | `{access_token, token_type}` |
| `logout` | POST `/auth/logout` | Bearer | void |

#### `src/api/cameras.ts`

| Function | HTTP | Output |
|----------|------|--------|
| `getCameras` | GET `/cameras` | `Camera[]` |
| `getCamera` | GET `/cameras/{id}` | `Camera` (backend route missing) |
| `getCameraStatus` | GET `/cameras/{id}/status` | status string |

There are **no** axios modules yet for alerts, incidents, reports, or users.

### 5.3 Types and auth state

#### `src/types/auth.ts`

`UserRole`, `User` `{id, role, camera_ids}`, `LoginResponse`, `AuthState`.

#### `src/types/camera.ts`

`CameraStatus`, `Camera` `{id, name, rtsp_url, status, use_cases, fps}`. List API currently does not return `status`/`rtsp_url` from `get_active_cameras`.

#### `src/lib/jwt.ts`

**Input:** access token. **Output:** `User` from `sub`, `role`, `camera_ids`.

#### `src/lib/rbac.ts`

`hasMinimumRole`, `canSeeCamera` (admin/superadmin see all).

#### `src/lib/queryClient.ts`

staleTime 5s, retry 1, no refetch on focus.

#### `src/store/auth-context.ts`

React context type.

#### `src/store/AuthContext.tsx`

**Input:** login/logout. **Output:** context. Hydrates user from localStorage JWT. Login stores token; logout calls API then clears storage.

#### `src/store/useAuth.ts`

Hook; throws if outside provider.

#### `src/store/auth.ts`

Unused-looking `AuthState` interface duplicate.

### 5.4 Routing and layout

#### `src/routes/AppRoutes.tsx`

| Path | Guard | Page |
|------|--------|------|
| `/login` | public | Login |
| `/unauthorized` | public | Unauthorized |
| `/` | auth | MasterDashboard |
| `/cameras/:cameraId` | auth | CameraDetail |
| `/alerts`, `/incidents`, `/reports` | operator+ | placeholders |
| `/admin/cameras`, `/compliance` | admin+ | placeholders |
| `/admin/users` | superadmin | placeholder |

#### `src/routes/ProtectedRoute.tsx`

Unauthenticated → `/login`.

#### `src/routes/RoleRoute.tsx`

Insufficient role → `/unauthorized`.

#### `src/components/layout/AppLayout.tsx`

Header + sidebar filtered by role + logout + `<Outlet />`.

#### Common UI

`LoadingState`, `ErrorState`, `EmptyState` — presentational.

`CameraTile` — **Input:** `Camera`. Click navigates to `/cameras/{id}`. Shows name, status, fps, use cases.

### 5.5 Pages

#### `src/pages/Login.tsx`

**Input:** email/password form. Calls `login`. Redirects to `location.state.from` or `/`. Already authenticated → `/`.

#### `src/pages/MasterDashboard.tsx`

**Input:** `getCameras` via React Query. Filters by `user.camera_ids` unless admin/superadmin. **Output:** grid of `CameraTile`.

#### `src/pages/CameraDetail.tsx`

**Input:** route `cameraId`, `getCamera` + `getCameraStatus`. RBAC via `canSeeCamera`. **Output:** metadata; live feed / alerts / incidents / UC metrics are placeholders (“will be integrated”).

#### `src/pages/Unauthorized.tsx`

Static denied page.

#### Placeholders

`Alerts.tsx`, `Incidents.tsx`, `Reports.tsx`, `Compliance.tsx`, `admin/Cameras.tsx`, `admin/Users.tsx` — titles only.

---

## 6. Docker setup

### 6.1 How to start

From repo root (requires `.env`):

```bash
docker compose --env-file .env \
  -f infra/docker-compose.yml \
  -f infra/docker-compose.stubs.yml \
  up -d
```

Compose files live under `infra/`. **Build context is the repo root** (`context: ..`) so Dockerfiles can `COPY shared/` and `COPY services/`.

`.dockerignore` excludes `.git`, venvs, `node_modules`, videos (`*.mp4`), weights (`*.pt`), `.env`. Test video is still available because Compose **bind-mounts** `test_data/videos` into ingestion after build.

### 6.2 Environment (`.env.example`)

| Variable | Used by |
|----------|---------|
| POSTGRES_USER/PASSWORD | Postgres + DATABASE_URL |
| DATABASE_URL | All DB services (`postgresql+asyncpg://…@postgres:5432/innovision_platform`) |
| REDIS_* | Ingestion, alerts, notification, stubs |
| MINIO_* | Ingestion, reporting, bucket script |
| GRAFANA_PASSWORD | Grafana |
| CAMERA_REGISTRY_URL | Ingestion |
| JWT_* | Auth, alert Socket.IO, incident (algorithm hardcoded HS256 in incident compose env) |
| SMTP_* | Notification |

Host tools should use `REDIS_LOCAL_URL` and `MINIO_HOST_ENDPOINT` (`localhost`) because inside Compose hostnames are `redis` / `minio`.

### 6.3 `infra/docker-compose.yml`

#### Data plane (images, no app build)

| Service | Image | Ports | Notes |
|---------|-------|-------|--------|
| `postgres` | `pgvector/pgvector:pg16` | 5432 | DB `innovision_platform`, volume `postgres_data`, health `pg_isready` |
| `redis` | `redis:7-alpine` | 6379 | 2GB maxmemory, `allkeys-lru`, `--save ""` (no RDB), volume `redis_data` |
| `minio` | `minio/minio` | 9000 API, 9001 console | `server /data --console-address :9001` |
| `nginx` | `nginx:alpine` | 80 | Mounts `infra/nginx/nginx.conf` — currently **only** `return 200 "Innovision nginx is running"` (not an API gateway) |
| `prometheus` | official | 9090 | Expects `infra/prometheus/prometheus.yml` and `alerts.yml` |
| `grafana` | official | **3001**:3000 | 3000 left free for dashboard; provisioning dir mount |
| `loki` | official | 3100 | Expects `infra/loki/loki-config.yml` |

Health: Postgres/Redis/MinIO have healthchecks. App services `depends_on` those conditions where listed.

#### Application services

| Compose service | Dockerfile | Host port | Container listen | depends_on |
|-----------------|------------|-----------|------------------|------------|
| `camera_registry` | `services/camera_registry/Dockerfile` | 8011 | 8011 | postgres, redis healthy |
| `ingestion` | `services/ingestion/Dockerfile` | 8020 | 8020 | postgres, redis, minio, camera_registry; volume videos |
| `auth` | `services/auth/Dockerfile` | 8000 | 8000 | postgres |
| `alert_management` | alert Dockerfile | **8010:8010** | image CMD **8000** | postgres, redis, minio |
| `alert_management_worker` | same image | none | Celery `services.alert_management.src.escalation.celery_app` | postgres, redis |
| `audit` | audit Dockerfile | 8002:8000 | 8000 | postgres |
| `incident_management` | incident Dockerfile | 8003:8000 | 8000 | postgres |
| `notification` | notification Dockerfile | 8004:8000 | 8000 | postgres, redis |
| `reporting_worker` | reporting Dockerfile | none | Celery `services.reporting.src.tasks.celery_app` broker DB 2 | redis, postgres, minio |

**Not composed:** reporting FastAPI, dashboard, a migrate job. You must run Alembic and `create_buckets.py` from the host (or a one-off container) before frames/reports work.

**Port mismatch:** `alert_management` publishes 8010:8010 and healthchecks `localhost:8010`, but Dockerfile listens on 8000. UC1-v2 defaults to `http://alert_management:8000`. Align CMD, published ports, and healthcheck to one port.

### 6.4 `infra/docker-compose.stubs.yml`

Overlay; merge with the main file. All stubs `env_file: ../.env`.

| Service | Camera UUID | Interval | Role |
|---------|-------------|----------|------|
| `uc1_stub` | …0001 | 10s | Synthetic UC1 alerts |
| `uc2_stub` | …0002 | 15s | Fire/smoke |
| `uc3_stub` | …0003 | 12s | PPE |
| `uc4_stub` | …0004 | 8s | Vehicle |
| `uc1_v2_stub` | …0001 | n/a | YOLO consumer, port **8021**, depends on healthy `ingestion` |

### 6.5 Image build pattern

Two styles:

1. **Ingestion / camera_registry / UC1-v2:** slimmer copy (`shared` + that service), extra apt packages (ffmpeg/curl/OpenCV).
2. **Auth, alerts, incidents, audit, notification, reporting:** `COPY . .` entire tree after pip install from that service’s `requirements.txt`. `PYTHONPATH=/app` so `services.*` and `shared.*` imports work.

Workers reuse the API image and override `command`.

### 6.6 Nginx (`infra/nginx/nginx.conf`)

Listens on 80; no upstreams to FastAPI. Dashboard and APIs are reached on **published ports** (8000, 8011, 8020, …) until nginx is expanded into a real gateway (`VITE_API_BASE_URL` would then be `http://localhost` with path routing).

### 6.7 Volumes

Named volumes: `postgres_data`, `redis_data`, `minio_data`, `prometheus_data`, `grafana_data`, `loki_data`. Redis AOF/RDB persistence is disabled (`--save ""`); streams/cache are ephemeral across Redis data loss except what was snapshotted in the volume if any dump existed.

### 6.8 Typical local ports cheat sheet

| Port | Service |
|------|---------|
| 80 | nginx placeholder |
| 3000 | (reserved) Vite dashboard |
| 3001 | Grafana |
| 3100 | Loki |
| 5432 | Postgres |
| 6379 | Redis |
| 8000 | Auth |
| 8002 | Audit |
| 8003 | Incidents |
| 8004 | Notification |
| 8010 | Alert management (intended) |
| 8011 | Camera registry |
| 8020 | Ingestion health |
| 8021 | UC1-v2 demo |
| 9000/9001 | MinIO API/console |
| 9090 | Prometheus |

---

## 7. Cross-cutting data contracts

### Redis keys and streams

| Key / stream | Writer | Reader |
|--------------|--------|--------|
| `frames:{camera_id}` | Ingestion | UC1-v2 (and future UCs) |
| `frame:{camera_id}:{seq}` | Ingestion cache | UC1-v2 GET |
| `alerts:live` | UCs / AlertPublisher | Alert Management |
| `alerts:dead_letter` | Publisher + consumer | Ops / smoke tests |
| `notifications:live` | Escalation Celery | Notification |
| `camera:added\|updated\|removed:{id}` | Camera Registry | Ingestion manager |
| `camera:offline:{id}` | Offline monitor | (no consumer yet) |
| `heartbeat:ingestion:{id}` | Ingestion heartbeat | Offline monitor |
| Celery Redis DB 1 | Alert worker | Escalation tasks |
| Celery Redis DB 2 | Reporting worker | Report tasks |

### MinIO object keys

| Bucket | Key pattern |
|--------|-------------|
| `innovision-frames` | `frames/{camera_id}/{seq:08d}.jpg` |
| `innovision-reports` | `{YYYY-MM}/{report_id}.pdf` |
| snapshots / evidence | Documented in `create_buckets.py`, unused by current services |

### JWT access token payload

`sub`, `role`, `camera_ids`, `iat`, `exp`, `type: "access"`. Dashboard and Socket.IO both depend on this shape.

---

## 8. Known gaps (useful when reading the code)

These are current mismatches, not extra features:

1. Seeded cameras have no `rtsp_url` → ingestion logs `camera_missing_rtsp_url` until config is updated (file path to `/app/test_data/videos/uc1.mp4` works with FFmpeg).
2. Camera Registry missing `GET /cameras/{id}`, `PATCH …/status`, and `get_camera()` while ingestion and dashboard call them.
3. Auth login attribute typo `password_hash` vs `password_has`; JWT env alias mismatches.
4. Alert management Docker port 8000 vs Compose 8010.
5. `reports` table not in Alembic; reporting API not in Compose.
6. Nginx is not an API gateway; dashboard needs a single base URL or CORS on each service.
7. Dashboard alerts/incidents/reports/admin pages and Socket.IO client are not wired.
8. Prometheus/Grafana/Loki config files referenced by Compose may be absent.
9. `incident_report.py` redefines `incidents_in_range` without returning the query result (generator will fail if used).
10. UC1-v2 and synthetic UC1 stub can both publish to `alerts:live` for the same camera if both Compose overlays are up.

---

## 9. File index (quick)

**Shared:** `shared/contracts/*`, `shared/platform_client/*`, `shared/database/base.py`  
**Schema:** `migrations/versions/0001_platform_base.py`, `migrations/env.py`  
**Auth:** `services/auth/main.py`, `src/{router,jwt,rbac,config}.py`  
**Cameras:** `services/camera_registry/{main.py,src/router.py,service.py,schemas.py}`  
**Ingestion:** `services/ingestion/main.py`, `src/{camera_manager,camera_task,stream_decoder,frame_sampler,jpeg_encoder,frame_cache,frame_store,publisher,heartbeat,offline_monitor,health,config,camera_registry_client}.py`  
**Alerts:** `services/alert_management/{main.py,src/{consumer,persistence,validator,incident_trigger,router,websocket,reconnect,escalation,config}.py}`  
**Incidents:** `services/incident_management/{main.py,src/{router,workflow,timeline,consumer,config}.py}`  
**Notify:** `services/notification/{main.py,src/{consumer,email,push,logger,config}.py}`  
**Audit:** `services/audit/{main.py,src/{writer,router,consumer,config}.py}`  
**Reports:** `services/reporting/{main.py,src/{router,tasks,aggregator,pdf_writer,storage,config,generators/*}.py}`  
**Stubs:** `stubs/uc{1,2,3,4}_stub/main.py`, `stubs/uc1_v2/main.py`  
**UI:** `services/dashboard/src/**`  
**Docker:** `infra/docker-compose.yml`, `infra/docker-compose.stubs.yml`, each `services/*/Dockerfile`, `stubs/*/Dockerfile`  
**Ops:** `scripts/create_buckets.py`, `scripts/create_platform_streams.py`, `scripts/smoke_test_*.py`
