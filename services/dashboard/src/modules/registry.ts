import type { ReactElement } from "react";
import type { UserRole } from "@/types/auth";
import { uc4Routes, uc4NavItems } from "./uc4";

export interface UCRoute {
  path: string;
  element: ReactElement;
  requiredRole?: UserRole;
}

export interface UCNavItem {
  label: string;
  to: string;
  requiredRole?: UserRole;
  icon?: string;
}

export interface UCModule {
  id: string;
  name: string;
  shortName: string;
  description: string;
  color: string;
  colorBg: string;
  icon: string;
  overlayBaseUrl: string;
  routes: UCRoute[];
  navItems: UCNavItem[];
  requiredRole?: UserRole;
  enabled: boolean;
}

/**
 * Global UC Module Registry
 *
 * Core rule: The shell contains ZERO hardcoded UC code.
 * UC4 is registered as enabled. UC1-UC3 are disabled metadata-only entries
 * so badges, filters, and layouts account for them automatically.
 */
export const UC_MODULES: Record<string, UCModule> = {
  uc1: {
    id: "uc1",
    name: "Worker Count & Presence",
    shortName: "Worker Count (UC1)",
    description: "Real-time occupancy monitoring and worker density tracking",
    color: "#1E3A8A", // Navy
    colorBg: "rgba(30, 58, 138, 0.15)",
    icon: "👷",
    overlayBaseUrl: import.meta.env.VITE_UC1_API_URL || "http://localhost:8021",
    routes: [],
    navItems: [],
    enabled: false,
  },
  uc2: {
    id: "uc2",
    name: "Fire, Smoke & Sparks Detection",
    shortName: "Fire & Smoke (UC2)",
    description: "Multi-stage CV pipeline with deliberate flame vs critical hazard zoning",
    color: "#DC2626", // Red
    colorBg: "rgba(220, 38, 38, 0.15)",
    icon: "🔥",
    overlayBaseUrl: import.meta.env.VITE_UC2_API_URL || "http://localhost:8022",
    routes: [],
    navItems: [],
    enabled: false,
  },
  uc3: {
    id: "uc3",
    name: "PPE Safety Compliance",
    shortName: "PPE Safety (UC3)",
    description: "Safety helmet, vest and personal protection compliance verification",
    color: "#D97706", // Amber
    colorBg: "rgba(217, 119, 6, 0.15)",
    icon: "🦺",
    overlayBaseUrl: import.meta.env.VITE_UC3_API_URL || "http://localhost:8023",
    routes: [],
    navItems: [],
    enabled: false,
  },
  uc4: {
    id: "uc4",
    name: "Traffic & Vehicle Analytics",
    shortName: "Traffic & Vehicle (UC4)",
    description: "ANPR plate recognition, speed compliance, vehicle tracking and access control",
    color: "#0D9488", // Teal
    colorBg: "rgba(13, 148, 136, 0.15)",
    icon: "🚗",
    overlayBaseUrl: import.meta.env.VITE_UC4_API_URL || "http://localhost:8024",
    routes: uc4Routes,
    navItems: uc4NavItems,
    enabled: true,
  },
};

/** Get all registered modules (enabled and disabled) */
export function getAllUCModules(): UCModule[] {
  return Object.values(UC_MODULES);
}

/** Get only enabled modules (for navigation and route mounting) */
export function getEnabledUCModules(): UCModule[] {
  return Object.values(UC_MODULES).filter((mod) => mod.enabled);
}

/** Look up a module by its identifier ('uc1', 'uc2', etc.) */
export function getUCModule(id: string): UCModule | undefined {
  return UC_MODULES[id.toLowerCase()];
}

/** Get color for a given UC ID, with fallback */
export function getUCColor(id: string): string {
  const mod = getUCModule(id);
  return mod?.color ?? "#707786";
}

/** Get badge inline style with background and border */
export function getUCBadgeStyle(id: string): {
  color: string;
  backgroundColor: string;
  borderColor: string;
} {
  const mod = getUCModule(id);
  if (!mod) {
    return {
      color: "#a2a8b5",
      backgroundColor: "rgba(162, 168, 181, 0.12)",
      borderColor: "rgba(162, 168, 181, 0.3)",
    };
  }

  return {
    color: mod.color,
    backgroundColor: mod.colorBg,
    borderColor: `${mod.color}55`,
  };
}
