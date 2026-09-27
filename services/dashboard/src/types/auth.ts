export type UserRole =
  | "viewer"
  | "operator"
  | "admin"
  | "superadmin";

export interface User {
  id: string;
  role: UserRole;
  camera_ids: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
}