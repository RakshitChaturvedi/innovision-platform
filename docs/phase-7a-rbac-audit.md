# Phase 7A — RBAC Expansion, Tenant Security & Role-Based UX Audit Report

**Date:** October 11, 2026  
**Platform:** Innovision Industrial Video Intelligence & Safety Platform  
**Target Architecture:** Multi-Tenant Role-Based Access Control (RBAC) & Tenant Security Hardening  
**Scope:** Read-Only Audit of Authentication, Authorization, Resource Ownership, Route Protection, and Role UX  

---

## Executive Summary

This comprehensive audit inspects the current checkout of the **Innovision Platform** across backend services, database migrations, API routers, frontend dashboard components, test suites, and Docker container configurations.

The platform's baseline includes camera hierarchy (Organization $\rightarrow$ Site $\rightarrow$ Zone $\rightarrow$ Camera), analytics catalog subscriptions, zone safety policies, camera effective analytics, native UC3 PPE detection engine, alert management, incident tracking, audit trails, reporting, and notifications.

However, a thorough line-by-line inspection reveals critical security and isolation gaps:
1. **Missing Backend Mutation Guards:** Key mutation endpoints (e.g., incident creation/updates, camera status patching, alert acknowledgements) either lack role dependencies or allow lower roles (such as `viewer`) to execute mutations.
2. **Cross-Tenant Leakage on Targeted IDs:** While listing endpoints frequently filter by organization, individual resource retrieval and mutation endpoints (such as `GET /cameras/{id}`, `GET /zones/{id}/analytics`, `PUT /cameras/{id}/config`, `PATCH /alerts/{id}/acknowledge`) do not verify that the target resource belongs to the authenticated user's organization.
3. **Unauthenticated Endpoints:** Several endpoints that expose sensitive telemetry or reports (`GET /reports/{id}/status`, `GET /reports/{id}/download`, `GET /cameras/by-uc/{uc_id}`, `GET /alerts`) allow unauthenticated access or use `get_optional_user`.
4. **Incident Workflow Authorization:** Incident closure (`closed` status) and incident creation/assignment lack role gates in the API layer, allowing any authenticated user to transition incident states.

---

## 1. Role Model & Implementation Status

### 1.1 Canonical Roles in Database & Backend
Inspection of database migrations (`migrations/versions/0001_platform_base.py` and `0008_user_organization_scope.py`) and backend RBAC definition (`services/auth/src/rbac.py`) confirms that PostgreSQL defines `operator_role` as:
```sql
CREATE TYPE operator_role AS ENUM ('superadmin', 'admin', 'operator', 'viewer', 'org_admin');
```

The backend maps these into canonical roles with explicit rank values:
| Canonical Role | System Value | Legacy Alias | Privilege Rank | Target Profile Equivalent |
| :--- | :--- | :--- | :---: | :--- |
| **Plant Viewer** | `viewer` | — | `0` | `PLANT_VIEWER` |
| **Shift Operator** | `operator` | — | `1` | `SHIFT_OPERATOR` |
| **Organization Admin** | `org_admin` | `admin` | `2` | `ORG_ADMIN` |
| **Superadmin** | `superadmin` | — | `3` | `SUPERADMIN` |

### 1.2 Verification Findings
* **`viewer`**: Fully defined in enum and rank. Intended as read-only observation desk. **Gap**: Backend endpoints currently permit viewers to perform incident mutations and view cross-tenant cameras.
* **`operator`**: Fully defined in enum and rank. Intended for live telemetry, alert triage, incident investigation. **Gap**: Can close incidents (which should be restricted to Org Admin/Superadmin) and can acknowledge alerts across tenant boundaries.
* **`org_admin` / `admin`**: `admin` is the legacy alias of `org_admin`. Both share rank `2`. Intended for plant/company administration (cameras, zones, safety policies, reports, audit logs). Scoped strictly to their assigned `organization_id`.
* **`superadmin`**: Global sovereign authority. Holds rank `3`. Global multi-tenant visibility, microservice health monitoring, and system-wide user governance.

---

## 2. API Router Authorization Audit

### 2.1 Authentication Microservice (`services/auth/src/router.py`)
* `POST /auth/login`: Public authentication endpoint. Verifies email/password hash via bcrypt and validates `is_active`. Issues JWT containing `sub`, `role`, `org_id`, and `camera_ids`.
* `POST /auth/refresh`: Public refresh token rotation.
* `POST /auth/logout`: Requires `get_current_user`. Revokes active session in database.
* `GET /auth/me`: Requires `get_current_user`. Returns caller's profile and organization metadata.
* `GET /auth/users`: Protected by `require_role(Role.ADMIN)`. Superadmin can filter by `organization_id`; Org Admin is strictly scoped to own `organization_id`.
* `POST /auth/users`: Protected by `require_role(Role.ADMIN)`. Prevents privilege escalation (only Superadmin can create Superadmin). Org Admin forced to own `org_id`.
* `GET /auth/users/{id}`, `PUT /auth/users/{id}`, `PUT /auth/users/{id}/status`: Protected by `require_role(Role.ADMIN)`. Cross-org modifications correctly rejected with 403.

### 2.2 Camera Registry Microservice (`services/camera_registry/src/router.py`)
* `GET /analytics/catalog`: **Unauthenticated**. Should require `get_current_user`.
* `GET /organizations/{org_id}/subscriptions`: Protected with `get_current_user` and validates caller's `org_id`.
* `POST /organizations/{org_id}/subscriptions`, `PUT ...`, `DELETE ...`: Protected by `require_role(Role.ADMIN)` and validates caller's `org_id`.
* `POST /organizations`: Protected by `require_role(Role.SUPERADMIN)`.
* `GET /organizations`: Requires `get_current_user`. Returns all for Superadmin, filters to caller's org for others.
* `POST /sites`: Protected by `require_role(Role.ADMIN)`. Cross-org site creation blocked.
* `GET /sites`: Requires `get_current_user`. Scoped to caller's org.
* `POST /zones`: Protected by `require_role(Role.ADMIN)`. **Critical Gap:** Does not verify that `body.site_id` belongs to caller's organization.
* `GET /zones`: Requires `get_current_user`. **Critical Gap:** Does not filter by caller's organization when `site_id` is omitted.
* `POST /cameras`: Protected by `require_role(Role.ADMIN)`. **Critical Gap:** Does not verify that `body.organization_id` or `body.site_id` belongs to caller's organization.
* `GET /cameras`: Requires `get_current_user`. Scoped to caller's org.
* `GET /cameras/by-uc/{uc_id}`: **Unauthenticated**. Internal pipeline hook; should require authentication.
* `GET /cameras/{camera_id}`: Requires `get_current_user`. **Critical Gap:** Returns camera details without verifying organization ownership.
* `GET /cameras/{camera_id}/hierarchy`: Requires `get_current_user`. **Critical Gap:** Missing organization ownership check.
* `PUT /cameras/{camera_id}/config`: Protected by `require_role(Role.ADMIN)`. **Critical Gap:** Missing organization ownership check on `camera_id`.
* `PATCH /cameras/{camera_id}/status`: Requires `get_current_user`. **Critical Gap:** Missing `require_role(Role.ADMIN)` dependency! Viewers and operators can alter camera status. Missing org check.
* `PUT /cameras/{camera_id}/assign-zone`: Protected by `require_role(Role.ADMIN)`. **Critical Gap:** Does not verify camera or zone ownership.
* `DELETE /cameras/{camera_id}`: Protected by `require_role(Role.SUPERADMIN)`. Verified.
* `GET /zones/{zone_id}/analytics`, `GET /zones/{zone_id}/ppe-rules`: **Critical Gap:** Missing zone organization verification.
* `PUT /zones/{zone_id}/analytics`, `PUT /zones/{zone_id}/ppe-rules`: Protected by `require_role(Role.ADMIN)`. Verified via service-level `user_org_id` check.
* `GET /cameras/{camera_id}/analytics/overrides`, `.../effective`: Requires `get_current_user`. **Critical Gap:** Missing camera organization ownership check.

### 2.3 Alert Management Microservice (`services/alert_management/src/router.py`)
* `GET /alerts`: Uses `get_optional_user`. **Critical Gap:** Unauthenticated users can query alerts. If authenticated, no organization filter is applied to the alerts table.
* `PATCH /alerts/{alert_id}/acknowledge`: Protected by `require_role(Role.OPERATOR)`. **Critical Gap:** Does not verify whether the alert belongs to caller's organization.
* `PATCH /alerts/{alert_id}/resolve`: Protected by `require_role(Role.OPERATOR)`. **Critical Gap:** Does not verify whether the alert belongs to caller's organization.
* `GET /alerts/unacknowledged`, `GET /alerts/count`: Requires `get_current_user`. **Critical Gap:** Missing organization isolation check.

### 2.4 Incident Management Microservice (`services/incident_management/src/router.py`)
* `GET /incidents`, `GET /incidents/summary`: Requires `get_current_user`. Organization isolation enforced in `IncidentService`.
* `GET /incidents/{incident_id}`: Requires `get_current_user`. Organization isolation enforced in `IncidentService`.
* `POST /incidents`: Requires `get_current_user`. **Critical Gap:** Missing `require_role(Role.OPERATOR)`. Viewers can create incidents.
* `PUT /incidents/{incident_id}`: Requires `get_current_user`. **Critical Gap:** Missing `require_role(Role.OPERATOR)`. Viewers can update incidents.
* `PUT /incidents/{incident_id}/status`: Requires `get_current_user`. **Critical Gap:** Missing role checks! Viewers can change status; operators can transition to `closed` (which must be restricted to `admin` / `org_admin` / `superadmin`).
* `PUT /incidents/{incident_id}/assign`: Requires `get_current_user`. **Critical Gap:** Missing `require_role(Role.OPERATOR)`. Viewers can assign incidents.
* `POST /incidents/{incident_id}/alerts/{alert_id}`, `DELETE ...`: Requires `get_current_user`. **Critical Gap:** Missing `require_role(Role.OPERATOR)`.

### 2.5 Reporting Microservice (`services/reporting/src/router.py`)
* `GET /reports/summary`, `GET /reports/alerts`, `GET /reports/incidents`, `GET /reports/analytics`: Requires `get_current_user`. Organization isolation enforced in `ReportingService`.
* `POST /reports/generate`: Protected by `require_role(Role.OPERATOR)`. Verified.
* `GET /reports/{report_id}/status`: **Critical Gap:** Completely unauthenticated! No user dependency.
* `GET /reports/{report_id}/download`: **Critical Gap:** Completely unauthenticated! No user dependency.
* `GET /reports`: Requires `get_current_user`. **Critical Gap:** Executes `SELECT * FROM reports` without organization scoping.

### 2.6 Forensic Audit & Settings Microservice (`services/audit/src/router.py`)
* `GET /audit`, `GET /audit/{id}`: Protected by `require_role(Role.ORG_ADMIN)`. Organization isolation enforced in `AuditService`.
* `GET /settings`, `GET /settings/organization`, `PUT /settings/organization`: Protected by `require_role(Role.ORG_ADMIN)`. Organization isolation enforced in `SettingsService`.

### 2.7 Notification Microservice (`services/notification/src/router.py`)
* `GET /notifications`, `GET /notifications/unread-count`, `PUT /notifications/read-all`, `PUT /notifications/{id}/read`: Protected by `get_current_user`. Scoped to `user["sub"]`.
* `GET /notifications/preferences`, `PUT /notifications/preferences`: Protected by `get_current_user`. Scoped to `user["sub"]`.

---

## 3. Cross-Organization Tenant Isolation Matrix

| Resource Entity | List Filtering Scoped? | Get by ID Scoped? | Create Scoped? | Update Scoped? | Delete Scoped? |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Organizations** | ✅ Scoped | ✅ Scoped | ✅ Superadmin | ✅ Superadmin | ✅ Superadmin |
| **Sites** | ✅ Scoped | ✅ Scoped | ✅ Scoped | ✅ Scoped | ❌ N/A |
| **Zones** | ⚠️ **Unscoped** | ⚠️ **Unscoped** | ⚠️ **No site org check** | ✅ Service-level | ❌ N/A |
| **Cameras** | ✅ Scoped | ⚠️ **Unscoped** | ⚠️ **Body org ignored** | ⚠️ **Unscoped** | ✅ Superadmin |
| **Alerts** | ⚠️ **Unscoped** | ⚠️ **Unscoped** | ✅ AlertPublisher | ⚠️ **No org check on Ack/Resolve** | ❌ N/A |
| **Incidents** | ✅ Scoped | ✅ Scoped | ✅ Scoped | ✅ Scoped | ❌ N/A |
| **Reports** | ⚠️ **Unscoped** | ⚠️ **Unauthenticated** | ✅ Scoped | ❌ N/A | ❌ N/A |
| **Audit Logs** | ✅ Scoped | ✅ Scoped | ✅ System | ❌ Read-only | ❌ Read-only |
| **Users** | ✅ Scoped | ✅ Scoped | ✅ Scoped | ✅ Scoped | ✅ Scoped |
| **Settings** | ✅ Scoped | ✅ Scoped | ❌ N/A | ✅ Scoped | ❌ N/A |

---

## 4. Frontend Route & Component Accessibility Audit

### 4.1 Route Guard Analysis (`AppRoutes.tsx` & `RoleRoute.tsx`)
The frontend defines route access via `minimumRole`:
* **Public**: `/landing`, `/login`, `/unauthorized`.
* **Viewer+** (`minimumRole: "viewer"`): `/`, `/dashboard`, `/live-monitoring`, `/analytics`, `/cameras/:cameraId`.
* **Operator+** (`minimumRole: "operator"`): `/alerts`, `/incidents`, `/reports`.
* **Admin+** (`minimumRole: "admin"`): `/sites-zones`, `/admin/cameras`, `/audit-log`, `/settings`.
* **Superadmin** (`minimumRole: "superadmin"`): `/admin/users`.

### 4.2 Frontend Vulnerabilities & Discrepancies
1. **Direct Navigation Leakage**: If a `viewer` manually navigates to `/alerts` or `/incidents`, `RoleRoute` redirects to `/unauthorized`. However, if the backend APIs lack role enforcement, any direct API call or script can execute mutations.
2. **Dashboard UI Mutation Buttons for Viewers**: The Master Dashboard hides triage buttons in viewer mode, but the backend does not enforce this denial on `POST /incidents` or `PATCH /alerts/{id}/acknowledge`.
3. **Incident Closure UI**: The incident status dropdown does not currently disable the `closed` option for operators, relying on backend checks which are currently missing.
4. **User Management Navigation Discrepancy**: Backend `/auth/users` allows `Role.ADMIN` (`org_admin`), but frontend routes restrict `/admin/users` strictly to `superadmin`. Either `org_admin` should be granted scoped user management in the frontend, or the backend should align to Superadmin-only user provisioning.

---

## 5. Existing Test Coverage Audit

### 5.1 Test Execution Results
* **`tests/contracts/test_alert_event.py`**: **11 passed**. Validates AlertEvent schema, source_uc enums, severity mapping.
* **`tests/contracts/test_frame_event.py`**: **4 passed**. Validates FrameEvent structure, Redis/MinIO providers.
* **`tests/test_uc3.py`**: **3 passed**. Validates UC3 model pipeline and class mappings.
* **`tests/auth/test_rbac_isolation.py`**: **4 passed, 2 failed** on initial run due to Windows Python 3.14 asyncpg Proactor connection handling on host port 5433 (Postgres Docker container). Tests covering token claims and role checkers passed cleanly.
* **Frontend Checks**:
  * `npm run build` (`tsc -b && vite build`): **PASS** (Zero type errors, 204 modules transformed).
  * `npx eslint src`: **PASS** (Zero lint errors).

### 5.2 Test Coverage Gaps
* No automated tests for unauthenticated access to `/reports/{id}/download` and `/reports/{id}/status`.
* No automated tests preventing `viewer` from calling `POST /incidents` or `PATCH /alerts/{id}/acknowledge`.
* No automated tests preventing `operator` from setting incident status to `closed`.
* No automated tests verifying cross-tenant isolation when requesting specific camera IDs (`GET /cameras/{foreign_id}`) or specific alert IDs (`PATCH /alerts/{foreign_id}/acknowledge`).

---

## 6. Inconsistencies Between Target Model and Actual Code

1. **Incident Workflow States**:
   * Target Lifecycle: `open → acknowledged → investigating → resolved → closed`.
   * Current Implementation (`workflow.py`): Supports `open`, `active`, `acknowledged`, `investigating`, `in_progress`, `resolved`, `closed`.
   * *Resolution*: Preserve full transition graph in `workflow.py` while ensuring operators can transition `open -> acknowledged -> investigating -> resolved`, but ONLY Admins (`admin`, `org_admin`, `superadmin`) can transition to `closed`.
2. **Alert Organization Scoping**:
   * Current schema: `alerts` table has `camera_id`, while `cameras` table has `organization_id`. `alerts` table does not directly store `organization_id`.
   * *Resolution*: When filtering or updating alerts, join `cameras` table to enforce caller's `cameras.organization_id == user["org_id"]`.
3. **Zones Organization Scoping**:
   * `zones` table has `site_id`, while `sites` table has `organization_id`.
   * *Resolution*: When listing zones or fetching zone rules, join `sites` table to enforce caller's `sites.organization_id == user["org_id"]`.

---

## 7. Minimal Implementation Plan to Close Verified Gaps

### Phase 1: Core Authorization & Scope Enforcement Dependencies
* In `services/auth/src/rbac.py`:
  * Add reusable helper `require_organization_resource_access(resource_org_id, user)` raising 403 on mismatch.
  * Ensure `require_role(minimum)` raises 401 on unauthenticated and 403 on insufficient rank.

### Phase 2: Router Hardening Across Services
1. **Camera Registry (`services/camera_registry/src/router.py`)**:
   * Add `get_current_user` to `/analytics/catalog` and `/cameras/by-uc/{uc_id}`.
   * Add ownership checks on `GET /cameras/{id}`, `GET /cameras/{id}/hierarchy`, `PUT /cameras/{id}/config`.
   * Add `require_role(Role.ADMIN)` and ownership check to `PATCH /cameras/{camera_id}/status`.
   * Enforce site ownership on `POST /zones`, `POST /cameras`, `PUT /cameras/{id}/assign-zone`.
   * Filter `GET /zones` by caller's organization via join with `sites`.
2. **Alert Management (`services/alert_management/src/router.py`)**:
   * Replace `get_optional_user` with mandatory `get_current_user` on `GET /alerts`.
   * Scope `GET /alerts`, `GET /alerts/unacknowledged`, `GET /alerts/count` to caller's organization by joining `cameras`.
   * In `PATCH /alerts/{id}/acknowledge` and `PATCH /alerts/{id}/resolve`, verify that `alerts.camera_id` belongs to caller's organization before applying update.
3. **Incident Management (`services/incident_management/src/router.py` & `service.py`)**:
   * Add `require_role(Role.OPERATOR)` to `POST /incidents`, `PUT /incidents/{id}`, `PUT /incidents/{id}/assign`, `POST .../alerts/...`, `DELETE .../alerts/...`.
   * In `update_status`: verify caller has `Role.OPERATOR` for standard transitions, and strictly require `Role.ADMIN` (`admin`, `org_admin`, `superadmin`) for transitioning to `closed`.
4. **Reporting Service (`services/reporting/src/router.py`)**:
   * Add `get_current_user` and ownership check to `GET /reports/{id}/status` and `GET /reports/{id}/download`.
   * Scope `GET /reports` to caller's organization.

### Phase 3: Frontend UX Hardening
* In `Alerts.tsx`, `Incidents.tsx`, `CameraDetail.tsx`: hide/disable action buttons if user lacks mutation privileges.
* Keep server-side API authoritative at all times.

### Phase 4: Automated Security & Regression Suite
* Create comprehensive security test suite covering:
  * Unauthenticated access rejection (401).
  * Role permission rejection (403 for viewer attempting mutation).
  * Cross-tenant resource rejection (403 for Org Admin attempting to access another org's camera/zone/alert).
  * Incident status transition enforcement (Operator blocked from `closed`).
  * UC3 and contracts regression validation.
