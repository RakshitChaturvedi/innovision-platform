# Phase 7A — Route-to-API Permission Matrix

**Date:** October 11, 2026  
**Platform:** Innovision Industrial Video Intelligence & Safety Platform  
**Document:** `docs/phase-7a-permission-matrix.md`  

---

## 1. Overview & Role Hierarchy

This matrix defines the authoritative mapping between **Frontend Dashboard Routes / Components** and **Backend Microservice HTTP Endpoints**, specifying the required role level, tenant ownership scoping, and expected security responses for unauthenticated and unauthorized requests.

### Role Hierarchy & Definitions
* **`viewer` (Plant Viewer):** Read-only situational awareness. Observes live CCTV feeds, video wall, analytics trends, and camera status. Prohibited from mutating any operational or configuration state.
* **`operator` (Shift Operator):** Real-time operational triage. Acknowledges and resolves alerts, creates incidents, investigates evidence, adds comments, transitions incident lifecycle (up to `resolved`), and generates shift handover reports.
* **`admin` / `org_admin` (Organization / Plant Admin):** Facility authority. Onboards and configures cameras, defines plant sites/zones and safety PPE enforcement policies, performs full incident lifecycle closure (`closed`), reviews forensic audit logs, and configures organization settings. Strictly scoped to their own tenant organization.
* **`superadmin` (Platform Superadministrator):** Global multi-tenant sovereignty. Provisions tenant organizations, creates and manages user accounts and RBAC across all tenants, monitors microservice cluster daemons, and exercises unrestricted cross-organization administrative oversight.

---

## 2. Route-to-API Permission Matrix

| Frontend Route / Component | HTTP Method & Backend Endpoint | Resource Entity | Required Role | Tenant Ownership Scope Rule | Unauthenticated Response | Unauthorized Response | Required Automated Test |
| :--- | :--- | :--- | :---: | :--- | :---: | :---: | :--- |
| **Public / Login** (`/login`) | `POST /auth/login` | Session / JWT | Public | Global; validates active user | 401 (Bad Credentials) | 403 (Deactivated Account) | `test_auth_login_success`, `test_deactivated_user_login` |
| **Public / Refresh** | `POST /auth/refresh` | Session Token | Public | Validates session token hash | 401 | 401 | `test_auth_token_refresh` |
| **AppLayout / Logout** | `POST /auth/logout` | Session | `viewer`+ | Revokes active user sessions | 401 | 403 | `test_auth_logout` |
| **AppLayout / Profile** | `GET /auth/me` | User Profile | `viewer`+ | Returns caller's profile only | 401 | 403 | `test_auth_get_me` |
| **User Access** (`/admin/users`) | `GET /auth/users` | Users List | `org_admin`+ | Scoped to caller's `org_id`; Superadmin sees all | 401 | 403 | `test_list_users_org_scoped`, `test_viewer_list_users_forbidden` |
| **User Access** (`/admin/users`) | `POST /auth/users` | User Account | `org_admin`+ | Scoped to caller's `org_id`; Superadmin creates any | 401 | 403 | `test_create_user_privilege_escalation_blocked` |
| **User Access** (`/admin/users`) | `GET /auth/users/{id}` | User Details | `org_admin`+ | Target user `org_id` must match caller | 401 | 403 | `test_get_foreign_user_forbidden` |
| **User Access** (`/admin/users`) | `PUT /auth/users/{id}` | User Role/Org | `org_admin`+ | Target user `org_id` must match caller | 401 | 403 | `test_update_foreign_user_forbidden` |
| **User Access** (`/admin/users`) | `PUT /auth/users/{id}/status` | User Status | `org_admin`+ | Target user `org_id` must match caller | 401 | 403 | `test_toggle_foreign_user_status_forbidden` |
| **Dashboard / Live Monitoring** (`/`, `/live-monitoring`) | `GET /cameras` | Camera Feeds | `viewer`+ | Scoped to caller's `org_id`; Superadmin sees all | 401 | 403 | `test_list_cameras_tenant_isolation` |
| **Camera Detail** (`/cameras/:id`) | `GET /cameras/{id}` | Camera Config | `viewer`+ | Camera `organization_id` must match caller | 401 | 403 | `test_get_foreign_camera_forbidden` |
| **Camera Detail** (`/cameras/:id`) | `GET /cameras/{id}/status` | Stream Status | `viewer`+ | Camera `organization_id` must match caller | 401 | 403 | `test_get_foreign_camera_status_forbidden` |
| **Camera Detail** (`/cameras/:id`) | `GET /cameras/{id}/hierarchy` | Spatial Context | `viewer`+ | Camera `organization_id` must match caller | 401 | 403 | `test_get_foreign_camera_hierarchy_forbidden` |
| **Camera Detail / Admin** | `PATCH /cameras/{id}/status` | Stream Status | `org_admin`+ | Camera `organization_id` must match caller | 401 | 403 | `test_viewer_patch_camera_status_forbidden` |
| **Camera Admin** (`/admin/cameras`) | `POST /cameras` | Physical Camera | `org_admin`+ | New camera `org_id` forced to caller's `org_id` | 401 | 403 | `test_create_camera_cross_org_rejected` |
| **Camera Admin** (`/admin/cameras`) | `PUT /cameras/{id}/config` | Camera Stream | `org_admin`+ | Camera `organization_id` must match caller | 401 | 403 | `test_update_foreign_camera_config_forbidden` |
| **Camera Admin** (`/admin/cameras`) | `PUT /cameras/{id}/assign-zone` | Zone Mapping | `org_admin`+ | Camera and Zone must belong to caller's org | 401 | 403 | `test_assign_camera_foreign_zone_forbidden` |
| **Camera Admin** (`/admin/cameras`) | `DELETE /cameras/{id}` | Physical Camera | `superadmin` | Superadmin only | 401 | 403 | `test_org_admin_delete_camera_forbidden` |
| **Sites & Zones** (`/sites-zones`) | `GET /sites` | Plant Sites | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_list_sites_scoped_to_org` |
| **Sites & Zones** (`/sites-zones`) | `POST /sites` | Plant Site | `org_admin`+ | Site `organization_id` forced to caller's `org_id` | 401 | 403 | `test_create_site_foreign_org_forbidden` |
| **Sites & Zones** (`/sites-zones`) | `GET /zones` | Safety Zones | `viewer`+ | Scoped to caller's `org_id` via site join | 401 | 403 | `test_list_zones_scoped_to_org` |
| **Sites & Zones** (`/sites-zones`) | `POST /zones` | Safety Zone | `org_admin`+ | Target `site_id` must belong to caller's org | 401 | 403 | `test_create_zone_foreign_site_forbidden` |
| **Sites & Zones** (`/sites-zones`) | `GET /zones/{id}/analytics` | Zone Policy | `viewer`+ | Zone's site `org_id` must match caller | 401 | 403 | `test_get_foreign_zone_analytics_forbidden` |
| **Sites & Zones** (`/sites-zones`) | `PUT /zones/{id}/analytics` | Zone Policy | `org_admin`+ | Zone's site `org_id` must match caller | 401 | 403 | `test_update_foreign_zone_analytics_forbidden` |
| **Sites & Zones** (`/sites-zones`) | `GET /zones/{id}/ppe-rules` | PPE Rules | `viewer`+ | Zone's site `org_id` must match caller | 401 | 403 | `test_get_foreign_zone_ppe_rules_forbidden` |
| **Sites & Zones** (`/sites-zones`) | `PUT /zones/{id}/ppe-rules` | PPE Rules | `org_admin`+ | Zone's site `org_id` must match caller | 401 | 403 | `test_update_foreign_zone_ppe_rules_forbidden` |
| **Analytics Catalog** | `GET /analytics/catalog` | Model Catalog | `viewer`+ | Global catalog read-only | 401 | 403 | `test_list_analytics_catalog_authenticated` |
| **Settings / Subscriptions** | `GET /organizations/{id}/subscriptions` | Subscriptions | `viewer`+ | Target `org_id` must match caller | 401 | 403 | `test_get_foreign_org_subscriptions_forbidden` |
| **Settings / Subscriptions** | `POST /organizations/{id}/subscriptions` | Subscriptions | `superadmin` | Global subscription assignment | 401 | 403 | `test_org_admin_create_subscription_forbidden` |
| **Settings / Subscriptions** | `DELETE /organizations/{id}/subscriptions/{aid}` | Subscriptions | `superadmin` | Global subscription revocation | 401 | 403 | `test_org_admin_delete_subscription_forbidden` |
| **Camera Detail / Overrides** | `GET /cameras/{id}/analytics/overrides` | Overrides | `viewer`+ | Camera `organization_id` must match caller | 401 | 403 | `test_get_foreign_camera_overrides_forbidden` |
| **Camera Detail / Overrides** | `PUT /cameras/{id}/analytics/{aid}/override` | Overrides | `org_admin`+ | Camera `organization_id` must match caller | 401 | 403 | `test_set_foreign_camera_override_forbidden` |
| **Camera Detail / Overrides** | `DELETE /cameras/{id}/analytics/{aid}/override` | Overrides | `org_admin`+ | Camera `organization_id` must match caller | 401 | 403 | `test_delete_foreign_camera_override_forbidden` |
| **Camera Detail / Effective** | `GET /cameras/{id}/analytics/effective` | Effective Analytics | `viewer`+ | Camera `organization_id` must match caller | 401 | 403 | `test_get_foreign_camera_effective_forbidden` |
| **Live Alerts** (`/alerts`) | `GET /alerts` | Alerts Feed | `viewer`+ | Scoped to caller's `org_id` via camera join | 401 | 403 | `test_list_alerts_tenant_isolated`, `test_unauthenticated_alerts_rejected` |
| **Live Alerts** (`/alerts`) | `PATCH /alerts/{id}/acknowledge` | Alert Triage | `operator`+ | Alert's camera must belong to caller's org | 401 | 403 | `test_viewer_acknowledge_alert_forbidden`, `test_ack_foreign_alert_forbidden` |
| **Live Alerts** (`/alerts`) | `PATCH /alerts/{id}/resolve` | Alert Triage | `operator`+ | Alert's camera must belong to caller's org | 401 | 403 | `test_viewer_resolve_alert_forbidden`, `test_resolve_foreign_alert_forbidden` |
| **Live Alerts** (`/alerts`) | `GET /alerts/unacknowledged` | Pending Alerts | `viewer`+ | Scoped to caller's `org_id` via camera join | 401 | 403 | `test_unacknowledged_alerts_scoped` |
| **Live Alerts** (`/alerts`) | `GET /alerts/count` | Pending Count | `viewer`+ | Scoped to caller's `org_id` via camera join | 401 | 403 | `test_alert_count_scoped` |
| **Incidents** (`/incidents`) | `GET /incidents` | Incident List | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_list_incidents_tenant_isolated` |
| **Incidents** (`/incidents`) | `GET /incidents/summary` | Summary KPIs | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_incident_summary_scoped` |
| **Incidents** (`/incidents/:id`) | `GET /incidents/{id}` | Incident Detail | `viewer`+ | Incident `organization_id` must match caller | 401 | 403 | `test_get_foreign_incident_forbidden` |
| **Incidents** (`/incidents`) | `POST /incidents` | Incident Ticket | `operator`+ | New incident `org_id` forced to caller's org | 401 | 403 | `test_viewer_create_incident_forbidden` |
| **Incidents** (`/incidents/:id`) | `PUT /incidents/{id}` | Incident Metadata | `operator`+ | Incident `organization_id` must match caller | 401 | 403 | `test_viewer_update_incident_forbidden` |
| **Incidents** (`/incidents/:id`) | `PUT /incidents/{id}/status` | Status: `acknowledged`, `investigating`, `resolved` | `operator`+ | Incident `organization_id` must match caller | 401 | 403 | `test_viewer_change_status_forbidden`, `test_invalid_transition_rejected` |
| **Incidents** (`/incidents/:id`) | `PUT /incidents/{id}/status` | Status: `closed` | `org_admin`+ | Incident `organization_id` must match caller | 401 | 403 | `test_operator_close_incident_forbidden`, `test_admin_close_incident_allowed` |
| **Incidents** (`/incidents/:id`) | `PUT /incidents/{id}/assign` | Assigned Officer | `operator`+ | Incident and Assignee must belong to caller org | 401 | 403 | `test_viewer_assign_incident_forbidden`, `test_assign_foreign_user_forbidden` |
| **Incidents** (`/incidents/:id`) | `POST /incidents/{id}/alerts/{aid}` | Link Alert | `operator`+ | Both Incident & Alert must belong to caller org | 401 | 403 | `test_viewer_link_alert_forbidden`, `test_link_foreign_alert_forbidden` |
| **Incidents** (`/incidents/:id`) | `DELETE /incidents/{id}/alerts/{aid}`| Unlink Alert | `operator`+ | Incident must belong to caller org | 401 | 403 | `test_viewer_unlink_alert_forbidden` |
| **PDF Reports** (`/reports`) | `GET /reports/summary` | Analytics Summary | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_report_summary_scoped` |
| **PDF Reports** (`/reports`) | `GET /reports/alerts` | Alert Report CSV | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_report_alerts_scoped` |
| **PDF Reports** (`/reports`) | `GET /reports/incidents` | Incident Report | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_report_incidents_scoped` |
| **PDF Reports** (`/reports`) | `GET /reports/analytics` | Safety Adherence | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_report_analytics_scoped` |
| **PDF Reports** (`/reports`) | `POST /reports/generate` | Generate PDF | `operator`+ | Async Celery task scoped to caller | 401 | 403 | `test_viewer_generate_report_forbidden` |
| **PDF Reports** (`/reports`) | `GET /reports/{id}/status` | PDF Task Status | `viewer`+ | Report `generated_by` / org must match caller | 401 | 403 | `test_unauthenticated_report_status_forbidden` |
| **PDF Reports** (`/reports`) | `GET /reports/{id}/download` | MinIO Presigned URL | `viewer`+ | Report `generated_by` / org must match caller | 401 | 403 | `test_unauthenticated_report_download_forbidden` |
| **PDF Reports** (`/reports`) | `GET /reports` | Reports Archive | `viewer`+ | Scoped to caller's `org_id` | 401 | 403 | `test_list_reports_scoped_to_org` |
| **Audit Ledger** (`/audit-log`) | `GET /audit` | Audit Trail | `org_admin`+ | Scoped to caller's `org_id`; Superadmin sees all | 401 | 403 | `test_operator_view_audit_forbidden`, `test_audit_cross_org_forbidden` |
| **Audit Ledger** (`/audit-log`) | `GET /audit/{id}` | Audit Event | `org_admin`+ | Audit entry org must match caller | 401 | 403 | `test_get_foreign_audit_entry_forbidden` |
| **Platform Settings** (`/settings`) | `GET /settings` | Settings Overview | `org_admin`+ | Scoped to caller's `org_id` | 401 | 403 | `test_operator_view_settings_forbidden` |
| **Platform Settings** (`/settings`) | `GET /settings/organization` | Org Metadata | `org_admin`+ | Scoped to caller's `org_id` | 401 | 403 | `test_operator_get_org_settings_forbidden` |
| **Platform Settings** (`/settings`) | `PUT /settings/organization` | Org Metadata | `org_admin`+ | Updates caller's `org_id` only | 401 | 403 | `test_update_foreign_org_settings_forbidden` |
| **Notification Center** | `GET /notifications` | Notifications | `viewer`+ | Scoped to caller user ID | 401 | 403 | `test_list_notifications_user_scoped` |
| **Notification Center** | `PUT /notifications/{id}/read` | Notification Read | `viewer`+ | Target notification must belong to caller | 401 | 403 | `test_mark_foreign_notification_forbidden` |
| **Notification Settings** | `GET /notifications/preferences` | User Preferences | `viewer`+ | Scoped to caller user ID | 401 | 403 | `test_get_notification_preferences_scoped` |
| **Notification Settings** | `PUT /notifications/preferences` | User Preferences | `viewer`+ | Updates caller's preferences only | 401 | 403 | `test_update_notification_preferences_scoped` |

---

## 3. Enforcement Strategy & Security Principles

1. **Strict Defense in Depth:**
   * Frontend route guards (`RoleRoute`, `ProtectedRoute`) prevent unauthorized view navigation.
   * Component-level permission checks disable or hide mutation controls (Acknowledge, Resolve, New Incident, Onboard Camera, Configure Zones).
   * **Backend dependencies (`require_role`, ownership verifiers) remain 100% authoritative.** Even if a client bypasses the frontend, the API returns `401 Unauthorized` or `403 Forbidden`.
2. **Deterministic Response Codes:**
   * Missing or invalid Bearer token: **`401 Unauthorized`**.
   * Valid token, but role rank below required threshold: **`403 Forbidden`**.
   * Valid token, but resource ID belongs to another tenant: **`403 Forbidden`** (or `404 Not Found` if resource does not exist).
3. **Privilege Escalation Immunity:**
   * User creation and update schemas reject attempts by non-Superadmins to create `superadmin` accounts or reassign users to foreign organizations.
4. **Audit Logging Integration:**
   * All security-critical mutations (user creation/updates, status changes, camera creations, policy updates, alert resolutions, incident lifecycle transitions) generate immutable entries in `audit_log`.
