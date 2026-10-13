import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";

import { Login } from "@/pages/Login";
import { Unauthorized } from "@/pages/Unauthorized";

import MasterDashboard from "@/pages/MasterDashboard";
import CameraDetail from "@/pages/CameraDetail";
import Alerts from "@/pages/Alerts";
import { Incidents } from "@/pages/Incidents";
import { Reports } from "@/pages/Reports";
import { Compliance } from "@/pages/Compliance";

import { Cameras } from "@/pages/admin/Cameras";
import { Users } from "@/pages/admin/Users";

import { ProtectedRoute } from "./ProtectedRoute";
import { RoleRoute } from "./RoleRoute";
import { getEnabledUCModules } from "@/modules/registry";

export function AppRoutes() {
  const enabledModules = getEnabledUCModules();

  return (
    <BrowserRouter>
      <Routes>
        {/* Public Routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/unauthorized" element={<Unauthorized />} />

        {/* Authenticated Application Shell */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            {/* Viewer+ Core Pages */}
            <Route path="/" element={<MasterDashboard />} />
            <Route path="/cameras/:cameraId" element={<CameraDetail />} />

            {/* Operator+ Core Pages */}
            <Route element={<RoleRoute minimumRole="operator" />}>
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/incidents" element={<Incidents />} />
              <Route path="/reports" element={<Reports />} />
            </Route>

            {/* Admin+ Core Pages */}
            <Route element={<RoleRoute minimumRole="admin" />}>
              <Route path="/admin/cameras" element={<Cameras />} />
              <Route path="/compliance" element={<Compliance />} />
            </Route>

            {/* Superadmin Core Pages */}
            <Route element={<RoleRoute minimumRole="superadmin" />}>
              <Route path="/admin/users" element={<Users />} />
            </Route>

            {/* Dynamically Registered UC Module Routes (Zero hardcoded UC references) */}
            {enabledModules.map((module) =>
              module.routes.map((route) => {
                if (route.requiredRole) {
                  return (
                    <Route
                      key={`${module.id}-${route.path}-auth`}
                      element={<RoleRoute minimumRole={route.requiredRole} />}
                    >
                      <Route path={route.path} element={route.element} />
                    </Route>
                  );
                }

                return (
                  <Route
                    key={`${module.id}-${route.path}`}
                    path={route.path}
                    element={route.element}
                  />
                );
              }),
            )}
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}