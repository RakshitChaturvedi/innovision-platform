import { alertClient } from "./client";

import type { Alert } from "@/types/alert";

export interface AlertStatusCounts {
  pending: number;
  acknowledged: number;
  resolved: number;
}

export async function getAlertStatusCounts(): Promise<AlertStatusCounts> {
  const { data } = await alertClient.get<AlertStatusCounts>(
    "/alerts/status-counts",
  );

  return data;
}

export interface AlertFilters {
  cameraId?: string;
  ucId?: string;
  severity?: string;
  status?: string;
}

export async function getAlerts(
  filters?: AlertFilters,
): Promise<Alert[]> {
  console.log("[API] GET /alerts", filters);

  const { data } = await alertClient.get<Alert[]>("/alerts", {
    params: filters,
  });

  console.log("[API] /alerts response:", data);

  return data;
}

export async function acknowledgeAlert(
  alertId: string,
): Promise<Alert> {
  const { data } = await alertClient.patch<Alert>(
    `/alerts/${alertId}/acknowledge`,
  );

  return data;
}

export async function resolveAlert(
  alertId: string,
): Promise<Alert> {
  const { data } = await alertClient.patch<Alert>(
    `/alerts/${alertId}/resolve`,
  );

  return data;
}