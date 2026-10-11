import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getExecutiveSummary,
  getAlertsReport,
  getAlertsTrend,
  getIncidentsReport,
  getIncidentsTrend,
  getLocationBreakdown,
  getAnalyticsPerformance,
  downloadReportCsv,
  type ReportFilters,
} from "@/api/reports";
import { getSites, getZones, getAnalyticsCatalog } from "@/api/platform";
import { getCameras } from "@/api/cameras";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import type { Camera } from "@/types/camera";

type CameraWithHierarchy = Camera & { site_id?: string | null };

export function Reports() {
  // Preset date ranges
  const [datePreset, setDatePreset] = useState<"7d" | "30d" | "24h" | "all">("7d");
  const [startDateInput, setStartDateInput] = useState<string>("");
  const [endDateInput, setEndDateInput] = useState<string>("");

  // Filters state
  const [siteId, setSiteId] = useState<string>("");
  const [zoneId, setZoneId] = useState<string>("");
  const [cameraId, setCameraId] = useState<string>("");
  const [analyticId, setAnalyticId] = useState<string>("");
  const [severity, setSeverity] = useState<string>("");

  // Tab for Location/Asset Breakdown
  const [breakdownTab, setBreakdownTab] = useState<"site" | "zone" | "camera" | "analytic">("site");

  // Export state
  const [isExporting, setIsExporting] = useState<boolean>(false);

  // Compute active date filters
  const computeDateRange = (): { start_date?: string; end_date?: string } => {
    if (startDateInput || endDateInput) {
      return {
        start_date: startDateInput ? new Date(startDateInput).toISOString() : undefined,
        end_date: endDateInput ? new Date(endDateInput).toISOString() : undefined,
      };
    }
    const now = new Date();
    if (datePreset === "24h") {
      const past = new Date(now.getTime() - 24 * 60 * 60 * 1000);
      return { start_date: past.toISOString(), end_date: now.toISOString() };
    }
    if (datePreset === "7d") {
      const past = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      return { start_date: past.toISOString(), end_date: now.toISOString() };
    }
    if (datePreset === "30d") {
      const past = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      return { start_date: past.toISOString(), end_date: now.toISOString() };
    }
    return {};
  };

  const activeDates = computeDateRange();

  const reportFilters: ReportFilters = {
    ...activeDates,
    site_id: siteId || undefined,
    zone_id: zoneId || undefined,
    camera_id: cameraId || undefined,
    analytic_id: analyticId || undefined,
    severity: severity || undefined,
  };

  // Queries
  const { data: sites } = useQuery({
    queryKey: ["sites"],
    queryFn: () => getSites(),
  });

  const { data: zones } = useQuery({
    queryKey: ["zones", siteId],
    queryFn: () => getZones(siteId || undefined),
  });

  const { data: cameras } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });

  const { data: catalog } = useQuery({
    queryKey: ["analyticsCatalog"],
    queryFn: getAnalyticsCatalog,
  });

  // Report Queries
  const {
    data: summary,
    isLoading: loadingSummary,
    isError: errorSummary,
  } = useQuery({
    queryKey: ["reportSummary", reportFilters],
    queryFn: () => getExecutiveSummary(reportFilters),
  });

  const { data: alertsReport, isLoading: loadingAlerts } = useQuery({
    queryKey: ["reportAlerts", reportFilters],
    queryFn: () => getAlertsReport(reportFilters),
  });

  const { data: alertsTrend } = useQuery({
    queryKey: ["reportAlertsTrend", reportFilters],
    queryFn: () => getAlertsTrend(reportFilters),
  });

  const { data: incidentsReport } = useQuery({
    queryKey: ["reportIncidents", reportFilters],
    queryFn: () => getIncidentsReport(reportFilters),
  });

  const { data: incidentsTrend } = useQuery({
    queryKey: ["reportIncidentsTrend", reportFilters],
    queryFn: () => getIncidentsTrend(reportFilters),
  });

  const { data: breakdownData } = useQuery({
    queryKey: ["reportBreakdown", reportFilters, breakdownTab],
    queryFn: () => getLocationBreakdown({ ...reportFilters, group_by: breakdownTab }),
  });

  const { data: analyticsPerf } = useQuery({
    queryKey: ["reportAnalyticsPerformance", reportFilters],
    queryFn: () => getAnalyticsPerformance(reportFilters),
  });

  const handleExportCsv = async (reportType: string) => {
    try {
      setIsExporting(true);
      await downloadReportCsv(reportType, { ...reportFilters, group_by: breakdownTab });
    } catch (err) {
      console.error("Export failed:", err);
      alert("Failed to export report CSV. Please try again.");
    } finally {
      setIsExporting(false);
    }
  };

  const handleResetFilters = () => {
    setDatePreset("7d");
    setStartDateInput("");
    setEndDateInput("");
    setSiteId("");
    setZoneId("");
    setCameraId("");
    setAnalyticId("");
    setSeverity("");
  };

  if (loadingSummary || loadingAlerts) {
    return <LoadingState />;
  }

  if (errorSummary) {
    return <ErrorState message="Failed to load enterprise reporting workspace data." />;
  }

  const cameraList = (cameras || []) as CameraWithHierarchy[];
  const filteredCameras = cameraList.filter((c) => {
    if (siteId && c.site_id !== siteId) return false;
    return true;
  });

  return (
    <main className="page" style={{ paddingBottom: "60px" }}>
      {/* Header */}
      <header className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "24px" }}>
        <div>
          <h1 className="page-title">Enterprise Intelligence Reports</h1>
          <p className="page-description">
            Operational safety analytics, alert metrics, incident lifecycle, and asset breakdown across industrial sites.
          </p>
        </div>
        <div style={{ display: "flex", gap: "10px" }}>
          <button
            className="btn btn-secondary"
            onClick={() => handleExportCsv("summary")}
            disabled={isExporting}
            style={{ fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px" }}
          >
            📊 Export Summary CSV
          </button>
          <button
            className="btn btn-primary"
            onClick={() => handleExportCsv("alerts")}
            disabled={isExporting}
            style={{ fontSize: "13px", display: "inline-flex", alignItems: "center", gap: "6px" }}
          >
            📥 Export Alerts CSV
          </button>
        </div>
      </header>

      {/* Filter Workspace Card */}
      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "20px",
          marginBottom: "28px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h3 style={{ margin: 0, fontSize: "15px", fontWeight: 600, color: "var(--text-primary)" }}>
            ⚡ Reporting Filters & Parameters
          </h3>
          <button
            onClick={handleResetFilters}
            style={{ background: "none", border: "none", color: "var(--primary)", cursor: "pointer", fontSize: "13px", fontWeight: 500 }}
          >
            Reset Filters
          </button>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "14px" }}>
          {/* Quick Presets */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              Timeframe Preset
            </label>
            <select
              value={datePreset}
              onChange={(e) => {
                setDatePreset(e.target.value as "7d" | "30d" | "24h" | "all");
                setStartDateInput("");
                setEndDateInput("");
              }}
              className="select-input"
              style={{ width: "100%" }}
            >
              <option value="24h">Last 24 Hours</option>
              <option value="7d">Last 7 Days</option>
              <option value="30d">Last 30 Days</option>
              <option value="all">All Time</option>
            </select>
          </div>

          {/* Custom Start Date */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              From Date
            </label>
            <input
              type="date"
              value={startDateInput}
              onChange={(e) => setStartDateInput(e.target.value)}
              className="text-input"
              style={{ width: "100%" }}
            />
          </div>

          {/* Custom End Date */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              To Date
            </label>
            <input
              type="date"
              value={endDateInput}
              onChange={(e) => setEndDateInput(e.target.value)}
              className="text-input"
              style={{ width: "100%" }}
            />
          </div>

          {/* Site Filter */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              Plant Site
            </label>
            <select value={siteId} onChange={(e) => { setSiteId(e.target.value); setZoneId(""); setCameraId(""); }} className="select-input" style={{ width: "100%" }}>
              <option value="">All Sites</option>
              {sites?.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>

          {/* Zone Filter */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              Zone
            </label>
            <select value={zoneId} onChange={(e) => { setZoneId(e.target.value); setCameraId(""); }} className="select-input" style={{ width: "100%" }}>
              <option value="">All Zones</option>
              {zones?.map((z) => (
                <option key={z.id} value={z.id}>{z.name}</option>
              ))}
            </select>
          </div>

          {/* Camera Filter */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              Camera
            </label>
            <select value={cameraId} onChange={(e) => setCameraId(e.target.value)} className="select-input" style={{ width: "100%" }}>
              <option value="">All Cameras</option>
              {filteredCameras.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          {/* Analytics Filter */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              Analytic Capability
            </label>
            <select value={analyticId} onChange={(e) => setAnalyticId(e.target.value)} className="select-input" style={{ width: "100%" }}>
              <option value="">All Analytics</option>
              {catalog?.map((catItem) => (
                <option key={catItem.id} value={catItem.id}>
                  {catItem.display_name}
                </option>
              ))}
            </select>
          </div>

          {/* Severity Filter */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px", fontWeight: 500 }}>
              Severity Level
            </label>
            <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="select-input" style={{ width: "100%" }}>
              <option value="">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>
      </section>

      {/* Executive Summary Stats */}
      <section className="dashboard-stats" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", marginBottom: "32px" }}>
        <div className="stat">
          <span className="stat-label">Total Alerts</span>
          <strong className="stat-value">{summary?.total_alerts ?? 0}</strong>
        </div>

        <div className="stat">
          <span className="stat-label">Critical Alerts</span>
          <strong className="stat-value stat-danger">{summary?.critical_alerts ?? 0}</strong>
        </div>

        <div className="stat">
          <span className="stat-label">Total Incidents</span>
          <strong className="stat-value">{summary?.total_incidents ?? 0}</strong>
        </div>

        <div className="stat">
          <span className="stat-label">Open Incidents</span>
          <strong className="stat-value stat-warning">{summary?.open_incidents ?? 0}</strong>
        </div>

        <div className="stat">
          <span className="stat-label">Resolved Incidents</span>
          <strong className="stat-value stat-success">{summary?.resolved_incidents ?? 0}</strong>
        </div>

        <div className="stat">
          <span className="stat-label">Active Cameras</span>
          <strong className="stat-value">{summary?.active_cameras ?? 0}</strong>
        </div>

        <div className="stat">
          <span className="stat-label">Active Analytics</span>
          <strong className="stat-value">{summary?.active_analytics ?? 0}</strong>
        </div>
      </section>

      {/* Alerts Trend & Incidents Lifecycle */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))", gap: "24px", marginBottom: "32px" }}>
        {/* Alert Trend Card */}
        <section style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <div>
              <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 650, color: "var(--text-primary)" }}>
                Alert Volume Trends
              </h3>
              <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "var(--text-secondary)" }}>
                Time-series progression of detected safety & security events.
              </p>
            </div>
          </div>

          {!alertsTrend || alertsTrend.length === 0 ? (
            <EmptyState message="No alert trend activity found for the selected reporting period." />
          ) : (
            <div style={{ marginTop: "16px", display: "flex", flexDirection: "column", gap: "10px" }}>
              {alertsTrend.slice(-10).map((t, idx) => {
                const maxVal = Math.max(...alertsTrend.map((item) => item.total), 1);
                const percent = Math.min(100, Math.round((t.total / maxVal) * 100));
                const formattedDate = new Date(t.date).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                });
                return (
                  <div key={idx} style={{ display: "flex", alignItems: "center", gap: "12px", fontSize: "12px" }}>
                    <span style={{ width: "90px", color: "var(--text-secondary)", fontWeight: 500 }}>{formattedDate}</span>
                    <div style={{ flex: 1, background: "var(--border)", height: "10px", borderRadius: "5px", overflow: "hidden", display: "flex" }}>
                      <div style={{ width: `${percent}%`, background: "var(--primary)", height: "100%" }} />
                    </div>
                    <span style={{ width: "60px", textAlign: "right", fontWeight: 700, color: "var(--text-primary)" }}>
                      {t.total} alerts
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Incident Resolution Metrics Card */}
        <section style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px" }}>
          <div style={{ marginBottom: "16px" }}>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 650, color: "var(--text-primary)" }}>
              Incident Resolution Performance
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "var(--text-secondary)" }}>
              Actual Mean, Median, Fastest and Slowest resolution durations (minutes).
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px", marginBottom: "20px" }}>
            <div style={{ background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)" }}>
              <span style={{ fontSize: "11px", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Average Resolution</span>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--primary)", marginTop: "4px" }}>
                {incidentsReport?.resolution_performance.average_resolution_time != null
                  ? `${incidentsReport.resolution_performance.average_resolution_time} min`
                  : "N/A"}
              </div>
            </div>

            <div style={{ background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)" }}>
              <span style={{ fontSize: "11px", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Median Resolution</span>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--text-primary)", marginTop: "4px" }}>
                {incidentsReport?.resolution_performance.median_resolution_time != null
                  ? `${incidentsReport.resolution_performance.median_resolution_time} min`
                  : "N/A"}
              </div>
            </div>

            <div style={{ background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)" }}>
              <span style={{ fontSize: "11px", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Fastest Resolution</span>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--success)", marginTop: "4px" }}>
                {incidentsReport?.resolution_performance.fastest_resolution_time != null
                  ? `${incidentsReport.resolution_performance.fastest_resolution_time} min`
                  : "N/A"}
              </div>
            </div>

            <div style={{ background: "var(--bg-card)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)" }}>
              <span style={{ fontSize: "11px", color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>Slowest Resolution</span>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "var(--warning)", marginTop: "4px" }}>
                {incidentsReport?.resolution_performance.slowest_resolution_time != null
                  ? `${incidentsReport.resolution_performance.slowest_resolution_time} min`
                  : "N/A"}
              </div>
            </div>
          </div>

          <h4 style={{ margin: "0 0 10px 0", fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)" }}>
            Incident Lifecycle Status Distribution
          </h4>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "8px", textAlign: "center", fontSize: "12px" }}>
            <div style={{ background: "var(--bg-card)", padding: "8px", borderRadius: "4px" }}>
              <div style={{ color: "var(--warning)", fontWeight: 700 }}>{incidentsReport?.open ?? 0}</div>
              <div style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Open</div>
            </div>

            <div style={{ background: "var(--bg-card)", padding: "8px", borderRadius: "4px" }}>
              <div style={{ color: "var(--primary)", fontWeight: 700 }}>{incidentsReport?.acknowledged ?? 0}</div>
              <div style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Acked</div>
            </div>

            <div style={{ background: "var(--bg-card)", padding: "8px", borderRadius: "4px" }}>
              <div style={{ color: "var(--info)", fontWeight: 700 }}>{incidentsReport?.investigating ?? 0}</div>
              <div style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Investigating</div>
            </div>

            <div style={{ background: "var(--bg-card)", padding: "8px", borderRadius: "4px" }}>
              <div style={{ color: "var(--success)", fontWeight: 700 }}>{incidentsReport?.resolved ?? 0}</div>
              <div style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Resolved</div>
            </div>

            <div style={{ background: "var(--bg-card)", padding: "8px", borderRadius: "4px" }}>
              <div style={{ color: "var(--text-muted)", fontWeight: 700 }}>{incidentsReport?.closed ?? 0}</div>
              <div style={{ fontSize: "10px", color: "var(--text-secondary)" }}>Closed</div>
            </div>
          </div>

          {incidentsTrend && incidentsTrend.length > 0 && (
            <div style={{ marginTop: "14px", fontSize: "11px", color: "var(--text-secondary)", textAlign: "right" }}>
              Active Trend Points: {incidentsTrend.length}
            </div>
          )}
        </section>
      </div>

      {/* Alerts by Analytics Capability */}
      <section style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "32px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "18px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 650, color: "var(--text-primary)" }}>
              Alert Distribution by Analytics Catalog
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "var(--text-secondary)" }}>
              Real event distribution across shared platform analytics capabilities (UC1 - UC4).
            </p>
          </div>
          <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)" }}>
            Total Alerts: {alertsReport?.summary.total_alerts ?? 0}
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "16px" }}>
          {alertsReport?.by_analytics.map((item) => (
            <div
              key={item.analytic_id}
              style={{
                background: "var(--bg-card)",
                border: "1px solid var(--border)",
                borderRadius: "6px",
                padding: "16px",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <span style={{ fontSize: "11px", fontWeight: 700, color: "var(--primary)", textTransform: "uppercase" }}>
                  {item.internal_code}
                </span>
                <span style={{ fontSize: "13px", fontWeight: 700, color: "var(--text-primary)" }}>
                  {item.alert_count} alerts
                </span>
              </div>

              <h4 style={{ margin: "0 0 12px 0", fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>
                {item.display_name}
              </h4>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "6px", fontSize: "11px", textAlign: "center" }}>
                <div style={{ background: "var(--danger-bg)", color: "var(--danger)", padding: "4px", borderRadius: "4px" }}>
                  <strong>{item.critical_count}</strong>
                  <div style={{ fontSize: "9px" }}>Critical</div>
                </div>

                <div style={{ background: "var(--warning-bg)", color: "var(--warning)", padding: "4px", borderRadius: "4px" }}>
                  <strong>{item.high_count}</strong>
                  <div style={{ fontSize: "9px" }}>High</div>
                </div>

                <div style={{ background: "var(--info-bg)", color: "var(--info)", padding: "4px", borderRadius: "4px" }}>
                  <strong>{item.medium_count}</strong>
                  <div style={{ fontSize: "9px" }}>Med</div>
                </div>

                <div style={{ background: "var(--surface)", color: "var(--text-secondary)", padding: "4px", borderRadius: "4px" }}>
                  <strong>{item.low_count}</strong>
                  <div style={{ fontSize: "9px" }}>Low</div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Asset & Location Breakdown Table */}
      <section style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "32px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 650, color: "var(--text-primary)" }}>
              Location & Asset Breakdown Matrix
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "var(--text-secondary)" }}>
              Aggregated metrics grouped by plant site, zone, camera, or analytics catalog item.
            </p>
          </div>

          <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
            <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: "6px", overflow: "hidden" }}>
              <button
                className={`btn ${breakdownTab === "site" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setBreakdownTab("site")}
                style={{ borderRadius: 0, padding: "6px 12px", fontSize: "12px" }}
              >
                Sites
              </button>
              <button
                className={`btn ${breakdownTab === "zone" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setBreakdownTab("zone")}
                style={{ borderRadius: 0, padding: "6px 12px", fontSize: "12px" }}
              >
                Zones
              </button>
              <button
                className={`btn ${breakdownTab === "camera" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setBreakdownTab("camera")}
                style={{ borderRadius: 0, padding: "6px 12px", fontSize: "12px" }}
              >
                Cameras
              </button>
              <button
                className={`btn ${breakdownTab === "analytic" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setBreakdownTab("analytic")}
                style={{ borderRadius: 0, padding: "6px 12px", fontSize: "12px" }}
              >
                Analytics
              </button>
            </div>

            <button
              className="btn btn-secondary"
              onClick={() => handleExportCsv("breakdown")}
              disabled={isExporting}
              style={{ fontSize: "12px", padding: "6px 12px" }}
            >
              📥 Export CSV
            </button>
          </div>
        </div>

        {!breakdownData || breakdownData.length === 0 ? (
          <EmptyState message="No breakdown data available for the current filter criteria." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ width: "100%", fontSize: "13px" }}>
              <thead>
                <tr>
                  {breakdownTab === "site" && <th>Site Name</th>}
                  {breakdownTab === "zone" && <th>Zone Name</th>}
                  {breakdownTab === "zone" && <th>Site</th>}
                  {breakdownTab === "camera" && <th>Camera Name</th>}
                  {breakdownTab === "camera" && <th>Site</th>}
                  {breakdownTab === "analytic" && <th>Analytics Capability</th>}
                  {breakdownTab === "analytic" && <th>Internal Code</th>}
                  <th>Total Alerts</th>
                  <th>Critical Alerts</th>
                  <th>Total Incidents</th>
                  <th>Open Incidents</th>
                </tr>
              </thead>
              <tbody>
                {breakdownData.map((row, idx) => (
                  <tr key={idx}>
                    {breakdownTab === "site" && <td style={{ fontWeight: 600 }}>{row.site_name || row.site_id}</td>}
                    {breakdownTab === "zone" && <td style={{ fontWeight: 600 }}>{row.zone_name || row.zone_id}</td>}
                    {breakdownTab === "zone" && <td>{row.site_name || "—"}</td>}
                    {breakdownTab === "camera" && <td style={{ fontWeight: 600 }}>{row.camera_name || row.camera_id}</td>}
                    {breakdownTab === "camera" && <td>{row.site_name || "—"}</td>}
                    {breakdownTab === "analytic" && <td style={{ fontWeight: 600 }}>{row.display_name}</td>}
                    {breakdownTab === "analytic" && <td><span className="badge badge-secondary">{row.internal_code}</span></td>}
                    <td><strong>{row.alert_count}</strong></td>
                    <td><span className={row.critical_alert_count > 0 ? "stat-danger" : ""}>{row.critical_alert_count}</span></td>
                    <td><strong>{row.incident_count}</strong></td>
                    <td><span className={row.open_incident_count > 0 ? "stat-warning" : ""}>{row.open_incident_count}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Platform Analytics Performance Comparison */}
      <section style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 650, color: "var(--text-primary)" }}>
              Platform Analytics Catalog Performance
            </h3>
            <p style={{ margin: "4px 0 0 0", fontSize: "12px", color: "var(--text-secondary)" }}>
              Side-by-side comparison of active subscriptions and detection throughput.
            </p>
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => handleExportCsv("analytics")}
            disabled={isExporting}
            style={{ fontSize: "12px", padding: "6px 12px" }}
          >
            📥 Export Analytics CSV
          </button>
        </div>

        {!analyticsPerf || analyticsPerf.length === 0 ? (
          <EmptyState message="No analytics performance data found." />
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ width: "100%", fontSize: "13px" }}>
              <thead>
                <tr>
                  <th>Analytic Name</th>
                  <th>Internal Code</th>
                  <th>Subscription State</th>
                  <th>Alert Count</th>
                  <th>Incident Count</th>
                  <th>Critical Alerts</th>
                </tr>
              </thead>
              <tbody>
                {analyticsPerf.map((perfItem) => (
                  <tr key={perfItem.analytic_id}>
                    <td style={{ fontWeight: 600 }}>{perfItem.display_name}</td>
                    <td><span className="badge badge-secondary">{perfItem.internal_code}</span></td>
                    <td>
                      <span className={`badge ${perfItem.is_active ? "badge-success" : "badge-secondary"}`}>
                        {perfItem.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td><strong>{perfItem.alert_count}</strong></td>
                    <td><strong>{perfItem.incident_count}</strong></td>
                    <td><span className={perfItem.critical_alert_count > 0 ? "stat-danger" : ""}>{perfItem.critical_alert_count}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}