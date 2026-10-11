import { authClient } from "./client";
import type { UserRecord } from "@/types/auth";

export async function getUsers(organizationId?: string): Promise<UserRecord[]> {
  const params = organizationId ? { organization_id: organizationId } : {};
  const { data } = await authClient.get<UserRecord[]>("/auth/users", { params });
  return data;
}

export async function createUser(payload: {
  name: string;
  email: string;
  password: string;
  role: string;
  organization_id?: string | null;
}): Promise<UserRecord> {
  const { data } = await authClient.post<UserRecord>("/auth/users", payload);
  return data;
}

export async function updateUser(
  userId: string,
  payload: { name?: string; role?: string; organization_id?: string | null }
): Promise<{ status: string; id: string }> {
  const { data } = await authClient.put<{ status: string; id: string }>(`/auth/users/${userId}`, payload);
  return data;
}

export async function updateUserStatus(
  userId: string,
  isActive: boolean
): Promise<{ status: string; id: string; is_active: boolean }> {
  const { data } = await authClient.put<{ status: string; id: string; is_active: boolean }>(`/auth/users/${userId}/status`, {
    is_active: isActive,
  });
  return data;
}
