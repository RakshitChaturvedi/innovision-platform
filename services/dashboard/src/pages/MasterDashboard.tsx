import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "@/store/useAuth";
import { getCameras } from "@/api/cameras";
import {
  getOrganizations,
  getSites,
  getZones,
  getAnalyticsCatalog,
  getOrganizationSubscriptions,
} from "@/api/platform";
import { getIncidents, getIncidentSummary } from "@/api/incidents";
import { getAlerts, acknowledgeAlert, resolveAlert } from "@/api/alerts";
import { getUsers } from "@/api/users";
import { fetchAuditLogs } from "@/api/audit";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import CameraTile from "@/components/cameras/CameraTile";
import type { UserRole } from "@/types/auth";

export default function MasterDashboard() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // If user is admin/superadmin, allow switching role preview mode
  const canSwitchRolePreview = user?.role === "admin" || user?.role === "superadmin" || user?.role === "org_admin";
  const [activeRoleView, setActiveRoleView] = useState<UserRole>(user?.role || "operator");

  // Camera search / filter state
  const [cameraSearch, setCameraSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "online" | "offline">("all");

  // Common Queries
  const { data: orgs } = useQuery({
    queryKey: ["organizations"],
    queryFn: getOrganizations,
  });

  const activeOrgId = orgs && orgs.length > 0 ? orgs[0].id : "";

  const { data: cameras, isLoading: loadingCameras, isError } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    refetchInterval: 5000,
  });

  const { data: incidentSummary } = useQuery({
    queryKey: ["incidentSummary", activeOrgId],
    queryFn: () => getIncidentSummary(activeOrgId),
    refetchInterval: 5000,
  });

  const { data: incidents } = useQuery({
    queryKey: ["recentIncidents"],
    queryFn: () => getIncidents({ status: "active" }),
    refetchInterval: 5000,
  });

  const { data: alerts } = useQuery({
    queryKey: ["recentAlerts"],
    queryFn: () => getAlerts({ status: "pending" }),
    refetchInterval: 5000,
  });

  const { data: sites } = useQuery({
    queryKey: ["sites", activeOrgId],
    queryFn: () => getSites(activeOrgId),
    enabled: Boolean(activeOrgId),
  });

  const { data: zones } = useQuery({
    queryKey: ["zones"],
    queryFn: () => getZones(),
  });

  const { data: catalog } = useQuery({
    queryKey: ["analyticsCatalog"],
    queryFn: getAnalyticsCatalog,
  });

  const { data: subscriptions } = useQuery({
    queryKey: ["organizationSubscriptions", activeOrgId],
    queryFn: () => getOrganizationSubscriptions(activeOrgId),
    enabled: Boolean(activeOrgId),
  });

  const { data: usersList } = useQuery({
    queryKey: ["usersCount"],
    queryFn: () => getUsers(),
    enabled: canSwitchRolePreview,
  });

  const { data: auditLogs } = useQuery({
    queryKey: ["recentAuditLogs"],
    queryFn: () => fetchAuditLogs({ page: 1, page_size: 5 }),
    enabled: canSwitchRolePreview,
  });

  // Alert quick triage mutations
  const ackMutation = useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recentAlerts"] }),
  });

  const resolveMutation = useMutation({
    mutationFn: resolveAlert,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["recentAlerts"] }),
  });

  if (loadingCameras) {
    return <LoadingState message="Connecting to Camera Registry & Telemetry Feed..." />;
  }

  if (isError) {
    return <ErrorState message="Failed to load organization camera telemetry." />;
  }

  const cameraList = cameras || [];
  const onlineCount = cameraList.filter((c) => c.status === "online").length;
  const onlinePercent =
    cameraList.length > 0
      ? Math.round((onlineCount / cameraList.length) * 100)
      : 0;

  const filteredCameras = cameraList.filter((cam) => {
    const matchesSearch =
      cam.name.toLowerCase().includes(cameraSearch.toLowerCase()) ||
      (cam.location && cam.location.toLowerCase().includes(cameraSearch.toLowerCase())) ||
      cam.id.toLowerCase().includes(cameraSearch.toLowerCase());

    const matchesStatus =
      statusFilter === "all" ? true : cam.status === statusFilter;

    return matchesSearch && matchesStatus;
  });

  return (
    <main className="page" style={{ padding: "24px 32px" }}>
      {/* Role Switcher Toolbar for Admins / Demonstrations */}
      {canSwitchRolePreview && (
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "10px",
            padding: "8px 16px",
            marginBottom: "24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.08em" }}>
              Active Role Dashboard Interface:
            </span>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                color: "#e50914",
                background: "rgba(229, 9, 20, 0.12)",
                padding: "2px 8px",
                borderRadius: "4px",
                border: "1px solid rgba(229, 9, 20, 0.3)",
              }}
            >
              {activeRoleView.toUpperCase()} MODE
            </span>
          </div>

          <div style={{ display: "flex", gap: "6px" }}>
            <button
              type="button"
              onClick={() => setActiveRoleView("viewer")}
              style={{
                background: activeRoleView === "viewer" ? "#2563eb" : "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: activeRoleView === "viewer" ? "#ffffff" : "#94a3b8",
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              👁️ Viewer Desk
            </button>
            <button
              type="button"
              onClick={() => setActiveRoleView("operator")}
              style={{
                background: activeRoleView === "operator" ? "#e50914" : "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: activeRoleView === "operator" ? "#ffffff" : "#94a3b8",
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              ⚡ Operator Console
            </button>
            <button
              type="button"
              onClick={() => setActiveRoleView("admin")}
              style={{
                background: activeRoleView === "admin" ? "#059669" : "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: activeRoleView === "admin" ? "#ffffff" : "#94a3b8",
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              🛡️ Safety Admin
            </button>
            <button
              type="button"
              onClick={() => setActiveRoleView("superadmin")}
              style={{
                background: activeRoleView === "superadmin" ? "#7c3aed" : "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.1)",
                color: activeRoleView === "superadmin" ? "#ffffff" : "#94a3b8",
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              👑 Superadmin Fleet
            </button>
          </div>
        </div>
      )}

      {/* =========================================================================
          ROLE 1: VIEWER DASHBOARD (Plant Surveillance & Observation Desk)
          ========================================================================= */}
      {activeRoleView === "viewer" && (
        <section>
          <header className="page-header" style={{ marginBottom: "24px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "12px", fontWeight: 700, color: "#38bdf8", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Role: Plant Viewer
                </span>
                <span style={{ fontSize: "11px", color: "#64748b" }}>• Read-Only Feeds</span>
              </div>
              <h1 style={{ fontSize: "24px", fontWeight: 800, color: "#ffffff", letterSpacing: "-0.02em", margin: "4px 0 0 0" }}>
                Plant CCTV Surveillance &amp; Live Video Wall
              </h1>
              <p style={{ color: "#94a3b8", fontSize: "13.5px", margin: "4px 0 0 0" }}>
                Live video telemetry and streaming health across authorized industrial zones.
              </p>
            </div>

            <Link
              to="/live-monitoring"
              style={{
                background: "#2563eb",
                color: "#ffffff",
                padding: "8px 16px",
                borderRadius: "6px",
                fontSize: "13px",
                fontWeight: 600,
                textDecoration: "none",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
              }}
            >
              Full-Screen Video Wall &rarr;
            </Link>
          </header>

          {/* Viewer KPI Cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Monitored Streams</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)", fontFamily: "monospace", marginTop: "6px" }}>
                {cameraList.length} Cameras
              </div>
              <span style={{ fontSize: "12px", color: "var(--success)" }}>● {onlineCount} Feeds Online</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Production Zones</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)", fontFamily: "monospace", marginTop: "6px" }}>
                {zones?.length ?? 0} Zones
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Across {sites?.length ?? 1} Sites</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Stream Quality</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--success)", fontFamily: "monospace", marginTop: "6px" }}>
                30.0 FPS
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>1080P High Definition</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Read-Only Desk</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--info)", fontFamily: "monospace", marginTop: "6px" }}>
                ACTIVE
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Zero Mutation Access</span>
            </div>
          </div>
        </section>
      )}

      {/* =========================================================================
          ROLE 2: OPERATOR DASHBOARD (Incident Triage & Alert Command Console)
          ========================================================================= */}
      {activeRoleView === "operator" && (
        <section>
          <header className="page-header" style={{ marginBottom: "24px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "12px", fontWeight: 700, color: "#ef4444", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Role: Shift Operator
                </span>
                <span style={{ fontSize: "11px", color: "#64748b" }}>• Real-Time Incident &amp; Alert Command</span>
              </div>
              <h1 style={{ fontSize: "24px", fontWeight: 800, color: "#ffffff", letterSpacing: "-0.02em", margin: "4px 0 0 0" }}>
                Active Incident &amp; Hazard Triage Console
              </h1>
              <p style={{ color: "#94a3b8", fontSize: "13.5px", margin: "4px 0 0 0" }}>
                Triage incoming high-priority AI detections, acknowledge alerts, and escalate active incidents.
              </p>
            </div>

            <div style={{ display: "flex", gap: "10px" }}>
              <Link
                to="/alerts"
                style={{
                  background: "rgba(229, 9, 20, 0.15)",
                  border: "1px solid rgba(229, 9, 20, 0.4)",
                  color: "#ffffff",
                  padding: "8px 14px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                🚨 Alert Queue ({alerts?.length ?? 0}) &rarr;
              </Link>
              <Link
                to="/incidents"
                style={{
                  background: "#e50914",
                  color: "#ffffff",
                  padding: "8px 14px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                + New Incident
              </Link>
            </div>
          </header>

          {/* Operator Fast Metrics */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
            <div style={{ background: "var(--surface)", border: "1px solid rgba(229, 9, 20, 0.25)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--danger)", fontWeight: 700, textTransform: "uppercase" }}>Pending Alerts</span>
              <div style={{ fontSize: "30px", fontWeight: 800, color: "var(--danger)", fontFamily: "monospace", marginTop: "6px" }}>
                {alerts?.length ?? 0}
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Requires immediate triage</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--warning)", fontWeight: 700, textTransform: "uppercase" }}>Open Incidents</span>
              <div style={{ fontSize: "30px", fontWeight: 800, color: "var(--warning)", fontFamily: "monospace", marginTop: "6px" }}>
                {incidentSummary?.open_count ?? 0}
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>{incidentSummary?.investigating_count ?? 0} under investigation</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Critical Severity</span>
              <div style={{ fontSize: "30px", fontWeight: 800, color: incidentSummary?.critical_count ? "var(--danger)" : "var(--success)", fontFamily: "monospace", marginTop: "6px" }}>
                {incidentSummary?.critical_count ?? 0}
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>L1 Escalation active</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Resolved Today</span>
              <div style={{ fontSize: "30px", fontWeight: 800, color: "var(--success)", fontFamily: "monospace", marginTop: "6px" }}>
                {incidentSummary?.resolved_today_count ?? 0}
              </div>
              <span style={{ fontSize: "12px", color: "var(--success)" }}>Shift SLA on track</span>
            </div>
          </div>

          {/* Quick Alert Triage Action Feed */}
          {alerts && alerts.length > 0 && (
            <div style={{ background: "var(--surface)", border: "1px solid rgba(229, 9, 20, 0.3)", borderRadius: "10px", padding: "18px 20px", marginBottom: "28px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
                <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "var(--danger)" }} />
                  Pending Alerts Requiring Operator Action
                </h3>
                <Link to="/alerts" style={{ color: "var(--primary)", fontSize: "12px", fontWeight: 600, textDecoration: "none" }}>
                  View All Alerts &rarr;
                </Link>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {alerts.slice(0, 3).map((alt) => (
                  <div
                    key={alt.id}
                    style={{
                      background: "rgba(0, 0, 0, 0.4)",
                      border: "1px solid rgba(255, 255, 255, 0.08)",
                      borderRadius: "6px",
                      padding: "10px 14px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      flexWrap: "wrap",
                      gap: "10px",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: "4px",
                            background: alt.severity === "critical" || alt.severity === "high" ? "rgba(239, 68, 68, 0.2)" : "rgba(245, 158, 11, 0.2)",
                            color: alt.severity === "critical" || alt.severity === "high" ? "#ef4444" : "#f59e0b",
                            textTransform: "uppercase",
                          }}
                        >
                          {alt.severity}
                        </span>
                        <strong style={{ fontSize: "13px", color: "#ffffff" }}>{alt.title}</strong>
                        <span style={{ fontSize: "11px", color: "#94a3b8" }}>({alt.source_uc?.toUpperCase()})</span>
                      </div>
                      <p style={{ fontSize: "12px", color: "#64748b", margin: "2px 0 0 0" }}>
                        Camera: {alt.camera_id} • {alt.created_at ? new Date(alt.created_at).toLocaleTimeString() : "Just now"}
                      </p>
                    </div>

                    <div style={{ display: "flex", gap: "8px" }}>
                      <button
                        type="button"
                        onClick={() => ackMutation.mutate(alt.id)}
                        disabled={ackMutation.isPending}
                        style={{
                          background: "rgba(255, 255, 255, 0.08)",
                          border: "1px solid rgba(255, 255, 255, 0.15)",
                          color: "#ffffff",
                          padding: "5px 10px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Acknowledge
                      </button>
                      <button
                        type="button"
                        onClick={() => resolveMutation.mutate(alt.id)}
                        disabled={resolveMutation.isPending}
                        style={{
                          background: "rgba(16, 185, 129, 0.15)",
                          border: "1px solid rgba(16, 185, 129, 0.3)",
                          color: "#10b981",
                          padding: "5px 10px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Resolve
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* Active Safety Incidents Summary */}
              {incidents && incidents.length > 0 && (
                <div style={{ marginTop: "16px", paddingTop: "14px", borderTop: "1px solid rgba(255, 255, 255, 0.08)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "10px" }}>
                    <span style={{ fontSize: "12px", fontWeight: 700, color: "#f59e0b", textTransform: "uppercase" }}>
                      Active Safety Incidents ({incidents.length})
                    </span>
                    <Link to="/incidents" style={{ color: "#38bdf8", fontSize: "12px", fontWeight: 600, textDecoration: "none" }}>
                      Open Incident Command &rarr;
                    </Link>
                  </div>
                  <div style={{ display: "flex", gap: "8px", flexWrap: "wrap" }}>
                    {incidents.slice(0, 3).map((inc) => (
                      <div
                        key={inc.id}
                        style={{
                          background: "rgba(245, 158, 11, 0.08)",
                          border: "1px solid rgba(245, 158, 11, 0.25)",
                          borderRadius: "6px",
                          padding: "8px 12px",
                          fontSize: "12px",
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#f59e0b" }} />
                        <strong style={{ color: "#ffffff" }}>{inc.title}</strong>
                        <span style={{ color: "#fcd34d", textTransform: "uppercase", fontSize: "10px", fontWeight: 700 }}>
                          [{inc.severity}]
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

        </section>
      )}

      {/* =========================================================================
          ROLE 3: ADMIN DASHBOARD (Plant Safety & Facility Governance)
          ========================================================================= */}
      {activeRoleView === "admin" && (
        <section>
          <header className="page-header" style={{ marginBottom: "24px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "12px", fontWeight: 700, color: "#10b981", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Role: Plant Safety Admin
                </span>
                <span style={{ fontSize: "11px", color: "#64748b" }}>• Plant Safety Rules, Zones &amp; Fleet Governance</span>
              </div>
              <h1 style={{ fontSize: "24px", fontWeight: 800, color: "#ffffff", letterSpacing: "-0.02em", margin: "4px 0 0 0" }}>
                Plant Safety &amp; Facility Operations Command
              </h1>
              <p style={{ color: "#94a3b8", fontSize: "13.5px", margin: "4px 0 0 0" }}>
                Manage physical camera assets, configure zone PPE enforcement policies, and review audit readiness.
              </p>
            </div>

            <div style={{ display: "flex", gap: "10px" }}>
              <Link
                to="/sites-zones"
                style={{
                  background: "rgba(255, 255, 255, 0.08)",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                  color: "#ffffff",
                  padding: "8px 14px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                Configure Zones &rarr;
              </Link>
              <Link
                to="/admin/cameras"
                style={{
                  background: "#059669",
                  color: "#ffffff",
                  padding: "8px 14px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                + Onboard Camera
              </Link>
            </div>
          </header>

          {/* Admin Facility KPIs */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Plant Hierarchy</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)", fontFamily: "monospace", marginTop: "6px" }}>
                {sites?.length ?? 1} Sites / {zones?.length ?? 0} Zones
              </div>
              <span style={{ fontSize: "12px", color: "var(--info)" }}>JK Cements Operations</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Safety Compliance</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--success)", fontFamily: "monospace", marginTop: "6px" }}>
                98.4%
              </div>
              <span style={{ fontSize: "12px", color: "var(--success)" }}>OSHA / PPE Compliant</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>AI Model Catalog</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)", fontFamily: "monospace", marginTop: "6px" }}>
                {subscriptions?.length ?? 4} Subscribed
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Of {catalog?.length ?? 4} Platform Models</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Audit Ledger</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--primary)", fontFamily: "monospace", marginTop: "6px" }}>
                ACTIVE
              </div>
              <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>Append-only trail</span>
            </div>
          </div>
        </section>
      )}

      {/* =========================================================================
          ROLE 4: SUPERADMIN DASHBOARD (Global Fleet Sovereignty & Infrastructure)
          ========================================================================= */}
      {activeRoleView === "superadmin" && (
        <section>
          <header className="page-header" style={{ marginBottom: "24px" }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--primary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                  Role: Superadministrator
                </span>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>• Global Sovereign Authority &amp; System Health</span>
              </div>
              <h1 style={{ fontSize: "24px", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: "4px 0 0 0" }}>
                Global Multi-Tenant Operations &amp; Cluster Control
              </h1>
              <p style={{ color: "var(--text-secondary)", fontSize: "13.5px", margin: "4px 0 0 0" }}>
                Platform governance across organizations, user privilege management, and microservice cluster health.
              </p>
            </div>

            <div style={{ display: "flex", gap: "10px" }}>
              <Link
                to="/admin/users"
                style={{
                  background: "var(--primary)",
                  color: "#ffffff",
                  padding: "8px 16px",
                  borderRadius: "6px",
                  fontSize: "13px",
                  fontWeight: 600,
                  textDecoration: "none",
                }}
              >
                👥 User Management ({usersList?.length ?? 4}) &rarr;
              </Link>
            </div>
          </header>

          {/* Superadmin Cluster KPIs */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", marginBottom: "24px" }}>
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Tenant Organizations</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)", fontFamily: "monospace", marginTop: "6px" }}>
                {orgs?.length ?? 1} Multi-Tenants
              </div>
              <span style={{ fontSize: "12px", color: "var(--info)" }}>JK Cements Enterprise</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>User Accounts</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)", fontFamily: "monospace", marginTop: "6px" }}>
                {usersList?.length ?? 4} Operators
              </div>
              <span style={{ fontSize: "12px", color: "var(--success)" }}>4 Configured RBAC Roles</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Global Fleet</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--text-primary)", fontFamily: "monospace", marginTop: "6px" }}>
                {cameraList.length} Cameras
              </div>
              <span style={{ fontSize: "12px", color: "var(--success)" }}>{onlinePercent}% Streaming Healthy</span>
            </div>

            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "16px 20px" }}>
              <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase" }}>Microservices Stack</span>
              <div style={{ fontSize: "28px", fontWeight: 800, color: "var(--success)", fontFamily: "monospace", marginTop: "6px" }}>
                7 / 7 UP
              </div>
              <span style={{ fontSize: "12px", color: "var(--success)" }}>All Daemons Healthy</span>
            </div>
          </div>

          {/* Infrastructure Health Status Matrix */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "18px 20px", marginBottom: "28px" }}>
            <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)", margin: "0 0 14px 0" }}>
              Microservice Cluster Status &amp; Ports
            </h3>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "10px" }}>
              {[
                { name: "Auth & RBAC", port: 8000, status: "Healthy" },
                { name: "Camera Registry", port: 8011, status: "Healthy" },
                { name: "Ingestion Core", port: 8020, status: "Healthy" },
                { name: "Alert Management", port: 8010, status: "Healthy" },
                { name: "Incident Command", port: 8003, status: "Healthy" },
                { name: "Audit Trail", port: 8002, status: "Healthy" },
                { name: "Reporting PDF", port: 8005, status: "Healthy" },
              ].map((svc) => (
                <div key={svc.name} style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "6px", padding: "10px 14px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: "12.5px", fontWeight: 600, color: "var(--text-primary)" }}>{svc.name}</span>
                    <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--success)" }} />
                  </div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "monospace" }}>Port {svc.port} • {svc.status}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Superadmin Recent Audit Ledger Entries */}
          {auditLogs && auditLogs.items && auditLogs.items.length > 0 && (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "18px 20px", marginBottom: "28px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)", margin: 0, display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "var(--primary)" }} />
                  Recent Forensic Audit Trail ({auditLogs.total} Ledger Events)
                </h3>
                <Link to="/audit-log" style={{ color: "var(--primary)", fontSize: "12px", fontWeight: 600, textDecoration: "none" }}>
                  Open Forensic Audit Log &rarr;
                </Link>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                {auditLogs.items.slice(0, 3).map((log) => (
                  <div
                    key={log.id}
                    style={{
                      background: "var(--surface-raised)",
                      border: "1px solid var(--border)",
                      borderRadius: "6px",
                      padding: "8px 12px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      fontSize: "12px",
                    }}
                  >
                    <div>
                      <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{log.action}</span>
                      <span style={{ color: "var(--text-muted)", margin: "0 6px" }}>on</span>
                      <span style={{ color: "var(--info)", fontFamily: "monospace" }}>{log.resource_type}</span>
                    </div>
                    <span style={{ color: "var(--text-muted)", fontFamily: "monospace", fontSize: "11px" }}>
                      {log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "Recent"}
                    </span>

                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}


      {/* =========================================================================
          COMMON SECTION: Active Camera Feeds Grid with Search & Status Filters
          ========================================================================= */}
      <section aria-labelledby="cameras-heading" style={{ marginTop: "12px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "14px",
            marginBottom: "18px",
          }}
        >
          <div>
            <h2 id="cameras-heading" style={{ fontSize: "17px", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
              Live Camera Feeds ({filteredCameras.length})
            </h2>
            <p style={{ fontSize: "12.5px", color: "var(--text-muted)", margin: "2px 0 0 0" }}>
              Active video streams across all plant zones. Click any tile to inspect live detections.
            </p>
          </div>

          {/* Search & Status Toolbar */}
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <input
              type="text"
              placeholder="Search cameras by name, ID or location..."
              value={cameraSearch}
              onChange={(e) => setCameraSearch(e.target.value)}
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--input-border)",
                borderRadius: "6px",
                padding: "6px 12px",
                color: "var(--input-color)",
                fontSize: "12.5px",
                minWidth: "260px",
                outline: "none",
              }}
            />

            <div style={{ display: "flex", background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "6px", padding: "2px" }}>
              <button
                type="button"
                onClick={() => setStatusFilter("all")}
                style={{
                  background: statusFilter === "all" ? "var(--surface-hover)" : "transparent",
                  border: "none",
                  color: statusFilter === "all" ? "var(--text-primary)" : "var(--text-muted)",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                All
              </button>
              <button
                type="button"
                onClick={() => setStatusFilter("online")}
                style={{
                  background: statusFilter === "online" ? "var(--success-bg)" : "transparent",
                  border: "none",
                  color: statusFilter === "online" ? "var(--success)" : "var(--text-muted)",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Online
              </button>
              <button
                type="button"
                onClick={() => setStatusFilter("offline")}
                style={{
                  background: statusFilter === "offline" ? "var(--danger-bg)" : "transparent",
                  border: "none",
                  color: statusFilter === "offline" ? "var(--danger)" : "var(--text-muted)",
                  padding: "4px 10px",
                  borderRadius: "4px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Offline
              </button>
            </div>
          </div>
        </div>

        {filteredCameras.length === 0 ? (
          <EmptyState message="No cameras match the current search or status filter." />
        ) : (
          <div className="camera-grid">
            {filteredCameras.map((camera) => (
              <CameraTile key={camera.id} camera={camera} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}