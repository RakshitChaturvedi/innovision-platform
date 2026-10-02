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
  camera_id?: string;
  source_uc?: string;
  severity?: string;
  status?: string;
}

export async function getAlerts(
  filters?: AlertFilters,
  limit = 50,
  offset = 0,
): Promise<Alert[]> {
  const { data } = await alertClient.get<Alert[]>("/alerts", {
    params: { ...filters, limit, offset },
  });

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

export interface SnapshotResponse {
  url: string;
  expires_in: number;
}

export async function getAlertSnapshot(
  alertId: string,
): Promise<SnapshotResponse> {
  const { data } = await alertClient.get<SnapshotResponse>(
    `/alerts/${alertId}/snapshot`,
  );
  return data;
}