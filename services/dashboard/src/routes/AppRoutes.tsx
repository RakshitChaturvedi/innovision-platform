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
            {/* Viewer+ */}
            <Route path="/" element={<MasterDashboard />} />
            <Route path="/dashboard" element={<MasterDashboard />} />
            <Route path="/live-monitoring" element={<LiveMonitoring />} />
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/cameras/:cameraId" element={<CameraDetail />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/incidents" element={<Incidents />} />

            {/* Operator+ */}
            <Route element={<RoleRoute minimumRole="operator" />}>
              <Route path="/reports" element={<Reports />} />
            </Route>

            {/* Admin+ */}
            <Route element={<RoleRoute minimumRole="admin" />}>
              <Route path="/sites-zones" element={<SitesZonesPage />} />
              <Route path="/admin/cameras" element={<Cameras />} />
              <Route path="/audit-log" element={<AuditLogPage />} />
              <Route path="/settings" element={<SettingsPage />} />
            </Route>

            {/* Superadmin only */}
            <Route element={<RoleRoute minimumRole="superadmin" />}>
              <Route path="/admin/users" element={<Users />} />
            </Route>
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}