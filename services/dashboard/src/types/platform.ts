export interface Organization {
  id: string;
  name: string;
  code: string;
  tier: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Site {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  address?: string | null;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface Zone {
  id: string;
  site_id?: string | null;
  organization_id?: string | null;
  name: string;
  slug?: string | null;
  description?: string | null;
  zone_type: string;
  risk_level: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AnalyticCatalogItem {
  id: string;
  code: string;
  internal_code: string;
  display_name: string;
  description?: string | null;
  category: string;
  icon_key?: string | null;
  is_active: boolean;
  created_at: string;
}

export interface OrganizationSubscription {
  id: string;
  organization_id: string;
  analytic_id: string;
  analytic_code?: string | null;
  analytic_internal_code?: string | null;
  analytic_display_name?: string | null;
  is_enabled: boolean;
  max_cameras_allowed: number;
  valid_until?: string | null;
  status: "enabled" | "disabled" | "expired";
  created_at: string;
}

export interface ZoneAnalyticsPolicyItem {
  analytic_id: string;
  internal_code: string;
  code: string;
  display_name: string;
  category: string;
  is_enabled: boolean;
}

export interface ZonePPERuleItem {
  ppe_type: string;
  required: boolean;
  severity: string;
  grace_seconds: number;
}

export interface ZonePPERulesConfig {
  zone_id?: string | null;
  ppe_rules: ZonePPERuleItem[];
  min_confidence: number;
}

export interface CameraAnalyticsOverride {
  id: string;
  camera_id: string;
  analytic_id: string;
  analytic_code?: string | null;
  analytic_internal_code?: string | null;
  analytic_display_name?: string | null;
  is_enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface CameraEffectiveAnalytic {
  analytic_id: string;
  internal_code: string;
  code: string;
  display_name: string;
  is_active: boolean;
  source: "zone" | "camera_override" | "none";
  effective_config?: Record<string, unknown> | null;
  zone_policy_enabled: boolean;
  override_enabled?: boolean | null;
  subscription_active: boolean;
}

export interface CameraExtendedHierarchy {
  id: string;
  name: string;
  location?: string | null;
  rtsp_url: string | null;
  status: "online" | "offline" | "reconnecting" | "disabled";
  use_cases: string[];
  fps: number;
  organization_id?: string | null;
  site_id?: string | null;
  zone_id?: string | null;
  lifecycle_state: string;
  source_type: string;
  source_url?: string | null;
  is_simulation: boolean;
  organization?: { id: string; name: string; code: string } | null;
  site?: { id: string; name: string; code: string } | null;
  zone?: { id: string; name: string; zone_type: string; risk_level: string } | null;
}
