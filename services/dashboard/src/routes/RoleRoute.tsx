import { Navigate, Outlet } from "react-router-dom";
import type { UserRole } from "@/types/auth";
import { useAuth } from "@/store/useAuth";
import { hasMinimumRole, isRoleAllowed } from "@/lib/rbac";

interface RoleRouteProps {
  minimumRole?: UserRole;
  allowedRoles?: UserRole[];
  excludedRoles?: UserRole[];
  redirectTo?: string;
}

export function RoleRoute({
  minimumRole,
  allowedRoles,
  excludedRoles,
  redirectTo = "/unauthorized",
}: RoleRouteProps) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (minimumRole && !hasMinimumRole(user, minimumRole)) {
    return <Navigate to={redirectTo} replace />;
  }

  if (!isRoleAllowed(user, allowedRoles, excludedRoles)) {
    return <Navigate to={redirectTo} replace />;
  }

  return <Outlet />;
}