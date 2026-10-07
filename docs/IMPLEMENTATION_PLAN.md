# Innovision Platform — Revised Implementation Plan (IMPLEMENTATION_PLAN.md)

**Date:** October 6, 2026  
**Repository:** `innovision-platform`  
**Branch:** `feature/uc2-uc4-uc3`  

---

## 1. Roadmap Overview & Scope Priority

The immediate priority for `innovision-platform` is a fully working native **UC3 PPE Engine integration** alongside core platform fixes, while preserving existing **UC2** and **UC4** operations.

Broad multi-tenancy schema refactoring across platform-owned tables (`cameras`, `users`, `alerts`, `incidents`, `audit_log`) is excluded from the UC3 integration phase.

```text
Phase 1: Technical Audit & Architecture Plan (REVISED & COMPLETE)
   │
   ▼
Phase 2: Core Pipeline Fixes (Nginx Gateway, Live Feed, Overlay Letterboxing, Frame Drops)
   │
   ▼
Phase 3: Native UC3 Engine Integration (Port PPE Engine, ByteTrack, Compliance, Event Loop)
   │
   ▼
Phase 4: UC3 Event Persistence, AlertPublisher & Snapshot Storage
   │
   ▼
Phase 5: UC3 Overlay API, Health, Metrics & React Overlay Alignment
   │
   ▼
Phase 6: Platform Maintenance & Bug Fixes (Alembic 0002 for uc3_* and reports table)
   │
   ▼
Phase 7: Dashboard UI Enhancements & Zone Management Console
   │
   ▼
Phase 8: Telemetry, Production Hardening & Validation
```

---

## 2. File-by-File Integration Map (PPE_DETECTION -> innovision-platform)

All files copied from `PPE_DETECTION` are placed exclusively inside `innovision-platform/services/uc3/`. The standalone `PPE_DETECTION` project is **100% UNTOUCHED**.

| Source File in `PPE_DETECTION` | Target File in `innovision-platform` | Purpose / Responsibility |
|---|---|---|
| `backend/compliance.py` | `services/uc3/src/compliance.py` | Spatial association & temporal sliding window compliance engine |
| `backend/motion_gate.py` | `services/uc3/src/motion_gate.py` | OpenCV MOG2 motion gate filtering |
| `backend/person_gate.py` | `services/uc3/src/person_gate.py` | Fast YOLO person class verification gate |
| `backend/mannequin_gate.py` | `services/uc3/src/mannequin_gate.py` | Texture & edge variance mannequin filtering |
| `backend/config.py` | `services/uc3/src/ppe_config.py` | Confidence thresholds & window timing parameters |
| `backend/tracker_config.yaml` | `services/uc3/src/tracker_config.yaml` | ByteTrack tracker configuration |
| `backend/models/best.pt` | `services/uc3/models/best.pt` | Ultralytics YOLO model weights |

---

## 3. Detailed Phase Breakdown

### Phase 1: Audit & Plan Revision (Completed)
- **Status**: Complete. `AUDIT.md`, `ARCHITECTURE.md`, and `IMPLEMENTATION_PLAN.md` updated to enforce standalone repo protection, single database architecture, `FrameEvent.frame_reference` loading, enhanced `uc3_events` schema, read-only Camera Registry access, and UC2/UC4 backward compatibility.

---

### Phase 2: Core Pipeline Fixes
- **Goal**: Resolve runtime issues affecting video streaming, Nginx proxying, and overlay misalignment without altering UC2/UC4 behavior.
- **Planned Changes**:
  1. **Nginx Proxy Configuration (`infra/nginx/nginx.conf`)**:
     - Route `/stream/*` to `ingestion` (8020).
     - Route `/api/v1/auth/*` to `auth` (8000).
     - Route `/api/v1/cameras/*` to `camera_registry` (8011).
     - Route `/api/v1/alerts/*` to `alert_management` (8010).
     - Route `/api/v1/uc3/*` to `uc3` (8023).
  2. **Ingestion Non-Blocking Archival (`services/ingestion/src/camera_task.py`)**:
     - Prevent MinIO frame upload errors from aborting Redis stream publishing.
     - Add auto-creation of MinIO buckets `innovision-frames` and `innovision-snapshots` at startup.
  3. **Camera Registry Read-Only Endpoints (`services/camera_registry`)**:
     - Implement missing `GET /cameras/{id}` endpoint. UC3 will ONLY read camera configuration via GET routes and will NOT issue PATCH status calls.
  4. **Aspect-Ratio Canvas Scaling (`services/dashboard/src/components/cameras/CameraOverlay.tsx`)**:
     - Implement aspect-ratio letterbox offset calculation.
     - Preserve existing UC2 (`8022`) and UC4 (`8024`) endpoint polling while adding UC3 (`8023`) and UC1 (`8021`).

---

### Phase 3: Native UC3 Engine Integration
- **Goal**: Port standalone `PPE_DETECTION` inference code natively into `services/uc3`.
- **Planned Changes**:
  1. **Directory Structure**: Create `services/uc3/` with `Dockerfile`, `requirements.txt`, `main.py`, `models/`, and `src/`.
  2. **Code Porting**: Copy `compliance.py`, `motion_gate.py`, `person_gate.py`, `mannequin_gate.py`, `tracker_config.yaml`, and `best.pt` into `services/uc3/`.
  3. **Redis Stream Consumer (`services/uc3/src/consumer.py`)**:
     - Execute `XREADGROUP` on stream `frames:{camera_id}` under group `uc3_group`.
     - Deserialize `FrameEvent` and use `frame_reference` directly according to `frame_provider` (`redis` key load vs `minio` object download).
     - Run inference and compliance pipeline. `XACK` message upon completion.

---

### Phase 4: Event Persistence, AlertPublisher & Snapshots
- **Goal**: Persist UC3 internal events, upload snapshots, and publish canonical `AlertEvent`s.
- **Planned Changes**:
  1. **Alembic Migration (`0002_uc3_tables.py`)**:
     - Create `uc3_events` table (`id`, `organization_id`, `camera_id`, `zone_id`, `track_id`, `event_type`, `missing_ppe`, `present_ppe`, `compliance_score`, `timestamp`, `frame_reference`, `frame_provider`, `metadata`).
     - Create `uc3_zones` and `uc3_zone_ppe_rules` tables.
     - Create `reports` table (fixes reporting worker missing table error).
  2. **Event Persistence & Traceability**:
     - Save internal compliance event to `uc3_events` to obtain real `uc3_event_id`.
  3. **Snapshot Archival**:
     - Upload annotated JPEG frame to MinIO `innovision-snapshots` under `uc3/alerts/{YYYY-MM-DD}/{alert_id}.jpg`.
  4. **Alert Publishing**:
     - Use `AlertPublisher` to send `AlertEvent` to `alerts:live` with `source_event_id = uc3_event_id` and `source_uc = SourceUC.UC3`.

---

### Phase 5: UC3 Overlay API, Health, Metrics & Visual Parity
- **Goal**: Expose UC3 API endpoints and verify visual parity on the dashboard.
- **Planned Changes**:
  1. **Overlay Endpoint**: `GET /uc3/cameras/{camera_id}/latest-detections` returning normalized bounding boxes (`0.0`–`1.0`), track IDs, labels, colors, and zone required PPE.
  2. **Health & Metrics**: `/health` (service status, model loaded, Redis status, frame age) and `/metrics` (Prometheus counters & latency histograms).
  3. **Visual Parity Verification**: Verify person/PPE bounding boxes, labels, and missing-PPE badges match `PPE_DETECTION` over identical video input.

---

### Phase 6: Platform Bug Fixes & Maintenance
- **Goal**: Ensure reporting and platform database dependencies operate without errors.
- **Planned Changes**:
  1. Execute Alembic migration `0002_uc3_tables.py`.

---

### Phase 7: Dashboard UI & Zone Management Console
- **Goal**: Provide UI for Zone management and policy configuration.
- **Planned Changes**:
  1. Build Zone list, PPE requirement rule editor, and camera-to-zone assignment pages in React.

---

### Phase 8: Hardening & Validation
- **Goal**: Telemetry, security hardening, and load capacity validation.
- **Planned Changes**:
  1. Scrape Prometheus metrics from all services and configure Grafana dashboards.
  2. Execute multi-camera load testing and generate capacity report.

---

## 4. Final Acceptance & Verification Checklist

- [ ] Client can run **ONLY `innovision-platform`** (`docker compose up`) and experience complete UC3 PPE detection without starting `PPE_DETECTION`.
- [ ] Standalone `PPE_DETECTION` repo remains 100% read-only and untouched.
- [ ] Existing UC2 and UC4 services continue to operate without regression.
- [ ] UC3 consumes `frames:{camera_id}` via `uc3_group` using `XREADGROUP`.
- [ ] UC3 uses `FrameEvent.frame_reference` directly according to `frame_provider` (`redis` vs `minio`).
- [ ] `uc3_events` table contains `event_type`, `frame_reference`, `frame_provider`, and `metadata`.
- [ ] `AlertEvent.source_event_id` references real persisted UUIDs in `uc3_events`.
- [ ] UC3 alert snapshots uploaded to `innovision-snapshots` under `uc3/alerts/{YYYY-MM-DD}/{alert_id}.jpg`.
- [ ] UC3 accesses Camera Registry read-only (GET routes only, no `PATCH /status` calls).
- [ ] Dashboard renders live MJPEG feeds and correctly letterboxed bounding box overlays (no PPE detection logic in React).
- [ ] `GET /health` and `GET /metrics` exposed on UC3 (port 8023).
