import type { User, UserRole } from "@/types/auth";

const ROLE_HIERARCHY: Record<UserRole, number> = {
  viewer: 1,
  operator: 2,
  admin: 3,
  org_admin: 3,
  superadmin: 4,
};

export function hasMinimumRole(user: User | null, minimumRole: UserRole): boolean {
  if (!user || !user.role) return false;
  const userLevel = ROLE_HIERARCHY[user.role] ?? 0;
  const requiredLevel = ROLE_HIERARCHY[minimumRole] ?? 0;
  return userLevel >= requiredLevel;
}

export function isRoleAllowed(
  user: User | null,
  allowedRoles?: UserRole[],
  excludedRoles?: UserRole[]
): boolean {
  if (!user || !user.role) return false;
  if (excludedRoles && excludedRoles.includes(user.role)) return false;
  if (allowedRoles && allowedRoles.length > 0) return allowedRoles.includes(user.role);
  return true;
}
