import type { User, UserRole } from "@/types/auth";

export function decodeAccessToken(token: string): User {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) {
      throw new Error("Invalid JWT token format");
    }
    const payload = JSON.parse(atob(parts[1]));
    return {
      id: payload.sub || payload.user_id || payload.id || "anonymous",
      role: (payload.role as UserRole) || "viewer",
      camera_ids: Array.isArray(payload.camera_ids) ? payload.camera_ids : [],
    };
  } catch (e) {
    throw new Error(`Failed to decode JWT token: ${e}`);
  }
}
