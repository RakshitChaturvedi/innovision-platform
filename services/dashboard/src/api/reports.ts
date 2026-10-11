import { reportsClient } from "./client";

export interface ReportFilters {
  start_date?: string;
  end_date?: string;
  organization_id?: string;
  site_id?: string;
  zone_id?: string;
  camera_id?: string;
  analytic_id?: string;
  severity?: string;
  status?: string;
  assigned_to?: string;
  group_by?: "site" | "zone" | "camera" | "analytic";
  bucket?: "hourly" | "daily" | "weekly";
}

export interface ExecutiveSummaryData {
  total_alerts: number;
  critical_alerts: number;
  high_alerts: number;
  medium_alerts: number;
  low_alerts: number;

  total_incidents: number;
  open_incidents: number;
  investigating_incidents: number;
  resolved_incidents: number;
  closed_incidents: number;

  active_cameras: number;
  active_analytics: number;

  resolved_today: number;
}

export interface AlertAnalyticsItem {
  analytic_id: string;
  internal_code: string;
  display_name: string;
  alert_count: number;
  critical_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
}

export interface AlertsReportData {
  summary: {
    total_alerts: number;
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  by_analytics: AlertAnalyticsItem[];
}

export interface AlertTrendData {
  date: string;
  total: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
}

export interface IncidentResolutionMetrics {
  average_resolution_time: number | null;
  median_resolution_time: number | null;
  fastest_resolution_time: number | null;
  slowest_resolution_time: number | null;
}

export interface IncidentsReportData {
  total_incidents: number;
  open: number;
  acknowledged: number;
  investigating: number;
  resolved: number;
  closed: number;
  critical: number;
  high: number;
  medium: number;
  low: number;
  resolution_performance: IncidentResolutionMetrics;
}

export interface IncidentTrendData {
  date: string;
  created: number;
  resolved: number;
  open: number;
  critical: number;
}

export interface BreakdownItemData {
  site_id?: string;
  site_name?: string;
  zone_id?: string;
  zone_name?: string;
  camera_id?: string;
  camera_name?: string;
  analytic_id?: string;
  internal_code?: string;
  display_name?: string;
  alert_count: number;
  incident_count: number;
  critical_alert_count: number;
  open_incident_count: number;
}

export interface AnalyticsPerformanceData {
  analytic_id: string;
  internal_code: string;
  display_name: string;
  is_active: boolean;
  alert_count: number;
  incident_count: number;
  critical_alert_count: number;
}

export async function getExecutiveSummary(filters: ReportFilters = {}): Promise<ExecutiveSummaryData> {
  const { data } = await reportsClient.get<ExecutiveSummaryData>("/reports/summary", { params: filters });
  return data;
}

export async function getAlertsReport(filters: ReportFilters = {}): Promise<AlertsReportData> {
  const { data } = await reportsClient.get<AlertsReportData>("/reports/alerts", { params: filters });
  return data;
}

export async function getAlertsTrend(filters: ReportFilters = {}): Promise<AlertTrendData[]> {
  const { data } = await reportsClient.get<AlertTrendData[]>("/reports/alerts/trend", { params: filters });
  return data;
}

export async function getIncidentsReport(filters: ReportFilters = {}): Promise<IncidentsReportData> {
  const { data } = await reportsClient.get<IncidentsReportData>("/reports/incidents", { params: filters });
  return data;
}

export async function getIncidentsTrend(filters: ReportFilters = {}): Promise<IncidentTrendData[]> {
  const { data } = await reportsClient.get<IncidentTrendData[]>("/reports/incidents/trend", { params: filters });
  return data;
}

export async function getLocationBreakdown(filters: ReportFilters = {}): Promise<BreakdownItemData[]> {
  const { data } = await reportsClient.get<BreakdownItemData[]>("/reports/breakdown", { params: filters });
  return data;
}

export async function getAnalyticsPerformance(filters: ReportFilters = {}): Promise<AnalyticsPerformanceData[]> {
  const { data } = await reportsClient.get<AnalyticsPerformanceData[]>("/reports/analytics", { params: filters });
  return data;
}

export async function downloadReportCsv(reportType: string, filters: ReportFilters = {}): Promise<void> {
  const response = await reportsClient.get("/reports/export", {
    params: { report_type: reportType, ...filters },
    responseType: "blob",
  });

  const blob = new Blob([response.data], { type: "text/csv" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", `report_${reportType}.csv`);
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
