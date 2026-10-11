export type UserRole =
  | "viewer"
  | "operator"
  | "admin"
  | "org_admin"
  | "superadmin";

export interface User {
  id: string;
  name?: string;
  email?: string;
  role: UserRole;
  organization_id?: string | null;
  organization_name?: string | null;
  organization_code?: string | null;
  is_active?: boolean;
  camera_ids?: string[];
  created_at?: string | null;
}

export interface UserRecord {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  organization_id?: string | null;
  organization_name?: string | null;
  organization_code?: string | null;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user?: User;
}

export interface AuthState {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
}