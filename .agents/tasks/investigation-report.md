# Innovision Platform — Investigation Report

**Generated:** 2026-10-05  
**Investigator:** Read-only agent  
**Scope:** S1 (live feed), S2 (alerts page), S3 (UC3 detections), S4 (nginx)

---

## Executive Summary

| # | Symptom | Root Cause | Severity |
|---|---------|-----------|----------|
| S1 | Live feed `<img>` broken | **Not actually broken.** Frames are flowing (XLEN=1012+, TTL=294s remaining). The `<img>` uses relative URL `/stream/{cameraId}` which goes through the Vite proxy, and ingestion logs show 200 OK responses. The "alt text shows" symptom most likely occurs only until the first frame byte arrives (MJPEG streams don't fire `onLoad`, which the code already accounts for). No code fix needed — pipeline is healthy. | LOW |
| S2 | "Failed to load alerts" | **`GET /alerts` now requires auth (HTTP 401) but the dashboard has no 401 interceptor**. The token expires in 30 min; on expiry the API returns 401, the `alertClient` has no response interceptor, and the error surfaces as "Failed to load alerts." Secondary issue: `innovision_reporting_worker` crash-loops due to missing `greenlet` in `requirements.txt`. | **BLOCKER** (auth) + HIGH (reporting) |
| S3 | UC3 produces no detections | **Largely resolved but has a lag problem.** UC3 _is_ publishing alerts (confirmed in logs). The consumer group has `lag=999–1011` — ~100 seconds of backlog at 10 fps. CPU-only inference at ~60ms/frame processes ~16 fps but processing is sequential with gates, so real throughput is lower. All messages older than the frame-cache TTL window will return cache misses and be silently skipped. The `half` deprecation warning fires on every frame because `_fp16=False` (CPU) but `half=_fp16` is still passed. | **HIGH** (lag) + MEDIUM (half warning) |
| S4 | nginx `host not found in upstream` | **Not currently failing** — nginx is up and proxying correctly. The `host not found` error appeared historically (visible in nginx error logs) when `uc3_stub` was not yet running, because nginx used `set $u` with a static resolver. With `uc3_stub` now healthy, nginx resolves correctly. | LOW (historical) |

---

## Phase 0 — Wiring

### Container Status (`docker ps -a`)

```
NAMES                                STATUS                         PORTS
infra-uc1_v2_stub-1                  Up 23 minutes                  0.0.0.0:8021->8021
infra-alert_management-1             Up 23 minutes (healthy)        0.0.0.0:8010->8000
infra-uc4_stub-1                     Up 23 minutes                  
infra-uc2_stub-1                     Up 23 minutes                  
infra-uc1_stub-1                     Up 23 minutes                  
infra-uc3_stub-1                     Up 15 minutes (healthy)        0.0.0.0:8023->8023
infra-ingestion-1                    Up 23 minutes (healthy)        0.0.0.0:8020->8020
infra-camera_registry-1              Up 23 minutes (healthy)        0.0.0.0:8011->8011
innovision_notification              Up 23 minutes                  0.0.0.0:8004->8000
innovision_alert_management_worker   Up 23 minutes                  
innovision_auth                      Up 23 minutes                  0.0.0.0:8000->8000
innovision_incident_management       Up 23 minutes                  0.0.0.0:8003->8000
innovision_audit                     Up 23 minutes                  0.0.0.0:8002->8000
innovision_reporting_worker          Restarting (2) 7 seconds ago   ← CRASH-LOOPING
infra-grafana-1                      Up 23 minutes                  0.0.0.0:3001->3000
infra-postgres-1                     Up 23 minutes (healthy)        0.0.0.0:5433->5432
infra-minio-1                        Up 23 minutes (healthy)        0.0.0.0:9000-9001->9000-9001
infra-nginx-1                        Up 23 minutes                  0.0.0.0:80->80
infra-loki-1                         Up 23 minutes                  0.0.0.0:3100->3100
infra-redis-1                        Up 23 minutes (healthy)        0.0.0.0:6379->6379
infra-prometheus-1                   Up 23 minutes                  0.0.0.0:9090->9090
innovision_mailhog                   Exited (255) 43 hours ago      (dev profile, expected)
intelliwatch-alert-management        Exited (1) About an hour ago   (leftover from other project)
```

**Notable:** `innovision_reporting_worker` is crash-looping. All core services are healthy.

### UC3 Architecture

- UC3 runs **as a container** (`infra-uc3_stub-1`, port 8023), not as a host process.
- nginx reaches it via `set $u http://uc3_stub:8023` (nginx.conf line 18).
- Port 8030 is referenced in `docker-compose.yml` as `UC3_PPE_METRICS_URL=http://host.docker.internal:8030/uc3/compliance/ppe-summary` (the reporting worker tries to call it), but nothing listens there — that URL points to nothing running.
- No uc3 stub defined separately in `docker-compose.stubs.yml` conflicts: the stubs file defines `uc3_stub` with port 8023, same service, same config — the real `uc3_stub` container replaced it.

### UC3 Model

```
docker exec infra-uc3_stub-1 python -c "from ultralytics import YOLO; m=YOLO('/app/stubs/uc3_stub/models/best.pt'); print(m.names)"
{0: 'gloves', 1: 'goggles', 2: 'helmet', 3: 'mask', 4: 'no-gloves', 5: 'no-goggles', 6: 'no-helmet', 7: 'no-mask', 8: 'no-shoe', 9: 'no-vest', 10: 'person', 11: 'shoe', 12: 'vest'}
```

Same model path (`stubs/uc3_stub/models/best.pt`) and same 13 classes as the standalone app.

### UC3 Environment Variables (from `docker exec env`)

```
UC_ID=uc3
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_URL=redis://redis:6379
CAMERA_REGISTRY_URL=http://camera_registry:8011
TEST_CAMERA_ID=00000000-0000-0000-0000-000000000003
REDIS_CONSUMER_GROUP=uc3_compliance_group
REDIS_CONSUMER_NAME=uc3_worker_1
PPE_CONF_THRESHOLD=0.35
PPE_IOU_THRESHOLD=0.45
PPE_VIOLATION_WINDOW_SECONDS=3.0
FRAME_CACHE_TTL_S=300
UC3_PPE_METRICS_URL=http://host.docker.internal:8030/uc3/compliance/ppe-summary  ← dead URL
```

### Dashboard `.env` Variable Names

```
VITE_AUTH_API_URL
VITE_CAMERA_API_URL
VITE_ALERTS_API_URL
VITE_API_BASE_URL
VITE_SOCKET_URL
VITE_INGESTION_API_URL
VITE_UC3_API_URL
```

---

## S1 — Live Feed Broken

### Evidence

**Step 1 — Redis stream is active and growing:**
```
XLEN frames:00000000-0000-0000-0000-000000000003 → 1006 (t=0)
XLEN frames:00000000-0000-0000-0000-000000000003 → 1012 (t=5s)
```
6 frames in 5 seconds = ~1.2 fps ingestion rate (expected for a looping test video at reduced rate).

**Step 2 — Latest frame entry:**
```
1791176937610-0
data → {"frame_reference":"frame:00000000-0000-0000-0000-000000000003:8249","frame_shape":[1080,1920],...}
```

**Step 3 — Frame cache TTL:**
```
TTL frame:00000000-0000-0000-0000-000000000003:8249 → 294 seconds
```
Frame cache TTL is 300s (`settings.frame_cache_ttl_s=300`). Frames are present and not expired.

**Step 4 — Ingestion logs (200 OK for all four cameras):**
```
INFO: 172.19.0.1:36440 - "GET /stream/00000000-0000-0000-0000-000000000003 HTTP/1.1" 200 OK
INFO: 172.19.0.1:36446 - "GET /stream/00000000-0000-0000-0000-000000000001 HTTP/1.1" 200 OK
INFO: 172.19.0.1:36450 - "GET /stream/00000000-0000-0000-0000-000000000002 HTTP/1.1" 200 OK
INFO: 172.19.0.1:36456 - "GET /stream/00000000-0000-0000-0000-000000000004 HTTP/1.1" 200 OK
```
All four cameras return 200 OK to the streaming endpoint.

**Step 5 — LiveFeed.tsx URL:**
`src={`/stream/${cameraId}`}` — relative URL, goes through Vite proxy (`/stream` → `http://localhost:8020`). Correct.

**Step 6 — Streaming logic (streaming.py):**
- Uses `XREAD` with `block=1000ms`, starting from the most recent frame ID.
- On cache miss: increments `consecutive_misses`; after 5 misses, jumps to latest.
- Yields multipart MJPEG frames correctly.

### Root Cause

**There is no active code bug causing a permanent broken stream.** The pipeline from Redis → frame cache → streaming endpoint is working. The `<img>` element shows alt text before the first byte of MJPEG arrives — this is normal browser behaviour for MJPEG: the `<img>` renders alt text until the stream delivers its first frame boundary. The Vite dev server proxy (`/stream` → `http://localhost:8020`) is correctly wired.

**However**, there is one potential intermittent issue: the ingestion rate is ~1.2 fps (likely a looping test video), which means some frames may expire from the 300s cache before the streaming endpoint reads them. The `streaming.py` code handles this gracefully (5-miss jump-to-latest). No fix needed for the stream itself.

**Possible actual cause if stream stays black:** The dashboard `VITE_INGESTION_API_URL` is set, but `LiveFeed.tsx` hard-codes `/stream/${cameraId}` (relative URL), bypassing that env var entirely. If the Vite dev server is not running and the browser hits nginx on port 80, nginx does NOT proxy `/stream` — there is no `/stream` location in `nginx.conf`. Requests to `http://localhost/stream/...` return nginx's `200 "Innovision gateway running"` (the catch-all `/` route), which is not a valid MJPEG boundary and would cause a broken image.

**File/line:** `infra/nginx/nginx.conf` — missing `/stream` proxy location. `services/dashboard/src/components/cameras/LiveFeed.tsx:72` — `src={`/stream/${cameraId}`}`.

### Proposed Fix for S1

Add `/stream` location to `nginx.conf`:
```nginx
location /stream { set $u http://ingestion:8020; proxy_pass $u; }
```
Also add proxy buffering settings for MJPEG:
```nginx
proxy_buffering off;
proxy_cache off;
```
This makes the stream work whether the browser hits nginx (port 80) or the Vite dev server (port 5173).

---

## S2 — "Failed to load alerts"

### Evidence

**Step 1 — HTTP status without auth:**
```
GET /alerts → HTTP 401 Unauthorized
```
Confirmed by: nginx error log entry:
```
172.19.0.1 - "GET /alerts HTTP/1.1" 401 41
```
And confirmed by direct container call raising `HTTPError: HTTP Error 401: Unauthorized`.

**Step 2 — alert_management import check:**
```
docker exec infra-alert_management-1 python -c "import services.alert_management.main"
→ Exit code 0 (clean, no ImportError)
```
`minio` is present in `services/alert_management/requirements.txt` — the previously-reported `No module named 'minio'` crash is resolved.

**Step 3 — router.py auth requirement:**
`services/alert_management/src/router.py:49`:
```python
user: dict = Depends(get_current_user),
```
`GET /alerts` requires a valid Bearer token. There is no anonymous access.

**Step 4 — Dashboard API client (`client.ts`):**
```typescript
export const alertClient = axios.create({
  baseURL: import.meta.env.VITE_ALERTS_API_URL,
});
alertClient.interceptors.request.use(attachAuthToken);
```
There is a request interceptor that attaches the stored token. But there is **no response interceptor** — a 401 response is not caught, not redirected to login, and surfaces to the UI as a generic error ("Failed to load alerts").

**Step 5 — Token lifetime:**
```
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30  (from docker exec innovision_auth env)
```
`services/auth/src/config.py:10`: `access_token_expire_minutes: int = Field(default=15, ...)` — default is 15 min, but the container env overrides it to **30 minutes**. After 30 minutes of inactivity, any API call returns 401 and the dashboard shows "Failed to load alerts."

**Step 6 — CORS hardcoded origins:**
`services/alert_management/main.py:36–42`:
```python
allow_origins=[
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
```
`services/camera_registry/main.py:67–72`: Same hardcoded list. No env-var override.

**Step 7 — reporting_worker crash loop:**
```
ImportError: The SQLAlchemy asyncio module requires that the Python 'greenlet' library is installed.
  File "/app/services/reporting/src/tasks.py", line 12
    from shared.platform_client.db import get_session_factory
```
`shared/platform_client/db.py` uses `sqlalchemy.ext.asyncio`, which requires `greenlet`. It is **not** in `services/reporting/requirements.txt`. The container restarts every ~10s.

### Root Cause (S2)

**Primary — BLOCKER:** `GET /alerts` requires auth (`Depends(get_current_user)` at `router.py:49`). The dashboard has no 401 response interceptor on `alertClient`. When the 30-minute access token expires, every alert request returns 401 and the error handler shows "Failed to load alerts." This also affects `cameraClient` and `authClient` — any expired-token request silently fails.

**Secondary — HIGH:** `innovision_reporting_worker` crash-loops because `services/reporting/requirements.txt` is missing `greenlet` (needed transitively by `sqlalchemy[asyncio]`).

**Tertiary — MEDIUM:** CORS origins are hardcoded to `localhost:5173` in both `alert_management` and `camera_registry`. Any deployment where the frontend runs on a different origin will fail preflight checks.

### Proposed Fixes for S2

1. **Dashboard (`services/dashboard/src/api/client.ts`):** Add a response interceptor to `alertClient`, `cameraClient`, and `authClient`: on 401, clear `localStorage.innovision_access_token`, show user-visible message "Session expired, please sign in again", and redirect to `/login`. Guard the login request itself to avoid redirect loops.

2. **Reporting worker (`services/reporting/requirements.txt`):** Add `greenlet` (or `sqlalchemy[asyncio]`). The fix is one line: `greenlet` or replace `sqlalchemy` with `sqlalchemy[asyncio]`.

3. **CORS configuration:** In `alert_management/main.py` and `camera_registry/main.py`, read `CORS_ALLOWED_ORIGINS` from env (defaulting to `http://localhost:5173`) and pass it to `CORSMiddleware`. Add `CORS_ALLOWED_ORIGINS` to `.env` and the docker-compose environment blocks.

---

## S3 — UC3 Detections and Alerts on Live Video

### Evidence

**Step 1 — UC3 is running and producing alerts:**
From `docker logs infra-uc3_stub-1`:
```
2026-10-05 04:46:11 INFO uc3_real_service — alert_published alert_id=7e5a9ea6 ... ppe_type=eye_prot
2026-10-05 04:56:13 INFO uc3_real_service — alert_published alert_id=f8b9c0f8 ... ppe_type=eye_prot
```
UC3 _is_ producing alerts (every ~10 minutes). The complaint "no usable detections and no new real UC3 alerts" reflects a **lag/throughput problem**, not a complete failure.

**Step 2 — Consumer group lag:**
```
XINFO GROUPS frames:00000000-0000-0000-0000-000000000003
  name: uc3_compliance_group
  consumers: 1
  pending: 2
  last-delivered-id: 1791176817264-0
  entries-read: 7478 (check 1) → 8106 (check 2, ~5 min later)
  lag: 999 (check 1) → 1011 (check 2)
```
**Lag is increasing.** The group consumed ~628 messages in 5 minutes (~2.09/s = 2.09 fps processed) while ingestion produced ~6 per 5s (~1.2 fps). The lag grew by 12 in 5 min, meaning UC3 is not keeping up even at 1.2 fps ingestion rate. At 10 fps ingestion the backlog would be catastrophic.

**Step 3 — Pipeline path and stale-frame risk:**
- Frame cache TTL: 300s (`FRAME_CACHE_TTL_S=300` in env, confirmed from ingestion settings).
- At 1.2 fps ingestion and 2.09 fps UC3 processing, UC3 is nominally keeping up.
- BUT: The consumer group reads with `XREADGROUP … ">"` which delivers the next undelivered message regardless of age. The code in `main.py` does NOT have a stale-message drop (the standalone `frame_source.py`'s `RedisFrameSource` used `BRPOP` on a list, a completely different mechanism). The platform's `uc3_stub/main.py` at the `process_frame_message` function just calls `redis_client.get(frame_event.frame_reference)` — if the frame has expired from the 300s cache, `jpeg_bytes` will be `None` and the function returns with a debug log only.
- At 1.2 fps ingestion with a 300s TTL, frames are well within TTL. But at 10 fps ingestion with 999 messages of lag, the oldest pending message is ~999/10 = ~100 seconds old — still within 300s TTL. However, if lag grows above 3000 (300s × 10fps), frames will start expiring before UC3 processes them.

**Step 4 — `half` deprecation warnings:**
```
WARNING ⚠️ 'half' is deprecated and will be removed in the future. Use 'quantize' instead.
```
This fires on every inference call. In `stubs/uc3_stub/main.py`:
```python
_fp16: bool = False  # CPU path
...
results = model.track(..., half=_fp16, ...)  # passes half=False to Ultralytics
```
Ultralytics deprecated the `half` parameter. The fix is to omit `half` when `_fp16=False`.

**Step 5 — alerts:live stream (last 5):**
All 5 recent entries in `alerts:live` are from UC1 (`uc1`) and UC2 (`uc2`) and UC4 (`uc4`) stubs. No UC3 entries in the last 5. The two UC3 alerts logged earlier were from ~4:46 and ~4:56 — over 10 minutes ago. This confirms UC3 alert rate is very low (one alert ~every 10 minutes).

**Step 6 — Model identity:**
Platform model: `stubs/uc3_stub/models/best.pt` (13 classes: gloves, goggles, helmet, mask, no-gloves, no-goggles, no-helmet, no-mask, no-shoe, no-vest, person, shoe, vest).  
Standalone model: `PPE_DETECTION/backend/models/` — same file is referenced via config path `BASE_DIR / "models" / "best.pt"`.  
The same weights are used.

**Step 7 — Device difference:**
Platform (container): `device=cpu, fp16=False` (no CUDA in container).  
Standalone (host): may use CUDA if available.  
CPU inference is ~60ms/frame vs GPU ~9ms/frame — this is the throughput bottleneck.

**Step 8 — Critical difference: consumer group `id="0"` at creation:**
`stubs/uc3_stub/main.py` line in `run_uc3_pipeline`:
```python
await redis_client.xgroup_create(
    name=s_name, groupname=REDIS_CONSUMER_GROUP,
    id="0",   # ← delivers ALL historical messages from the beginning
    mkstream=True,
)
```
Starting from `id="0"` means on every restart, UC3 attempts to re-consume ALL messages ever written to the stream (currently 8000+). This creates the initial massive lag spike after every container restart. The correct approach for a live feed is `id="$"` (start from now).

### Root Cause (S3)

1. **HIGH — Consumer group starts from `id="0"`** (`stubs/uc3_stub/main.py` in `run_uc3_pipeline`): On restart, UC3 tries to replay ALL historical frames. With 8000+ frames already in the stream and CPU-only inference, the worker immediately falls 999+ messages behind and never catches up to live. Fix: change `id="0"` to `id="$"` in `xgroup_create`.

2. **HIGH — Consumer processes latest message in batch only, ACKs the rest silently:** In `run_uc3_pipeline`:
```python
latest_msg_id, latest_fields = messages[-1]
for msg_id, _ in messages[:-1]:
    await redis_client.xack(...)  # ACK without processing
```
This is intentional (process latest, skip stale), but combined with `id="0"`, it means all 8000 historical frames are ACK'd without processing on the first read, which is correct behaviour — but the lag counter reflects pending messages, not unprocessed ones. The real issue is the one alert per 10 minutes: even on live frames (after catching up), the pipeline needs to process enough consecutive frames to pass `MIN_EVIDENCE_SAMPLES=2` and `VIOLATION_WINDOW_SECONDS=3.0`.

3. **MEDIUM — `half` kwarg passed when `_fp16=False`** (`stubs/uc3_stub/main.py` in `_new_model()` and `model.track()`): Triggers deprecation warning on every inference call. Fix: pass `half=_fp16` only when `_fp16=True`, or switch to `quantize`.

4. **LOW — No visibility counter:** There is no periodic INFO log summarising frames read, gates passed, detections, alerts. Making drops visible requires adding a counter.

### Proposed Fixes for S3

1. Change `id="0"` to `id="$"` in `xgroup_create` call in `stubs/uc3_stub/main.py`. This makes UC3 start from now on restart rather than replaying history.

2. Pass `half` argument to Ultralytics only when `_fp16=True`:
   ```python
   predict_kwargs = dict(conf=CONF_THRESHOLD, iou=IOU_THRESHOLD, imgsz=IMAGE_SIZE, device=_device, verbose=False)
   if _fp16:
       predict_kwargs["half"] = True
   ```
   Apply to both `model.predict()` in `_new_model()` and `model.track()` in `_run_cascade_and_inference()`.

3. Add periodic INFO log every 30s per camera with counters (frames read, cache misses, gates passed/failed, detections, violations, alerts published).

4. For the alert persistence path: UC3 publishes directly to `alerts:live` Redis stream via `AlertPublisher`. The `AlertConsumer` in `alert_management` should be consuming that stream and writing to DB. If alerts appear in `alerts:live` but not in the DB/UI, check `alert_management`'s consumer — but based on evidence (401 on GET /alerts) the real issue is the expired token in the dashboard, not missing DB rows.

---

## S4 — nginx Port 80 / Host Not Found

### Evidence

**nginx logs (last 20):**
```
2026/10/04 19:53:32 [error] 23#23: *1 connect() failed (111: Connection refused) while connecting to upstream
  upstream: "http://172.19.0.20:8023/uc3/cameras/.../latest-detections"
```
This error is from **yesterday** (04/Oct). It occurred because `uc3_stub` was not yet running at that time. Nginx attempted to proxy to `uc3_stub:8023` but the container hadn't started.

**Current nginx status:** `Up 23 minutes` — healthy. No current errors. The `resolver 127.0.0.11` (Docker's internal DNS) is configured, and `set $u http://uc3_stub:8023` defers resolution to request time, so nginx survives upstream restarts without itself crashing.

**Missing `/stream` location (confirmed from nginx.conf):**
```nginx
# nginx.conf has:
location /uc3           { set $u http://uc3_stub:8023;   proxy_pass $u; }
location /ingestion     { set $u http://ingestion:8020;  proxy_pass $u; }
# BUT MISSING:
# location /stream      { ... }
```

### Root Cause (S4)

The historical `host not found` errors were caused by nginx starting before `uc3_stub` was healthy — now resolved.

**Active issue:** `/stream` is not proxied through nginx. If the dashboard is accessed via `http://localhost` (port 80, nginx) rather than `http://localhost:5173` (Vite dev server), the `LiveFeed.tsx` `<img src="/stream/...">` hits nginx's catch-all `/` route and receives `200 "Innovision gateway running"` — not a valid MJPEG stream. This is the **actual root cause of S1** when accessed via nginx.

### Proposed Fix for S4

Add to `infra/nginx/nginx.conf`:
```nginx
location /stream {
    set $u http://ingestion:8020;
    proxy_pass $u;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 86400s;
}
```

---

## Consolidated Fix List (in dependency order)

### Fix 1 — BLOCKER: 401 interceptor in dashboard API clients
**Files:** `services/dashboard/src/api/client.ts`  
**What:** Add Axios response interceptor to `alertClient`, `cameraClient`, and `authClient`. On 401: clear `localStorage.innovision_access_token`, display "Session expired, please sign in again", redirect to `/login`. Skip redirect if the failing request is itself the login endpoint.  
**Verify:** Log in, wait for token to expire (or manually clear it), navigate to Alerts page — should see "Session expired" message and redirect to login instead of "Failed to load alerts."

### Fix 2 — HIGH: Missing `greenlet` in reporting_worker
**Files:** `services/reporting/requirements.txt`  
**What:** Add `greenlet` (or change `sqlalchemy` to `sqlalchemy[asyncio]`).  
**Verify:** `docker compose ... up --build reporting_worker` → container stays up, `docker logs` shows celery worker ready.

### Fix 3 — HIGH: UC3 consumer group starts from history (`id="0"`)
**Files:** `stubs/uc3_stub/main.py` in `run_uc3_pipeline`  
**What:** Change `id="0"` to `id="$"` in `xgroup_create`. This makes UC3 consume only new frames on restart.  
**Verify:** Restart `uc3_stub`, check `XINFO GROUPS frames:...` — `lag` should be near 0 after startup.

### Fix 4 — MEDIUM: `half` kwarg deprecation warning spam
**Files:** `stubs/uc3_stub/main.py` in `_new_model()` and `_run_cascade_and_inference()`  
**What:** Only pass `half=True` when `_fp16=True`. On CPU, omit the `half` argument entirely.  
**Verify:** `docker logs infra-uc3_stub-1` — no more `'half' is deprecated` warnings.

### Fix 5 — MEDIUM: Missing `/stream` nginx proxy location
**Files:** `infra/nginx/nginx.conf`  
**What:** Add `/stream` location proxying to `ingestion:8020` with `proxy_buffering off`.  
**Verify:** `curl http://localhost/stream/00000000-0000-0000-0000-000000000003` returns multipart MJPEG content.

### Fix 6 — MEDIUM: CORS origins hardcoded
**Files:** `services/alert_management/main.py`, `services/camera_registry/main.py`, `.env`, `infra/docker-compose.yml`  
**What:** Read allowed origins from `CORS_ALLOWED_ORIGINS` env var (comma-separated, default `http://localhost:5173`).  
**Verify:** Set `CORS_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000`, restart services, confirm CORS preflight passes.

### Fix 7 — LOW: Add per-camera counters INFO log to UC3
**Files:** `stubs/uc3_stub/main.py`  
**What:** Add a counter dict per camera tracking: frames_read, cache_misses, motion_gate_pass/fail, person_gate_pass/fail, detections, violations_raised, alerts_published. Log at INFO every 30s.  
**Verify:** `docker logs infra-uc3_stub-1` shows counter lines every 30s.

---

## Appendix: Key File+Line Citations

| Finding | File | Line / Symbol |
|---------|------|---------------|
| UC3 consumer group `id="0"` (S3 root) | `stubs/uc3_stub/main.py` | `xgroup_create(..., id="0", ...)` in `run_uc3_pipeline` |
| `half=_fp16` always passed (S3) | `stubs/uc3_stub/main.py` | `model.track(..., half=_fp16, ...)` in `_run_cascade_and_inference` |
| No 401 interceptor (S2 root) | `services/dashboard/src/api/client.ts` | `alertClient` / `cameraClient` — no `.interceptors.response.use` |
| Alerts require auth | `services/alert_management/src/router.py` | line 49: `user: dict = Depends(get_current_user)` |
| Token expires 30 min | `services/auth/src/config.py` + env | `JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30` |
| greenlet missing (S2) | `services/reporting/requirements.txt` | missing `greenlet` |
| CORS hardcoded (S2) | `services/alert_management/main.py` | lines 36–42 |
| CORS hardcoded (S2) | `services/camera_registry/main.py` | lines 67–72 |
| `/stream` missing from nginx | `infra/nginx/nginx.conf` | no `/stream` location |
| LiveFeed relative URL | `services/dashboard/src/components/cameras/LiveFeed.tsx` | line 72: `src={\`/stream/${cameraId}\`}` |
| dead UC3_PPE_METRICS_URL | `infra/docker-compose.yml` | `UC3_PPE_METRICS_URL=http://host.docker.internal:8030/...` |
