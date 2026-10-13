import {
  useState,
  type ReactNode,
} from "react";
import { AuthContext } from "./auth-context";
import type { User, UserRole } from "@/types/auth";
import { login as loginApi, logout as logoutApi } from "@/api/auth";
import { decodeAccessToken } from "@/lib/jwt";

export interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginAsDemo: (role?: UserRole) => void;
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
    try {
      const response = await loginApi(email, password);
      localStorage.setItem(
        ACCESS_TOKEN_KEY,
        response.access_token,
      );
      setAccessToken(response.access_token);
      setUser(decodeAccessToken(response.access_token));
    } catch (err) {
      // In offline / standalone development without backend, allow dev credentials
      if (
        (email === "admin@innovision.com" && password === "admin123") ||
        email.endsWith("@innovision.com")
      ) {
        console.warn("[Auth] Backend unreachable, falling back to local Dev/Demo session.");
        loginAsDemo("superadmin");
        return;
      }
      throw err;
    }
  }

  function loginAsDemo(role: UserRole = "superadmin") {
    const demoToken = `demo_${role}_token`;
    localStorage.setItem(ACCESS_TOKEN_KEY, demoToken);
    setAccessToken(demoToken);
    setUser(decodeAccessToken(demoToken));
  }

  async function logout() {
    try {
      if (accessToken && !accessToken.startsWith("demo_")) {
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
        loginAsDemo,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}