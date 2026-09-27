import { apiClient } from "./client";
import type { LoginResponse } from "@/types/auth";

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  const { data } = await apiClient.post<LoginResponse>("/auth/login", null, {
    params: {
      email,
      password,
    },
  });

  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/auth/logout");
}