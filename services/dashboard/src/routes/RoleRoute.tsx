import { Navigate, Outlet } from "react-router-dom";
import type { UserRole } from "@/types/auth";
import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";

interface RoleRouteProps {
  minimumRole: UserRole;
}

export function RoleRoute({ minimumRole }: RoleRouteProps) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!hasMinimumRole(user, minimumRole)) {
    return <Navigate to="/unauthorized" replace />;
  }

  return <Outlet />;
}