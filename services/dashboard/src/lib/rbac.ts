import type { User, UserRole } from "@/types/auth";

const ROLE_HIERARCHY: Record<UserRole, number> = {
  viewer: 1,
  operator: 2,
  admin: 3,
  superadmin: 4,
};

export function hasMinimumRole(user: User | null, minimumRole: UserRole): boolean {
  if (!user || !user.role) return false;
  const userLevel = ROLE_HIERARCHY[user.role] ?? 0;
  const requiredLevel = ROLE_HIERARCHY[minimumRole] ?? 0;
  return userLevel >= requiredLevel;
}
