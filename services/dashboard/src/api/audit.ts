import { auditClient } from "./client";

export interface AuditLogItem {
  id: string;
  timestamp: string;
  service: string;
  action: string;
  resource_type: string;
  resource_id: string;
  actor_user_id?: string;
  user_name?: string;
  user_email?: string;
  actor_role?: string;
  source_uc?: string;
  organization_id?: string;
  description?: string;
  metadata: Record<string, unknown>;
}

export interface AuditLogResponse {
  items: AuditLogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuditQueryParams {
  start_date?: string;
  end_date?: string;
  organization_id?: string;
  actor_user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  search?: string;
  page?: number;
  page_size?: number;
}

export async function fetchAuditLogs(params: AuditQueryParams): Promise<AuditLogResponse> {
  const response = await auditClient.get<AuditLogResponse>("/api/v1/audit", { params });
  return response.data;
}

export async function fetchAuditLogById(id: string): Promise<AuditLogItem> {
  const response = await auditClient.get<AuditLogItem>(`/api/v1/audit/${id}`);
  return response.data;
}
