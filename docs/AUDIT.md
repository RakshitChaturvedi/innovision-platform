# Innovision Platform — Phase 1 Technical Audit Report (AUDIT.md)

**Date:** October 6, 2026  
**Repository:** `innovision-platform` (Integration Base) & `PPE_DETECTION` (Immutable Ground-Truth Reference)  
**Branch:** `feature/uc2-uc4-uc3`  
**Author:** Senior Staff Engineer & Solution Architect  

---

## Executive Summary

Innovision is a video analytics operations platform. This technical audit provides a precise analysis of `innovision-platform` and the standalone reference codebase `PPE_DETECTION`.

### Key Directives & Scope Constraints:
1. **Standalone Project Protection**: The `PPE_DETECTION` repository is strictly **READ-ONLY**. No files, models, or configurations in `PPE_DETECTION` will be edited.
2. **Self-Contained Client Deployment**: The final deliverable runs **ONLY from `innovision-platform`** (`docker compose up`). The standalone `PPE_DETECTION` project will NOT be started or required at runtime.
3. **Native UC3 Integration**: All required PPE model inference, ByteTrack tracking, compliance rules, cascaded filtering gates, and spatial association code from `PPE_DETECTION` will be integrated natively into `innovision-platform/services/uc3`.
4. **Preservation of Existing Functionality**: Existing Use Cases (**UC2** and **UC4**) and platform services MUST remain completely intact and functional as they operate now.
5. **Single PostgreSQL Database**: All persistence uses the single `innovision_platform` database. UC3 creates UC3-owned tables (`uc3_events`, `uc3_compliance_events`, `uc3_zones`, `uc3_zone_ppe_rules`) via Alembic and NEVER writes directly to platform-owned tables (`cameras`, `users`, `alerts`, `incidents`, `audit_log`, `notification_log`, `reports`).
6. **Strict Scope Control**: Avoid broad multi-tenancy schema refactoring across platform tables (`cameras`, `users`, `alerts`, `incidents`, `audit_log`) during UC3 integration. Scope is focused strictly on native UC3 integration, frame event consumption, event traceability, and UI overlay rendering.

---

## 1. Current System & Data Flow Architecture

```text
                                [ Physical / Virtual Cameras ]
                                              │ (RTSP / MP4 Streams)
                                              ▼
                             ┌──────────────────────────────────┐
                             │     Ingestion Microservice       │
                             │  FFmpeg -> Sampler -> Encoder    │
                             └────────────────┬─────────────────┘
                                              │
                      ┌───────────────────────┼───────────────────────┐
                      │ (Hot Path: JPEGs)     │ (FrameEvent Metadata) │ (Cold Path)
                      ▼                       ▼                       ▼
             ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
             │   Redis Cache   │    │   Redis Stream   │    │   MinIO Object   │
             │ frame:{cam}:{seq}│    │frames:{camera_id}│    │ innovision-frames│
             └────────┬────────┘    └────────┬─────────┘    └──────────────────┘
                      │                      │
                      └───────────┬──────────┘
                                  │
        ┌─────────────────────────┼─────────────────────────┬─────────────────────────┐
        ▼ (uc1_group)             ▼ (uc2_group)             ▼ (uc3_group)             ▼ (uc4_group)
┌─────────────────┐      ┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│   UC1 Service   │      │   UC2 Service   │       │   UC3 Service   │       │   UC4 Service   │
│ People Counting │      │  Fire & Smoke   │       │ PPE Compliance  │       │ Vehicle Motion  │
│ (uc1_v2 demo)   │      │   (uc2_stub)    │       │ (Native UC3)    │       │   (uc4_stub)    │
└────────┬────────┘      └────────┬────────┘       └────────┬────────┘       └────────┬────────┘
         │                        │                         │                         │
         │ AlertEvent             │ AlertEvent              │ AlertEvent              │ AlertEvent
         └────────────────────────┴────────────┬────────────┴─────────────────────────┘
                                               │
                                               ▼
                                 ┌──────────────────────────┐
                                 │ Redis Stream: alerts:live│
                                 └────────────┬─────────────┘
                                              │
                                              ▼
                                 ┌──────────────────────────┐
                                 │ Alert Management Service │
                                 │ Validation & Escalation  │
                                 └────────────┬─────────────┘
                                              │
        ┌─────────────────────────────────────┼─────────────────────────────────────┐
        ▼                                     ▼                                     ▼
┌──────────────────────────┐       ┌──────────────────────────┐       ┌──────────────────────────┐
│  PostgreSQL Database     │       │   Socket.IO Gateway      │       │ Notification Escalation  │
│  (innovision_platform)   │       │  room: camera:{id}       │       │ Celery -> SMTP / Email   │
└──────────────────────────┘       └──────────────────────────┘       └──────────────────────────┘
```

---

## 2. Technical Audit & Corrected Specifications

### 2.1 Database Structure (`migrations/versions/0001_platform_base.py`)
- **Target Single Database**: `innovision_platform` on PostgreSQL 16.
- **Platform Tables Currently Present**: `cameras`, `users`, `sessions`, `alerts`, `incidents`, `incident_timeline`, `audit_log`, `notification_log`.
- **Platform Bug Fix**: `reports` table is missing from Alembic migration `0001` (causes reporting Celery worker errors). It will be added via Alembic.
- **UC3-Owned Tables**: `uc3_events`, `uc3_compliance_events`, `uc3_zones`, `uc3_zone_ppe_rules` will be created inside `innovision_platform`.
- **Scope Rule**: Platform tables (`cameras`, `users`, `alerts`, `incidents`, `audit_log`) will NOT be modified with multi-tenancy columns during the UC3 integration phase.

### 2.2 FrameEvent Contract & Frame Provider Loading
- **Consuming `frames:{camera_id}`**: UC3 consumes via `XREADGROUP` using consumer group `uc3_group`.
- **Strict Frame Provider Resolution**: UC3 deserializes the `FrameEvent` payload and uses `FrameEvent.frame_reference` directly rather than reconstructing Redis key names:
  - If `frame_provider == "redis"`: Load bytes from Redis using `frame_reference`.
  - If `frame_provider == "minio"`: Download object from MinIO bucket `innovision-frames` using `frame_reference`.

### 2.3 MinIO Storage & Ingestion Pipeline Findings
- **Bucket Creation**: `create_buckets.py` is not executed automatically on `docker compose up`. If buckets `innovision-frames` and `innovision-snapshots` are missing, MinIO writes fail.
- **Ingestion Failure Coupling Bug**: In `services/ingestion/src/camera_task.py`, a failure during MinIO frame upload catches an exception and aborts publishing to Redis stream. This will be fixed in Phase 2 so MinIO archival errors log warnings without blocking hot-path Redis stream publishing.

### 2.4 Live Feed, Overlay API & Camera Registry Permissions
- **Live Feed Black Video Tiles**: `LiveFeed.tsx` defaults `STREAM_URL` to `http://localhost:8000` (Auth service!) instead of Ingestion (port 8020) or Nginx gateway.
- **Bounding Box Overlay Misalignment**: `CameraOverlay.tsx` currently multiplies normalized coordinates (`0.0`–`1.0`) by full container `width` and `height`. When aspect ratios mismatch (e.g. 16:9 video in 4:3 container), `object-fit: contain` introduces letterbox bars. `CameraOverlay.tsx` will calculate aspect-ratio letterbox offsets to correctly align boxes over displayed video.
- **Preservation of UC2 & UC4**: `CameraOverlay.tsx` will preserve `UC2_API_URL` (8022) and `UC4_API_URL` (8024) while adding `UC3_API_URL` (8023) and `UC1_API_URL` (8021).
- **Camera Registry Read-Only Access**: UC3 ONLY reads camera configuration via `GET` endpoints (`GET /cameras/by-uc/uc3`, `GET /cameras/{id}`). UC3 will NEVER call `PATCH /cameras/{id}/status` or modify camera records.

### 2.5 Standalone `PPE_DETECTION` Reference vs `innovision-platform` UC3
- **Standalone `PPE_DETECTION` Engine**:
  - Model: Ultralytics YOLO (`backend/models/best.pt`).
  - Class Mapping: `helmet`, `vest`, `gloves`, `shoes`, `goggles`, `mask`, `no-helmet`, `no-vest`, `no-gloves`, `no-shoe`, `no-goggles`, `no-mask`, `person`.
  - Cascaded Gates: `motion_gate.py` (MOG2) -> `person_gate.py` (YOLO person check) -> `mannequin_gate.py` (texture/edge analysis).
  - Tracking: ByteTrack integration (`tracker_config.yaml`).
  - Compliance Engine: `compliance.py` (hybrid IoU/distance spatial association, duration-weighted sliding time window persistence `VIOLATION_WINDOW_SECONDS = 2.0`).
- **Platform UC3 Implementation (`services/uc3`)**:
  - All required standalone Python logic (`compliance.py`, `motion_gate.py`, `person_gate.py`, `mannequin_gate.py`, `tracker_config.yaml`, `best.pt`, `ppe_config.py`) will be copied natively into `services/uc3/src/`. No PPE detection logic will exist in the React frontend.

---

## 3. Corrected `uc3_events` Schema Specification

The `uc3_events` table preserves complete traceability for `BaseAnalyticsEvent` and debugging, ensuring `AlertEvent.source_event_id` references a real persisted event:

```sql
CREATE TABLE uc3_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    organization_id UUID NULL,
    camera_id UUID NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    zone_id UUID NULL,
    track_id INTEGER NULL,
    event_type VARCHAR(100) NOT NULL, -- e.g. 'ppe_detected', 'compliance_check', 'ppe_violation'
    missing_ppe TEXT[] NOT NULL DEFAULT '{}',
    present_ppe TEXT[] NOT NULL DEFAULT '{}',
    compliance_score FLOAT NOT NULL DEFAULT 1.0,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    frame_reference VARCHAR(512) NULL,
    frame_provider VARCHAR(50) NULL,
    metadata JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX idx_uc3_events_camera_time ON uc3_events(camera_id, timestamp);
CREATE INDEX idx_uc3_events_event_type ON uc3_events(event_type);
```

---

## 4. Gap Analysis & Resolution Matrix

| Domain / Component | Current State (`innovision-platform`) | Target State (Integrated System) | Resolution |
|---|---|---|---|
| **Standalone PPE Repo** | Untouched | Remains 100% read-only & untouched | Enforced |
| **UC3 Engine** | Synthetic stub (`stubs/uc3_stub`) | Native Python microservice (`services/uc3`) running standalone PPE engine | High Priority |
| **UC2 & UC4 Services** | Working stubs (`uc2_stub`, `uc4_stub`) | Kept fully operational & backward compatible | Enforced |
| **Frame Loading** | Hardcoded key assumptions | Uses `FrameEvent.frame_reference` via `frame_provider` (`redis`/`minio`) | Corrected |
| **`uc3_events` Schema** | Missing fields | Schema extended with `event_type`, `frame_reference`, `frame_provider`, `metadata` | Corrected |
| **Database Tenancy Scope** | Proposed broad modifications | Broad multi-tenancy schema refactoring removed from UC3 phase | Corrected |
| **Camera Registry** | Missing GET route | GET routes implemented; UC3 is read-only (no PATCH /status calls) | Corrected |
| **Alert Publishing** | Stubs use random UUIDs / raw Redis write | UC3 persists `uc3_events` -> real `source_event_id` -> `AlertPublisher` -> `alerts:live` | Critical |
| **Snapshots** | None in UC3 stub | Annotated JPEG uploaded to `innovision-snapshots` at `uc3/alerts/{date}/{alert_id}.jpg` | Required |
| **UC3 Overlay API** | Missing | `GET /uc3/cameras/{id}/latest-detections` returning normalized boxes (`0.0`–`1.0`) | Required |
| **Dashboard Overlay** | Unscaled, missing UC3 | Letterbox-aware box scaling supporting UC1, UC2, UC3, UC4 | Required |
