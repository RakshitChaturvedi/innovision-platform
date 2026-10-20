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

import { ConfiguratorPage as UC4ConfiguratorPage } from "@/modules/uc4/pages/ConfiguratorPage";
import { TrackingPage as UC4TrackingPage } from "@/modules/uc4/pages/TrackingPage";
import { AnalyticsPage as UC4TrafficAnalyticsPage } from "@/modules/uc4/pages/AnalyticsPage";
import { PipelinePage as UC4PipelinePage } from "@/modules/uc4/pages/PipelinePage";
import { UC4OverviewPage } from "@/modules/uc4/pages/UC4OverviewPage";

import { OverlayAcceptancePage } from "@/pages/OverlayAcceptancePage";
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
        <Route path="/overlay-acceptance" element={<OverlayAcceptancePage />} />

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

            {/* UC4 Vehicle & Speed Routes */}
            <Route path="/uc4" element={<UC4OverviewPage />} />
            <Route path="/uc4/tracking" element={<UC4TrackingPage />} />
            <Route path="/uc4/analytics" element={<UC4TrafficAnalyticsPage />} />

            {/* Operator+ */}
            <Route element={<RoleRoute minimumRole="operator" />}>
              <Route path="/reports" element={<Reports />} />
              <Route path="/uc4/configurator" element={<UC4ConfiguratorPage />} />
              <Route path="/uc4/pipeline" element={<UC4PipelinePage />} />
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