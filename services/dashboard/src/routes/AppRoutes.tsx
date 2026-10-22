import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";

import { LandingPage } from "@/pages/LandingPage";
import { Login } from "@/pages/Login";
import { Unauthorized } from "@/pages/Unauthorized";

import MasterDashboard from "@/pages/MasterDashboard";
import { LiveMonitoring } from "@/pages/LiveMonitoring";
import CameraDetail from "@/pages/CameraDetail";
import Alerts from "@/pages/Alerts";
import { Incidents } from "@/pages/Incidents";
import { Reports } from "@/pages/Reports";
import { AnalyticsPage } from "@/pages/AnalyticsPage";
import { SitesZonesPage } from "@/pages/SitesZonesPage";
import { AuditLogPage } from "@/pages/AuditLogPage";
import { SettingsPage } from "@/pages/SettingsPage";

import { Cameras } from "@/pages/admin/Cameras";
import { Users } from "@/pages/admin/Users";

import { ProtectedRoute } from "./ProtectedRoute";
import { RoleRoute } from "./RoleRoute";

export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public & Showcase */}
        <Route path="/landing" element={<LandingPage />} />
        <Route path="/login" element={<Login />} />
        <Route path="/unauthorized" element={<Unauthorized />} />

        {/* Authenticated */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            {/* Platform Control Center / Operations Master Dashboard */}
            <Route path="/" element={<MasterDashboard />} />
            <Route path="/dashboard" element={<MasterDashboard />} />
            <Route path="/analytics" element={<AnalyticsPage />} />

            {/* Operational Video Wall & Camera Detections: Company Roles Only (admin, org_admin, operator, viewer) */}
            <Route element={<RoleRoute allowedRoles={["admin", "org_admin", "operator", "viewer"]} />}>
              <Route path="/live-monitoring" element={<LiveMonitoring />} />
              <Route path="/cameras/:cameraId" element={<CameraDetail />} />
            </Route>

            {/* Company Alert Queue & Incident Triage: Operator and Org Admins only */}
            <Route element={<RoleRoute allowedRoles={["admin", "org_admin", "operator"]} />}>
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/incidents" element={<Incidents />} />
            </Route>

            {/* Safety Compliance Reporting: Operator and Org Admins */}
            <Route element={<RoleRoute allowedRoles={["admin", "org_admin", "operator"]} />}>
              <Route path="/reports" element={<Reports />} />
            </Route>

            {/* Organization Facility Fleet & Policies: Org Admin / Admin only */}
            <Route element={<RoleRoute allowedRoles={["admin", "org_admin"]} />}>
              <Route path="/sites-zones" element={<SitesZonesPage />} />
              <Route path="/admin/cameras" element={<Cameras />} />
            </Route>

            {/* Governance, Audit & Settings: Admin & Superadmin */}
            <Route element={<RoleRoute allowedRoles={["superadmin", "admin", "org_admin"]} />}>
              <Route path="/audit-log" element={<AuditLogPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>

            {/* Sovereign Platform User Governance: Superadmin only */}
            <Route element={<RoleRoute allowedRoles={["superadmin"]} />}>
              <Route path="/admin/users" element={<Users />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}