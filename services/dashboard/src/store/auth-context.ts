import { createContext } from "react";

import type { User, UserRole } from "@/types/auth";

export interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginAsDemo: (role?: UserRole) => void;
  logout: () => Promise<void>;
}

export const AuthContext =
  createContext<AuthContextValue | null>(null);