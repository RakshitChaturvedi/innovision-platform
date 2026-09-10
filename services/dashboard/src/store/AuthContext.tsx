import {
  useState,
  type ReactNode,
} from "react";
import { AuthContext } from "./auth-context";
import type { User } from "@/types/auth";
import { login as loginApi, logout as logoutApi } from "@/api/auth";
import { decodeAccessToken } from "@/lib/jwt";

export interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}


const ACCESS_TOKEN_KEY = "innovision_access_token";

export function AuthProvider({
  children,
}: {
  children: ReactNode;
}) {
  const [accessToken, setAccessToken] = useState<string | null>(() =>
    localStorage.getItem(ACCESS_TOKEN_KEY),
  );

  const [user, setUser] = useState<User | null>(() => {
    const token = localStorage.getItem(ACCESS_TOKEN_KEY);

    if (!token) return null;

    try {
      return decodeAccessToken(token);
    } catch {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      return null;
    }
  });

  async function login(email: string, password: string) {
    const response = await loginApi(email, password);

    localStorage.setItem(
      ACCESS_TOKEN_KEY,
      response.access_token,
    );

    setAccessToken(response.access_token);
    setUser(decodeAccessToken(response.access_token));
  }

  async function logout() {
    try {
      if (accessToken) {
        await logoutApi();
      }
    } finally {
      localStorage.removeItem(ACCESS_TOKEN_KEY);
      setAccessToken(null);
      setUser(null);
    }
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        accessToken,
        isAuthenticated:
          user !== null && accessToken !== null,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}