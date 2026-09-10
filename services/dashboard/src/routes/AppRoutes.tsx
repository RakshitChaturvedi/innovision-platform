import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/components/layout/AppLayout";

import { Login } from "@/pages/Login";
import { Unauthorized } from "@/pages/Unauthorized";

import MasterDashboard from "@/pages/MasterDashboard";
import CameraDetail from "@/pages/CameraDetail";
import { Alerts } from "@/pages/Alerts";
import { Incidents } from "@/pages/Incidents";
import { Reports } from "@/pages/Reports";
import { Compliance } from "@/pages/Compliance";

import { Cameras } from "@/pages/admin/Cameras";
import { Users } from "@/pages/admin/Users";

import { ProtectedRoute } from "./ProtectedRoute";
import { RoleRoute } from "./RoleRoute";

export function AppRoutes() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<Login />} />
        <Route path="/unauthorized" element={<Unauthorized />} />

        {/* Authenticated */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            {/* Viewer+ */}
            <Route path="/" element={<MasterDashboard />} />
            <Route
              path="/cameras/:cameraId"
              element={<CameraDetail />}
            />

            {/* Operator+ */}
            <Route element={<RoleRoute minimumRole="operator" />}>
              <Route path="/alerts" element={<Alerts />} />
              <Route path="/incidents" element={<Incidents />} />
              <Route path="/reports" element={<Reports />} />
            </Route>

            {/* Admin+ */}
            <Route element={<RoleRoute minimumRole="admin" />}>
              <Route
                path="/admin/cameras"
                element={<Cameras />}
              />

              <Route
                path="/compliance"
                element={<Compliance />}
              />
            </Route>

            {/* Superadmin only */}
            <Route
              element={<RoleRoute minimumRole="superadmin" />}
            >
              <Route
                path="/admin/users"
                element={<Users />}
              />
            </Route>
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}