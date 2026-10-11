import { incidentClient } from "./client";

export interface LinkedAlert {
  alert_id: string;
  source_uc?: string;
  title?: string;
  severity?: string;
  camera_id?: string;
  timestamp?: string;
  linked_at?: string;
}

export interface IncidentTimelineEntry {
  timestamp: string;
  user_id?: string;
  action: string;
  note?: string;
  from_status?: string;
  to_status?: string;
}

export interface Incident {
  id: string;
  title: string;
  description?: string;
  severity: "low" | "medium" | "high" | "critical" | string;
  status: "open" | "acknowledged" | "investigating" | "resolved" | "closed" | string;
  organization_id: string;
  organization_name?: string;
  site_id?: string;
  site_name?: string;
  zone_id?: string;
  zone_name?: string;
  camera_id?: string;
  camera_name?: string;
  source_type: "alert" | "manual" | string;
  created_by?: string;
  created_by_name?: string;
  assigned_to?: string;
  assigned_to_name?: string;
  created_at: string;
  updated_at: string;
  acknowledged_at?: string;
  investigating_at?: string;
  resolved_at?: string;
  closed_at?: string;
  linked_alerts?: LinkedAlert[];
}

export interface IncidentDetail {
  incident: Incident;
  linked_alerts: LinkedAlert[];
  timeline: IncidentTimelineEntry[];
  valid_next_states: string[];
}

export interface IncidentSummary {
  open_count: number;
  investigating_count: number;
  critical_count: number;
  resolved_today_count: number;
}

export interface IncidentFilters {
  status?: string;
  severity?: string;
  organization_id?: string;
  site_id?: string;
  zone_id?: string;
  camera_id?: string;
  assigned_to?: string;
  source_type?: string;
  limit?: number;
  offset?: number;
}

export interface CreateIncidentInput {
  title: string;
  description?: string;
  severity?: string;
  organization_id?: string;
  site_id?: string;
  zone_id?: string;
  camera_id?: string;
  source_type?: string;
  assigned_to?: string;
  alert_ids?: string[];
}

export interface UpdateIncidentInput {
  title?: string;
  description?: string;
  severity?: string;
  site_id?: string;
  zone_id?: string;
  camera_id?: string;
  assigned_to?: string;
}

export async function getIncidents(filters?: IncidentFilters): Promise<Incident[]> {
  const { data } = await incidentClient.get<Incident[]>("/incidents", { params: filters });
  return data;
}

export async function getIncidentSummary(organizationId?: string): Promise<IncidentSummary> {
  const { data } = await incidentClient.get<IncidentSummary>("/incidents/summary", {
    params: organizationId ? { organization_id: organizationId } : undefined,
  });
  return data;
}

export async function getIncident(incidentId: string): Promise<IncidentDetail> {
  const { data } = await incidentClient.get<IncidentDetail>(`/incidents/${incidentId}`);
  return data;
}

export async function createIncident(input: CreateIncidentInput): Promise<IncidentDetail> {
  const { data } = await incidentClient.post<IncidentDetail>("/incidents", input);
  return data;
}

export async function updateIncident(incidentId: string, input: UpdateIncidentInput): Promise<IncidentDetail> {
  const { data } = await incidentClient.put<IncidentDetail>(`/incidents/${incidentId}`, input);
  return data;
}

export async function updateIncidentStatus(incidentId: string, status: string): Promise<IncidentDetail> {
  const { data } = await incidentClient.put<IncidentDetail>(`/incidents/${incidentId}/status`, { status });
  return data;
}

export async function assignIncident(incidentId: string, assignedTo: string | null): Promise<IncidentDetail> {
  const { data } = await incidentClient.put<IncidentDetail>(`/incidents/${incidentId}/assign`, { assigned_to: assignedTo });
  return data;
}

export async function linkAlertToIncident(incidentId: string, alertId: string): Promise<IncidentDetail> {
  const { data } = await incidentClient.post<IncidentDetail>(`/incidents/${incidentId}/alerts/${alertId}`);
  return data;
}

export async function unlinkAlertFromIncident(incidentId: string, alertId: string): Promise<IncidentDetail> {
  const { data } = await incidentClient.delete<IncidentDetail>(`/incidents/${incidentId}/alerts/${alertId}`);
  return data;
}
