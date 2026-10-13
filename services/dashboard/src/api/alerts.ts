import { alertClient } from "./client";

import type { Alert } from "@/types/alert";

export interface AlertStatusCounts {
  pending: number;
  acknowledged: number;
  resolved: number;
}

const SEED_ALERTS: Alert[] = [
  {
    id: "alert-uc4-001",
    alert_id: "alert-uc4-001",
    camera_id: "00000000-0000-0000-0000-000000000402",
    source_uc: "uc4",
    alert_type: "speed_violation",
    severity: "high",
    title: "Speed Enforcement Breach Detected",
    description: "Vehicle clocked at 38 km/h in restricted 20 km/h perimeter access corridor.",
    source_event_id: "evt-001",
    frame_reference: null,
    frame_provider: null,
    status: "pending",
    metadata: {
      plate_number: "KA01MJ4921",
      speed_kmh: 38,
      speed_limit_kmh: 20,
      confidence: 0.94,
      vehicle_type: "car",
      lane: "Zone B — Perimeter Speed Lane",
    },
    created_at: new Date(Date.now() - 3 * 60 * 1000).toISOString(),
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
  },
  {
    id: "alert-uc2-001",
    alert_id: "alert-uc2-001",
    camera_id: "00000000-0000-0000-0000-000000000002",
    source_uc: "uc2",
    alert_type: "fire_smoke_detected",
    severity: "critical",
    title: "Thermal Hazard / Flame Core Alert",
    description: "Multi-stage CV engine identified uncontrolled flame signature in Boiler Core West.",
    source_event_id: "evt-002",
    frame_reference: null,
    frame_provider: null,
    status: "pending",
    metadata: {
      hazard_type: "flame",
      confidence: 0.91,
      zone_name: "Zone A — Boiler Room West",
      deliberate_suppressed: false,
    },
    created_at: new Date(Date.now() - 8 * 60 * 1000).toISOString(),
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
  },
  {
    id: "alert-uc4-002",
    alert_id: "alert-uc4-002",
    camera_id: "00000000-0000-0000-0000-000000000004",
    source_uc: "uc4",
    alert_type: "anpr_read",
    severity: "critical",
    title: "Watchlisted Vehicle Ingress Detected",
    description: "License plate DL08CA2020 matched security watchlist entry (Flagged for unauthorized cargo).",
    source_event_id: "evt-003",
    frame_reference: null,
    frame_provider: null,
    status: "acknowledged",
    metadata: {
      plate_number: "DL08CA2020",
      reason: "Unauthorized logistics transport attempt",
      ocr_confidence: 0.97,
      vehicle_type: "truck",
    },
    created_at: new Date(Date.now() - 25 * 60 * 1000).toISOString(),
    acknowledged_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    acknowledged_by: "Operator Sarah",
    resolved_at: null,
    resolved_by: null,
  },
  {
    id: "alert-uc3-001",
    alert_id: "alert-uc3-001",
    camera_id: "00000000-0000-0000-0000-000000000003",
    source_uc: "uc3",
    alert_type: "ppe_violation",
    severity: "medium",
    title: "Mandatory Safety Hardhat Missing",
    description: "Worker in active construction zone observed without approved hardhat.",
    source_event_id: "evt-004",
    frame_reference: null,
    frame_provider: null,
    status: "resolved",
    metadata: {
      missing_gear: ["hardhat"],
      zone: "Construction Sector A",
      confidence: 0.88,
    },
    created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
    acknowledged_at: new Date(Date.now() - 50 * 60 * 1000).toISOString(),
    acknowledged_by: "Supervisor Dave",
    resolved_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
    resolved_by: "Supervisor Dave",
  },
  {
    id: "alert-uc1-001",
    alert_id: "alert-uc1-001",
    camera_id: "00000000-0000-0000-0000-000000000103",
    source_uc: "uc1",
    alert_type: "restricted_zone_presence",
    severity: "high",
    title: "Unauthorized Presence in Server Vault",
    description: "Motion and person tracked in strict zero-occupancy server archive area.",
    source_event_id: "evt-005",
    frame_reference: null,
    frame_provider: null,
    status: "pending",
    metadata: {
      person_count: 1,
      zone_name: "Zone C — Server Room & Archives",
      dwell_time_seconds: 42,
    },
    created_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
    acknowledged_at: null,
    acknowledged_by: null,
    resolved_at: null,
    resolved_by: null,
  },
];

let localAlerts = [...SEED_ALERTS];

export async function getAlertStatusCounts(): Promise<AlertStatusCounts> {
  try {
    const { data } = await alertClient.get<AlertStatusCounts>(
      "/alerts/status-counts",
    );
    return data;
  } catch {
    return {
      pending: localAlerts.filter((a) => a.status === "pending").length,
      acknowledged: localAlerts.filter((a) => a.status === "acknowledged").length,
      resolved: localAlerts.filter((a) => a.status === "resolved").length,
    };
  }
}

export async function getPendingAlertsCount(): Promise<number> {
  try {
    const { data } = await alertClient.get<{ count: number }>("/alerts/count");
    return data.count;
  } catch {
    return localAlerts.filter((a) => a.status === "pending").length;
  }
}

export interface AlertFilters {
  cameraId?: string;
  ucId?: string;
  severity?: string;
  status?: string;
  limit?: number;
  offset?: number;
}

export async function getAlerts(
  filters?: AlertFilters,
): Promise<Alert[]> {
  try {
    const params: Record<string, unknown> = {};
    if (filters?.cameraId) params.camera_id = filters.cameraId;
    if (filters?.ucId) params.source_uc = filters.ucId;
    if (filters?.severity) params.severity = filters.severity;
    if (filters?.status) params.status = filters.status;
    if (filters?.limit) params.limit = filters.limit;
    if (filters?.offset) params.offset = filters.offset;

    const { data } = await alertClient.get<Alert[]>("/alerts", {
      params,
    });

    if (Array.isArray(data) && data.length > 0) {
      return data;
    }
  } catch {
    // Graceful offline fallback
  }

  // Filter local demo alerts
  return localAlerts.filter((alert) => {
    if (filters?.cameraId && alert.camera_id !== filters.cameraId) return false;
    if (filters?.ucId && alert.source_uc !== filters.ucId) return false;
    if (filters?.severity && alert.severity !== filters.severity) return false;
    if (filters?.status && alert.status !== filters.status) return false;
    return true;
  });
}

export async function acknowledgeAlert(
  alertId: string,
): Promise<Alert> {
  try {
    const { data } = await alertClient.patch<Alert>(
      `/alerts/${alertId}/acknowledge`,
    );
    return data;
  } catch {
    // Offline local mutation
    localAlerts = localAlerts.map((a) =>
      a.alert_id === alertId || a.id === alertId
        ? {
            ...a,
            status: "acknowledged",
            acknowledged_at: new Date().toISOString(),
            acknowledged_by: "Demo Operator",
          }
        : a,
    );
    return localAlerts.find((a) => a.alert_id === alertId || a.id === alertId)!;
  }
}

export async function resolveAlert(
  alertId: string,
): Promise<Alert> {
  try {
    const { data } = await alertClient.patch<Alert>(
      `/alerts/${alertId}/resolve`,
    );
    return data;
  } catch {
    // Offline local mutation
    localAlerts = localAlerts.map((a) =>
      a.alert_id === alertId || a.id === alertId
        ? {
            ...a,
            status: "resolved",
            resolved_at: new Date().toISOString(),
            resolved_by: "Demo Operator",
          }
        : a,
    );
    return localAlerts.find((a) => a.alert_id === alertId || a.id === alertId)!;
  }
}