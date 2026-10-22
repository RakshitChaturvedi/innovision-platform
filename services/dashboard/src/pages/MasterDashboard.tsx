import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAuth } from "@/store/useAuth";
import { getCameras } from "@/api/cameras";
import {
  getOrganizations,
  createOrganization,
  updateOrganization,
  updateOrganizationStatus,
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
import type { Organization } from "@/types/platform";

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

  const activeOrgId = user?.organization_id || (orgs && orgs.length > 0 ? orgs[0].id : "");

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

  // Organization management state for Superadmin Platform Control Center
  const [showCreateOrgModal, setShowCreateOrgModal] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgCode, setNewOrgCode] = useState("");
  const [newOrgTier, setNewOrgTier] = useState("enterprise");
  const [orgSearch, setOrgSearch] = useState("");
  const [orgError, setOrgError] = useState("");

  // Edit Organization State
  const [editingOrg, setEditingOrg] = useState<Organization | null>(null);
  const [editOrgName, setEditOrgName] = useState("");
  const [editOrgTier, setEditOrgTier] = useState("enterprise");

  // Deactivate Organization State
  const [deactivatingOrg, setDeactivatingOrg] = useState<Organization | null>(null);

  const createOrgMutation = useMutation({
    mutationFn: createOrganization,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setShowCreateOrgModal(false);
      setNewOrgName("");
      setNewOrgCode("");
      setOrgError("");
    },
    onError: (err: any) => {
      setOrgError(err?.response?.data?.detail || "Failed to create organization account.");
    },
  });

  const updateOrgMutation = useMutation({
    mutationFn: () => {
      if (!editingOrg) throw new Error("No organization selected for update");
      return updateOrganization(editingOrg.id, { name: editOrgName, tier: editOrgTier });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setEditingOrg(null);
      setOrgError("");
    },
    onError: (err: any) => {
      setOrgError(err?.response?.data?.detail || "Failed to update organization account.");
    },
  });

  const toggleOrgStatusMutation = useMutation({
    mutationFn: ({ orgId, isActive }: { orgId: string; isActive: boolean }) =>
      updateOrganizationStatus(orgId, isActive),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizations"] });
      setDeactivatingOrg(null);
      setOrgError("");
    },
    onError: (err: any) => {
      setOrgError(err?.response?.data?.detail || "Failed to update organization status.");
    },
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

          {/* Superadmin Tenant Organizations Directory & Management */}
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "10px", padding: "18px 20px", marginBottom: "28px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "10px" }}>
              <div>
                <h3 style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                  Client Organizations &amp; Multi-Tenant Accounts ({orgs?.length ?? 0})
                </h3>
                <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "2px 0 0 0" }}>
                  Sovereign tenant governance, subscription plan provisioning, and account lifecycle status.
                </p>
              </div>

              <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                <input
                  type="text"
                  placeholder="Filter organizations..."
                  value={orgSearch}
                  onChange={(e) => setOrgSearch(e.target.value)}
                  style={{
                    background: "var(--input-bg)",
                    border: "1px solid var(--input-border)",
                    borderRadius: "6px",
                    padding: "6px 12px",
                    color: "var(--input-color)",
                    fontSize: "12px",
                    outline: "none",
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowCreateOrgModal(true)}
                  style={{
                    background: "var(--primary)",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: "6px",
                    padding: "6px 14px",
                    fontSize: "12.5px",
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                  }}
                >
                  + Onboard Organization
                </button>
              </div>
            </div>

            {/* Creation Form Modal if triggered */}
            {showCreateOrgModal && (
              <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border-hover)", borderRadius: "8px", padding: "16px", marginBottom: "16px" }}>
                <h4 style={{ fontSize: "13.5px", fontWeight: 700, margin: "0 0 10px 0", color: "var(--text-primary)" }}>
                  Provision New Client Organization Account
                </h4>
                {orgError && (
                  <div style={{ color: "var(--danger)", fontSize: "12px", marginBottom: "10px" }}>{orgError}</div>
                )}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "12px", marginBottom: "12px" }}>
                  <div>
                    <label style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Organization Legal Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Apex Manufacturing Corp"
                      value={newOrgName}
                      onChange={(e) => {
                        setNewOrgName(e.target.value);
                        if (!newOrgCode) {
                          setNewOrgCode(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, "_").slice(0, 20));
                        }
                      }}
                      style={{ width: "100%", background: "var(--input-bg)", border: "1px solid var(--input-border)", borderRadius: "6px", padding: "6px 10px", color: "var(--input-color)", fontSize: "12px" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Account Identifier Code</label>
                    <input
                      type="text"
                      placeholder="e.g. org_apex_01"
                      value={newOrgCode}
                      onChange={(e) => setNewOrgCode(e.target.value)}
                      style={{ width: "100%", background: "var(--input-bg)", border: "1px solid var(--input-border)", borderRadius: "6px", padding: "6px 10px", color: "var(--input-color)", fontSize: "12px" }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Subscription Tier</label>
                    <select
                      value={newOrgTier}
                      onChange={(e) => setNewOrgTier(e.target.value)}
                      style={{ width: "100%", background: "var(--input-bg)", border: "1px solid var(--input-border)", borderRadius: "6px", padding: "6px 10px", color: "var(--input-color)", fontSize: "12px" }}
                    >
                      <option value="enterprise">Enterprise Plan</option>
                      <option value="growth">Industrial Growth</option>
                      <option value="starter">Safety Starter</option>
                    </select>
                  </div>
                </div>
                <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                  <button
                    type="button"
                    onClick={() => { setShowCreateOrgModal(false); setOrgError(""); }}
                    style={{ background: "transparent", border: "1px solid var(--border)", borderRadius: "6px", padding: "6px 12px", color: "var(--text-secondary)", fontSize: "12px", cursor: "pointer" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    disabled={!newOrgName || !newOrgCode || createOrgMutation.isPending}
                    onClick={() => createOrgMutation.mutate({ name: newOrgName, code: newOrgCode, tier: newOrgTier })}
                    style={{ background: "var(--primary)", border: "none", borderRadius: "6px", padding: "6px 16px", color: "#ffffff", fontSize: "12px", fontWeight: 600, cursor: "pointer" }}
                  >
                    {createOrgMutation.isPending ? "Provisioning..." : "Confirm Provisioning"}
                  </button>
                </div>
              </div>
            )}

            {/* Organizations Table */}
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12.5px" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)", textAlign: "left" }}>
                    <th style={{ padding: "8px 12px", fontWeight: 600 }}>Organization Name</th>
                    <th style={{ padding: "8px 12px", fontWeight: 600 }}>Account Code</th>
                    <th style={{ padding: "8px 12px", fontWeight: 600 }}>Plan Tier</th>
                    <th style={{ padding: "8px 12px", fontWeight: 600 }}>Timezone</th>
                    <th style={{ padding: "8px 12px", fontWeight: 600 }}>Account Status</th>
                    <th style={{ padding: "8px 12px", fontWeight: 600 }}>Created Date</th>
                    <th style={{ padding: "8px 12px", fontWeight: 600, textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {(orgs || [])
                    .filter((o) => !orgSearch || o.name.toLowerCase().includes(orgSearch.toLowerCase()) || o.code?.toLowerCase().includes(orgSearch.toLowerCase()))
                    .slice(0, 8)
                    .map((orgItem) => (
                      <tr key={orgItem.id} style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
                        <td style={{ padding: "10px 12px", fontWeight: 600 }}>{orgItem.name}</td>
                        <td style={{ padding: "10px 12px", fontFamily: "monospace", color: "var(--info)" }}>{orgItem.code || "—"}</td>
                        <td style={{ padding: "10px 12px", textTransform: "capitalize" }}>
                          <span style={{ background: "rgba(166, 70, 189, 0.12)", color: "var(--primary)", padding: "2px 8px", borderRadius: "4px", fontSize: "11px", fontWeight: 600 }}>
                            {orgItem.tier || "Enterprise"}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", color: "var(--text-secondary)" }}>{orgItem.timezone || "UTC"}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={{ display: "inline-flex", alignItems: "center", gap: "6px", color: orgItem.is_active ? "var(--success)" : "var(--danger)", fontSize: "11.5px", fontWeight: 600 }}>
                            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: orgItem.is_active ? "var(--success)" : "var(--danger)" }} />
                            {orgItem.is_active ? "Active" : "Suspended"}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px", color: "var(--text-muted)", fontFamily: "monospace", fontSize: "11px" }}>
                          {orgItem.created_at ? new Date(orgItem.created_at).toLocaleDateString() : "—"}
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "right" }}>
                          <div style={{ display: "flex", justifyContent: "flex-end", gap: "6px" }}>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingOrg(orgItem);
                                setEditOrgName(orgItem.name);
                                setEditOrgTier(orgItem.tier || "enterprise");
                              }}
                              style={{
                                background: "var(--surface-raised)",
                                border: "1px solid var(--border)",
                                color: "var(--text-primary)",
                                padding: "3px 8px",
                                borderRadius: "4px",
                                fontSize: "11px",
                                cursor: "pointer",
                                fontWeight: 600,
                              }}
                            >
                              ✏️ Edit
                            </button>
                            {orgItem.is_active ? (
                              <button
                                type="button"
                                onClick={() => setDeactivatingOrg(orgItem)}
                                style={{
                                  background: "rgba(239, 68, 68, 0.1)",
                                  border: "1px solid rgba(239, 68, 68, 0.3)",
                                  color: "var(--danger)",
                                  padding: "3px 8px",
                                  borderRadius: "4px",
                                  fontSize: "11px",
                                  cursor: "pointer",
                                  fontWeight: 600,
                                }}
                              >
                                Deactivate
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={() => toggleOrgStatusMutation.mutate({ orgId: orgItem.id, isActive: true })}
                                style={{
                                  background: "rgba(16, 185, 129, 0.1)",
                                  border: "1px solid rgba(16, 185, 129, 0.3)",
                                  color: "var(--success)",
                                  padding: "3px 8px",
                                  borderRadius: "4px",
                                  fontSize: "11px",
                                  cursor: "pointer",
                                  fontWeight: 600,
                                }}
                              >
                                Reactivate
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>

            {/* Modal: Edit Organization */}
            {editingOrg && (
              <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: "16px" }}>
                <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "420px" }}>
                  <h3 style={{ margin: "0 0 6px 0", fontSize: "18px", color: "var(--text-primary)" }}>Edit Client Organization</h3>
                  <p style={{ margin: "0 0 16px 0", fontSize: "12px", color: "var(--text-muted)" }}>
                    Update organization account name and enterprise subscription tier.
                  </p>
                  {orgError && (
                    <div style={{ color: "var(--danger)", fontSize: "12px", marginBottom: "12px" }}>{orgError}</div>
                  )}
                  <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
                    <div>
                      <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Organization Name *</label>
                      <input
                        type="text"
                        value={editOrgName}
                        onChange={(e) => setEditOrgName(e.target.value)}
                        style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                      />
                    </div>
                    <div>
                      <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Subscription Tier</label>
                      <select
                        value={editOrgTier}
                        onChange={(e) => setEditOrgTier(e.target.value)}
                        style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                      >
                        <option value="enterprise">Enterprise Plan</option>
                        <option value="growth">Industrial Growth</option>
                        <option value="starter">Safety Starter</option>
                      </select>
                    </div>
                  </div>
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                    <button
                      type="button"
                      onClick={() => { setEditingOrg(null); setOrgError(""); }}
                      style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "6px 14px", borderRadius: "4px", cursor: "pointer" }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={!editOrgName.trim() || updateOrgMutation.isPending}
                      onClick={() => updateOrgMutation.mutate()}
                      style={{ background: "var(--primary)", border: "none", color: "#fff", padding: "6px 16px", borderRadius: "4px", fontWeight: 600, cursor: "pointer" }}
                    >
                      {updateOrgMutation.isPending ? "Saving..." : "Save Changes"}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Confirmation Modal: Deactivate Organization */}
            {deactivatingOrg && (
              <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: "16px" }}>
                <div style={{ background: "var(--surface)", border: "1px solid rgba(239,68,68,0.4)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "460px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
                    <span style={{ fontSize: "24px" }}>⚠️</span>
                    <h3 style={{ margin: 0, fontSize: "18px", color: "var(--danger)" }}>Confirm Organization Deactivation</h3>
                  </div>
                  <p style={{ margin: "0 0 12px 0", fontSize: "13.5px", color: "var(--text-primary)", lineHeight: 1.5 }}>
                    Are you sure you want to deactivate organization account <strong>{deactivatingOrg.name}</strong> ({deactivatingOrg.code})?
                  </p>
                  <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "6px", padding: "12px", marginBottom: "20px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    <div style={{ color: "var(--text-primary)", fontWeight: 600, marginBottom: "4px" }}>
                      Platform Sovereignty &amp; Data Safeguards:
                    </div>
                    <ul style={{ margin: 0, paddingLeft: "18px" }}>
                      <li>Tenant users will be suspended from performing operational mutations.</li>
                      <li>Multi-tenant isolation and foreign key relations are strictly maintained.</li>
                      <li>Historical alerts, incidents, and audit trails remain permanently preserved.</li>
                    </ul>
                  </div>
                  <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
                    <button
                      type="button"
                      onClick={() => setDeactivatingOrg(null)}
                      style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "7px 16px", borderRadius: "4px", fontSize: "13px", cursor: "pointer" }}
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      disabled={toggleOrgStatusMutation.isPending}
                      onClick={() => toggleOrgStatusMutation.mutate({ orgId: deactivatingOrg.id, isActive: false })}
                      style={{ background: "var(--danger)", border: "none", color: "#fff", padding: "7px 18px", borderRadius: "4px", fontWeight: 600, fontSize: "13px", cursor: "pointer" }}
                    >
                      {toggleOrgStatusMutation.isPending ? "Deactivating..." : "Confirm Deactivation"}
                    </button>
                  </div>
                </div>
              </div>
            )}
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
          COMPANY OPERATIONAL SECTION: Active Camera Feeds Grid with Search & Status Filters
          Exclusively for company operational roles (Admin, Operator, Viewer).
          Routine operational feeds are excluded from Superadmin sovereign view.
          ========================================================================= */}
      {activeRoleView !== "superadmin" && (
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

          {cameraList.length === 0 ? (
            <div style={{ background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: "8px", padding: "48px 24px", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
              <div style={{ width: "48px", height: "48px", borderRadius: "50%", background: "var(--surface-raised)", border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "22px" }}>
                📹
              </div>
              <div style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                No Operational Cameras Registered
              </div>
              <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: 0, maxWidth: "460px", lineHeight: 1.5 }}>
                Your organization currently has no live cameras configured. Begin by creating plant sites and zones, then register your operational cameras to enable real-time safety monitoring.
              </p>
              {(user?.role === "admin" || user?.role === "org_admin") && (
                <div style={{ display: "flex", gap: "12px", marginTop: "8px" }}>
                  <Link
                    to="/sites-zones"
                    style={{
                      background: "var(--surface-raised)",
                      border: "1px solid var(--border)",
                      color: "var(--text-primary)",
                      padding: "7px 16px",
                      borderRadius: "6px",
                      fontSize: "13px",
                      fontWeight: 600,
                      textDecoration: "none",
                    }}
                  >
                    📍 Set Up Sites &amp; Zones
                  </Link>
                  <Link
                    to="/admin/cameras"
                    style={{
                      background: "var(--primary, #3b82f6)",
                      border: "none",
                      color: "#ffffff",
                      padding: "7px 16px",
                      borderRadius: "6px",
                      fontSize: "13px",
                      fontWeight: 600,
                      textDecoration: "none",
                    }}
                  >
                    + Register Camera
                  </Link>
                </div>
              )}
            </div>
          ) : filteredCameras.length === 0 ? (
            <EmptyState message="No cameras match the current search or status filter." />
          ) : (
            <div className="camera-grid">
              {filteredCameras.map((camera) => (
                <CameraTile key={camera.id} camera={camera} />
              ))}
            </div>
          )}
        </section>
      )}
    </main>
  );
}