import { cameraClient } from "./client";
import type {
  AnalyticCatalogItem,
  Organization,
  OrganizationSubscription,
  Site,
  Zone,
  ZoneAnalyticsPolicyItem,
  ZonePPERulesConfig,
  CameraAnalyticsOverride,
  CameraEffectiveAnalytic,
  CameraExtendedHierarchy
} from "@/types/platform";

// --- Analytics Catalog & Subscriptions ---
export async function getAnalyticsCatalog(): Promise<AnalyticCatalogItem[]> {
  const { data } = await cameraClient.get<AnalyticCatalogItem[]>("/analytics/catalog");
  return data;
}

export async function getOrganizationSubscriptions(orgId: string): Promise<OrganizationSubscription[]> {
  const { data } = await cameraClient.get<OrganizationSubscription[]>(`/organizations/${orgId}/subscriptions`);
  return data;
}

export async function createOrganizationSubscription(
  orgId: string,
  payload: { analytic_id: string; is_enabled?: boolean; max_cameras_allowed?: number }
): Promise<OrganizationSubscription> {
  const { data } = await cameraClient.post<OrganizationSubscription>(`/organizations/${orgId}/subscriptions`, payload);
  return data;
}

export async function updateOrganizationSubscription(
  orgId: string,
  analyticId: string,
  payload: { is_enabled?: boolean; max_cameras_allowed?: number }
): Promise<OrganizationSubscription> {
  const { data } = await cameraClient.put<OrganizationSubscription>(`/organizations/${orgId}/subscriptions/${analyticId}`, payload);
  return data;
}

// --- Organizations, Sites, Zones ---
export async function getOrganizations(): Promise<Organization[]> {
  const { data } = await cameraClient.get<Organization[]>("/cameras/organizations");
  return data;
}

export async function createOrganization(payload: { name: string; code: string; tier?: string }): Promise<Organization> {
  const { data } = await cameraClient.post<Organization>("/cameras/organizations", payload);
  return data;
}

export async function getSites(orgId?: string): Promise<Site[]> {
  const params = orgId ? { organization_id: orgId } : {};
  const { data } = await cameraClient.get<Site[]>("/cameras/sites", { params });
  return data;
}

export async function createSite(payload: { organization_id: string; name: string; code: string; address?: string }): Promise<Site> {
  const { data } = await cameraClient.post<Site>("/cameras/sites", payload);
  return data;
}

export async function getZones(siteId?: string): Promise<Zone[]> {
  const params = siteId ? { site_id: siteId } : {};
  const { data } = await cameraClient.get<Zone[]>("/cameras/zones", { params });
  return data;
}

export async function createZone(payload: { site_id?: string; name: string; zone_type?: string; risk_level?: string }): Promise<Zone> {
  const { data } = await cameraClient.post<Zone>("/cameras/zones", payload);
  return data;
}

// --- Zone Analytics Policies & PPE Rules ---
export async function getZoneAnalyticsPolicies(zoneId: string): Promise<ZoneAnalyticsPolicyItem[]> {
  const { data } = await cameraClient.get<ZoneAnalyticsPolicyItem[]>(`/zones/${zoneId}/analytics`);
  return data;
}

export async function updateZoneAnalyticsPolicy(zoneId: string, analyticId: string, isEnabled: boolean): Promise<ZoneAnalyticsPolicyItem> {
  const { data } = await cameraClient.put<ZoneAnalyticsPolicyItem>(`/zones/${zoneId}/analytics/${analyticId}`, { is_enabled: isEnabled });
  return data;
}

export async function getZonePPERules(zoneId: string): Promise<ZonePPERulesConfig> {
  const { data } = await cameraClient.get<ZonePPERulesConfig>(`/zones/${zoneId}/ppe-rules`);
  return data;
}

export async function updateZonePPERules(zoneId: string, rules: ZonePPERulesConfig["ppe_rules"], minConfidence: number = 0.50): Promise<ZonePPERulesConfig> {
  const { data } = await cameraClient.put<ZonePPERulesConfig>(`/zones/${zoneId}/ppe-rules`, { ppe_rules: rules, min_confidence: minConfidence });
  return data;
}

// --- Camera Overrides & Effective Analytics ---
export async function getCameraEffectiveAnalytics(cameraId: string): Promise<CameraEffectiveAnalytic[]> {
  const { data } = await cameraClient.get<CameraEffectiveAnalytic[]>(`/cameras/${cameraId}/analytics/effective`);
  return data;
}

export async function getCameraAnalyticsOverrides(cameraId: string): Promise<CameraAnalyticsOverride[]> {
  const { data } = await cameraClient.get<CameraAnalyticsOverride[]>(`/cameras/${cameraId}/analytics/overrides`);
  return data;
}

export async function setCameraAnalyticsOverride(cameraId: string, analyticId: string, isEnabled: boolean): Promise<CameraAnalyticsOverride> {
  const { data } = await cameraClient.put<CameraAnalyticsOverride>(`/cameras/${cameraId}/analytics/${analyticId}/override`, { is_enabled: isEnabled });
  return data;
}

export async function deleteCameraAnalyticsOverride(cameraId: string, analyticId: string): Promise<void> {
  await cameraClient.delete(`/cameras/${cameraId}/analytics/${analyticId}/override`);
}

export async function assignCameraZone(cameraId: string, payload: { site_id?: string | null; zone_id?: string | null; lifecycle_state?: string | null }): Promise<CameraExtendedHierarchy> {
  const { data } = await cameraClient.put<CameraExtendedHierarchy>(`/cameras/${cameraId}/assign-zone`, payload);
  return data;
}

export async function getCameraHierarchy(cameraId: string): Promise<CameraExtendedHierarchy> {
  const { data } = await cameraClient.get<CameraExtendedHierarchy>(`/cameras/${cameraId}/hierarchy`);
  return data;
}
