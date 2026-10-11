import { settingsClient } from "./client";

export interface OrganizationSettings {
  id: string;
  name: string;
  code: string;
  tier: string;
  timezone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OrganizationUpdateData {
  name?: string;
  timezone?: string;
}

export interface SecuritySettings {
  auth_provider: string;
  session_duration: string;
  supported_roles: string[];
  user_management_url: string;
}

export interface PlatformSettings {
  platform_name: string;
  version: string;
  environment: string;
  status: string;
  services_count: number;
}

export interface SubscriptionSummaryItem {
  analytic_id: string;
  name: string;
  code: string;
  status: string;
  description?: string;
}

export interface SettingsResponse {
  organization: OrganizationSettings | null;
  security: SecuritySettings;
  platform: PlatformSettings;
  subscriptions: SubscriptionSummaryItem[];
}

export async function fetchSettings(organizationId?: string): Promise<SettingsResponse> {
  const params = organizationId ? { organization_id: organizationId } : undefined;
  const response = await settingsClient.get<SettingsResponse>("/api/v1/settings", { params });
  return response.data;
}

export async function updateOrganizationSettings(
  data: OrganizationUpdateData,
  organizationId?: string
): Promise<OrganizationSettings> {
  const params = organizationId ? { organization_id: organizationId } : undefined;
  const response = await settingsClient.put<OrganizationSettings>("/api/v1/settings/organization", data, { params });
  return response.data;
}
