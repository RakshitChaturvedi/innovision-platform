import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getIncidents,
  getIncident,
  getIncidentSummary,
  createIncident,
  updateIncidentStatus,
  assignIncident,
  linkAlertToIncident,
  unlinkAlertFromIncident,
  type IncidentFilters,
} from "@/api/incidents";
import { getSites, getZones, getOrganizations } from "@/api/platform";
import { getCameras } from "@/api/cameras";
import { getUsers } from "@/api/users";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";
import type { Alert } from "@/types/alert";

export function Incidents() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const canOperate = hasMinimumRole(user, "operator");
  const canCloseIncident = hasMinimumRole(user, "admin");

  // Filters state
  const [filters, setFilters] = useState<IncidentFilters>({});
  const [searchTitle, setSearchTitle] = useState("");

  // Selected incident detail state
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);

  // Create Modal state
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    title: "",
    description: "",
    severity: "medium",
    site_id: "",
    zone_id: "",
    camera_id: "",
    source_type: "manual",
    assigned_to: "",
    alert_ids: [] as string[],
  });

  // Link Alert input state in detail drawer
  const [alertIdToLink, setAlertIdToLink] = useState("");

  // Handle pre-associated alert from navigation
  useEffect(() => {
    const navState = location.state as { createForAlert?: Alert } | null;
    if (navState?.createForAlert) {
      const alertItem = navState.createForAlert;
      setTimeout(() => {
        setCreateForm({
          title: alertItem.title || `Incident from alert ${alertItem.alert_id}`,
          description: `Created from alert ${alertItem.alert_id} (Source: ${alertItem.source_uc?.toUpperCase()})`,
          severity: alertItem.severity || "medium",
          site_id: "",
          zone_id: "",
          camera_id: alertItem.camera_id || "",
          source_type: "alert",
          assigned_to: "",
          alert_ids: [alertItem.alert_id],
        });
        setIsCreateModalOpen(true);
      }, 0);
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location.state, navigate, location.pathname]);

  // Queries
  const { data: orgs } = useQuery({
    queryKey: ["organizations"],
    queryFn: getOrganizations,
  });

  const activeOrgId = orgs && orgs.length > 0 ? orgs[0].id : "";

  const { data: incidentSummary } = useQuery({
    queryKey: ["incidentSummary", activeOrgId],
    queryFn: () => getIncidentSummary(activeOrgId),
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

  const { data: cameras } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });

  const { data: users } = useQuery({
    queryKey: ["users"],
    queryFn: () => getUsers(),
  });

  const {
    data: incidents,
    isLoading: loadingIncidents,
    isError: errorIncidents,
  } = useQuery({
    queryKey: ["incidents", filters],
    queryFn: () => getIncidents(filters),
    refetchInterval: 5000,
  });

  const { data: selectedIncidentDetail } = useQuery({
    queryKey: ["incidentDetail", selectedIncidentId],
    queryFn: () => (selectedIncidentId ? getIncident(selectedIncidentId) : null),
    enabled: Boolean(selectedIncidentId),
    refetchInterval: 3000,
  });

  // Mutations
  const createMutation = useMutation({
    mutationFn: createIncident,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["incidentSummary"] });
      setIsCreateModalOpen(false);
      setSelectedIncidentId(data.incident.id);
      setCreateForm({
        title: "",
        description: "",
        severity: "medium",
        site_id: "",
        zone_id: "",
        camera_id: "",
        source_type: "manual",
        assigned_to: "",
        alert_ids: [],
      });
    },
  });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      updateIncidentStatus(id, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["incidentDetail"] });
      queryClient.invalidateQueries({ queryKey: ["incidentSummary"] });
    },
  });

  const assignMutation = useMutation({
    mutationFn: ({ id, assignedTo }: { id: string; assignedTo: string | null }) =>
      assignIncident(id, assignedTo),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      queryClient.invalidateQueries({ queryKey: ["incidentDetail"] });
    },
  });

  const linkAlertMutation = useMutation({
    mutationFn: ({ incidentId, alertId }: { incidentId: string; alertId: string }) =>
      linkAlertToIncident(incidentId, alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidentDetail"] });
      setAlertIdToLink("");
    },
  });

  const unlinkAlertMutation = useMutation({
    mutationFn: ({ incidentId, alertId }: { incidentId: string; alertId: string }) =>
      unlinkAlertFromIncident(incidentId, alertId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidentDetail"] });
    },
  });

  const filteredIncidents = (incidents || []).filter((inc) => {
    if (!searchTitle) return true;
    return (
      inc.title.toLowerCase().includes(searchTitle.toLowerCase()) ||
      inc.id.toLowerCase().includes(searchTitle.toLowerCase()) ||
      (inc.description && inc.description.toLowerCase().includes(searchTitle.toLowerCase()))
    );
  });

  return (
    <main className="page" style={{ position: "relative" }}>
      <header className="page-header">
        <div>
          <h1 className="page-title">Enterprise Incident Management</h1>
          <p className="page-description">
            Analytics-agnostic operational incident tracking, alert grouping, workflow & resolution management.
          </p>
        </div>
        {canOperate && (
          <button
            type="button"
            className="button button-primary"
            onClick={() => setIsCreateModalOpen(true)}
            style={{
              background: "var(--primary)",
              color: "#fff",
              padding: "8px 16px",
              borderRadius: "6px",
              fontWeight: 600,
              cursor: "pointer",
              border: "none",
            }}
          >
            + Create Incident
          </button>
        )}
      </header>

      {/* Summary Cards */}
      <section
        className="dashboard-stats"
        aria-label="Incident summary statistics"
        style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "16px", marginBottom: "24px" }}
      >
        <div className="stat" style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: "16px", borderRadius: "6px" }}>
          <span className="stat-label" style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Open Incidents</span>
          <strong className="stat-value" style={{ fontSize: "24px", color: "var(--warning)" }}>{incidentSummary?.open_count ?? 0}</strong>
        </div>

        <div className="stat" style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: "16px", borderRadius: "6px" }}>
          <span className="stat-label" style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Investigating</span>
          <strong className="stat-value" style={{ fontSize: "24px", color: "var(--primary)" }}>{incidentSummary?.investigating_count ?? 0}</strong>
        </div>

        <div className="stat" style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: "16px", borderRadius: "6px" }}>
          <span className="stat-label" style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Critical Incidents</span>
          <strong className="stat-value" style={{ fontSize: "24px", color: "var(--danger)" }}>{incidentSummary?.critical_count ?? 0}</strong>
        </div>

        <div className="stat" style={{ background: "var(--surface)", border: "1px solid var(--border)", padding: "16px", borderRadius: "6px" }}>
          <span className="stat-label" style={{ fontSize: "12px", color: "var(--text-secondary)" }}>Resolved Today</span>
          <strong className="stat-value" style={{ fontSize: "24px", color: "var(--success)" }}>{incidentSummary?.resolved_today_count ?? 0}</strong>
        </div>
      </section>

      {/* Filters Bar */}
      <section className="alert-filters" aria-label="Incident filters" style={{ marginBottom: "20px" }}>
        <div className="filter-field">
          <label>Search</label>
          <input
            type="text"
            placeholder="Search by title or ID..."
            value={searchTitle}
            onChange={(e) => setSearchTitle(e.target.value)}
          />
        </div>

        <div className="filter-field">
          <label>Status</label>
          <select
            value={filters.status ?? ""}
            onChange={(e) => setFilters({ ...filters, status: e.target.value || undefined })}
          >
            <option value="">All Statuses</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="investigating">Investigating</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        <div className="filter-field">
          <label>Severity</label>
          <select
            value={filters.severity ?? ""}
            onChange={(e) => setFilters({ ...filters, severity: e.target.value || undefined })}
          >
            <option value="">All Severities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>

        <div className="filter-field">
          <label>Site</label>
          <select
            value={filters.site_id ?? ""}
            onChange={(e) => setFilters({ ...filters, site_id: e.target.value || undefined })}
          >
            <option value="">All Sites</option>
            {sites?.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-field">
          <label>Zone</label>
          <select
            value={filters.zone_id ?? ""}
            onChange={(e) => setFilters({ ...filters, zone_id: e.target.value || undefined })}
          >
            <option value="">All Zones</option>
            {zones?.map((z) => (
              <option key={z.id} value={z.id}>{z.name}</option>
            ))}
          </select>
        </div>

        <div className="filter-field">
          <label>Assigned User</label>
          <select
            value={filters.assigned_to ?? ""}
            onChange={(e) => setFilters({ ...filters, assigned_to: e.target.value || undefined })}
          >
            <option value="">All Assignees</option>
            {users?.map((u) => (
              <option key={u.id} value={u.id}>{u.name} ({u.role})</option>
            ))}
          </select>
        </div>

        {Object.values(filters).some(Boolean) || searchTitle ? (
          <button
            type="button"
            className="clear-filters-button"
            onClick={() => { setFilters({}); setSearchTitle(""); }}
          >
            Clear Filters
          </button>
        ) : null}
      </section>

      {/* Main Content Area */}
      <div style={{ display: "grid", gridTemplateColumns: selectedIncidentId ? "1fr 450px" : "1fr", gap: "24px" }}>
        {/* Table section */}
        <section aria-label="Incident table section">
          {loadingIncidents ? (
            <LoadingState message="Loading incidents..." />
          ) : errorIncidents ? (
            <ErrorState message="Failed to load incidents." />
          ) : filteredIncidents.length === 0 ? (
            <EmptyState message="No incidents match the current filters." />
          ) : (
            <div style={{ overflowX: "auto", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "6px" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
                <thead>
                  <tr style={{ background: "var(--surface-hover)", borderBottom: "1px solid var(--border)", color: "var(--text-secondary)" }}>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>INCIDENT ID</th>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>TITLE</th>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>SEVERITY</th>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>STATUS</th>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>SITE / ZONE / CAMERA</th>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>ASSIGNEE</th>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>CREATED</th>
                    <th style={{ padding: "12px 14px", fontWeight: 600 }}>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredIncidents.map((inc) => {
                    const isSelected = inc.id === selectedIncidentId;
                    return (
                      <tr
                        key={inc.id}
                        style={{
                          borderBottom: "1px solid var(--border)",
                          background: isSelected ? "var(--surface-selected, rgba(59,130,246,0.08))" : "transparent",
                          cursor: "pointer",
                        }}
                        onClick={() => setSelectedIncidentId(inc.id)}
                      >
                        <td style={{ padding: "12px 14px", fontFamily: "monospace", fontWeight: 600, color: "var(--primary)" }}>
                          INC-{inc.id.slice(0, 8).toUpperCase()}
                        </td>
                        <td style={{ padding: "12px 14px", fontWeight: 600 }}>
                          {inc.title}
                          {inc.description && (
                            <div style={{ fontSize: "11px", color: "var(--text-secondary)", fontWeight: 400, marginTop: "2px" }}>
                              {inc.description.slice(0, 60)}{inc.description.length > 60 ? "..." : ""}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          <span
                            style={{
                              padding: "2px 8px",
                              borderRadius: "10px",
                              fontSize: "11px",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              background:
                                inc.severity === "critical"
                                  ? "#fef2f2"
                                  : inc.severity === "high"
                                  ? "#fff7ed"
                                  : inc.severity === "medium"
                                  ? "#fefce8"
                                  : "#f0fdf4",
                              color:
                                inc.severity === "critical"
                                  ? "#dc2626"
                                  : inc.severity === "high"
                                  ? "#ea580c"
                                  : inc.severity === "medium"
                                  ? "#ca8a04"
                                  : "#16a34a",
                            }}
                          >
                            {inc.severity}
                          </span>
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          <span
                            style={{
                              padding: "2px 8px",
                              borderRadius: "10px",
                              fontSize: "11px",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              background:
                                inc.status === "open"
                                  ? "#eff6ff"
                                  : inc.status === "investigating"
                                  ? "#f5f3ff"
                                  : inc.status === "resolved"
                                  ? "#f0fdf4"
                                  : "#f3f4f6",
                              color:
                                inc.status === "open"
                                  ? "#2563eb"
                                  : inc.status === "investigating"
                                  ? "#7c3aed"
                                  : inc.status === "resolved"
                                  ? "#16a34a"
                                  : "#6b7280",
                            }}
                          >
                            {inc.status}
                          </span>
                        </td>
                        <td style={{ padding: "12px 14px", color: "var(--text-secondary)", fontSize: "12px" }}>
                          {inc.site_name || "—"} {inc.zone_name ? `> ${inc.zone_name}` : ""} {inc.camera_name ? `> ${inc.camera_name}` : ""}
                        </td>
                        <td style={{ padding: "12px 14px", fontSize: "12px" }}>
                          {inc.assigned_to_name ? (
                            <span style={{ fontWeight: 600 }}>{inc.assigned_to_name}</span>
                          ) : (
                            <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>Unassigned</span>
                          )}
                        </td>
                        <td style={{ padding: "12px 14px", color: "var(--text-secondary)", fontSize: "11px" }}>
                          {new Date(inc.created_at).toLocaleString()}
                        </td>
                        <td style={{ padding: "12px 14px" }}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedIncidentId(inc.id);
                            }}
                            style={{
                              background: "none",
                              border: "1px solid var(--border)",
                              borderRadius: "4px",
                              padding: "4px 8px",
                              fontSize: "11px",
                              cursor: "pointer",
                              color: "var(--primary)",
                            }}
                          >
                            View Detail
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Incident Detail Drawer Panel */}
        {selectedIncidentId && (
          <aside
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              padding: "20px",
              display: "flex",
              flexDirection: "column",
              gap: "20px",
              maxHeight: "calc(100vh - 180px)",
              overflowY: "auto",
            }}
          >
            {selectedIncidentDetail ? (
              <>
                {/* Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--border)", paddingBottom: "14px" }}>
                  <div>
                    <span style={{ fontSize: "11px", fontFamily: "monospace", color: "var(--primary)", fontWeight: 700 }}>
                      INC-{selectedIncidentDetail.incident.id.slice(0, 8).toUpperCase()}
                    </span>
                    <h2 style={{ fontSize: "18px", fontWeight: 700, margin: "4px 0", color: "var(--text-primary)" }}>
                      {selectedIncidentDetail.incident.title}
                    </h2>
                    <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                      Created: {new Date(selectedIncidentDetail.incident.created_at).toLocaleString()}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedIncidentId(null)}
                    style={{ background: "none", border: "none", fontSize: "18px", cursor: "pointer", color: "var(--text-secondary)" }}
                  >
                    ✕
                  </button>
                </div>

                {/* Status & Severity Badges */}
                <div style={{ display: "flex", gap: "10px", alignItems: "center" }}>
                  <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)" }}>Severity:</span>
                  <span style={{ padding: "3px 10px", borderRadius: "12px", fontSize: "11px", fontWeight: 700, textTransform: "uppercase", background: "var(--surface-hover)" }}>
                    {selectedIncidentDetail.incident.severity}
                  </span>
                  <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginLeft: "10px" }}>Status:</span>
                  <span style={{ padding: "3px 10px", borderRadius: "12px", fontSize: "11px", fontWeight: 700, textTransform: "uppercase", background: "var(--surface-hover)" }}>
                    {selectedIncidentDetail.incident.status}
                  </span>
                </div>

                {/* Status Workflow Controls */}
                <div style={{ background: "var(--surface-hover)", padding: "12px", borderRadius: "6px", border: "1px solid var(--border)" }}>
                  <span style={{ fontSize: "12px", fontWeight: 700, color: "var(--text-primary)", display: "block", marginBottom: "8px" }}>
                    Workflow Action / Status Transition
                  </span>
                  {!canOperate ? (
                    <div style={{ fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic" }}>
                      Read-only observation mode. Status transitions require Shift Operator or Admin permissions.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                      {selectedIncidentDetail.valid_next_states.map((nextState) => {
                        const isRestrictedClose = nextState === "closed" && !canCloseIncident;
                        return (
                          <button
                            key={nextState}
                            type="button"
                            disabled={statusMutation.isPending || isRestrictedClose}
                            title={isRestrictedClose ? "Incident closure is restricted to Organization Admin and Superadmin" : undefined}
                            onClick={() =>
                              !isRestrictedClose && statusMutation.mutate({ id: selectedIncidentDetail.incident.id, status: nextState })
                            }
                            style={{
                              background: isRestrictedClose ? "var(--surface)" : "var(--primary)",
                              color: isRestrictedClose ? "var(--text-muted)" : "#fff",
                              border: isRestrictedClose ? "1px solid var(--border)" : "none",
                              borderRadius: "4px",
                              padding: "6px 12px",
                              fontSize: "12px",
                              fontWeight: 600,
                              cursor: isRestrictedClose ? "not-allowed" : "pointer",
                              textTransform: "capitalize",
                              opacity: isRestrictedClose ? 0.6 : 1,
                            }}
                          >
                            Transition to {nextState} {isRestrictedClose && "(Admin only)"}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Context Details */}
                <div>
                  <h4 style={{ fontSize: "13px", fontWeight: 700, marginBottom: "8px", color: "var(--text-primary)" }}>Hierarchy Context</h4>
                  <div style={{ fontSize: "12px", color: "var(--text-secondary)", display: "grid", gap: "4px" }}>
                    <div><strong>Organization:</strong> {selectedIncidentDetail.incident.organization_name || selectedIncidentDetail.incident.organization_id}</div>
                    <div><strong>Site:</strong> {selectedIncidentDetail.incident.site_name || "Unspecified"}</div>
                    <div><strong>Zone:</strong> {selectedIncidentDetail.incident.zone_name || "Unspecified"}</div>
                    <div><strong>Camera:</strong> {selectedIncidentDetail.incident.camera_name || "Unspecified"}</div>
                  </div>
                </div>

                {/* Assignment Control */}
                <div>
                  <h4 style={{ fontSize: "13px", fontWeight: 700, marginBottom: "8px", color: "var(--text-primary)" }}>Assignee</h4>
                  {canOperate ? (
                    <div style={{ display: "flex", gap: "8px" }}>
                      <select
                        value={selectedIncidentDetail.incident.assigned_to || ""}
                        onChange={(e) =>
                          assignMutation.mutate({
                            id: selectedIncidentDetail.incident.id,
                            assignedTo: e.target.value || null,
                          })
                        }
                        style={{ flex: 1, padding: "6px 10px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)" }}
                      >
                        <option value="">-- Unassigned --</option>
                        {users?.map((u) => (
                          <option key={u.id} value={u.id}>{u.name} ({u.role})</option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <div style={{ fontSize: "12px", color: "var(--text-primary)" }}>
                      {users?.find((u) => u.id === selectedIncidentDetail.incident.assigned_to)?.name || selectedIncidentDetail.incident.assigned_to || "Unassigned"}
                    </div>
                  )}
                </div>

                {/* Linked Alerts */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                    <h4 style={{ fontSize: "13px", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                      Linked Alerts ({selectedIncidentDetail.linked_alerts.length})
                    </h4>
                  </div>

                  {selectedIncidentDetail.linked_alerts.length === 0 ? (
                    <div style={{ fontSize: "12px", color: "var(--text-muted)", fontStyle: "italic", marginBottom: "10px" }}>
                      No alerts linked to this incident yet.
                    </div>
                  ) : (
                    <div style={{ display: "grid", gap: "8px", marginBottom: "12px" }}>
                      {selectedIncidentDetail.linked_alerts.map((al) => (
                        <div
                          key={al.alert_id}
                          style={{
                            border: "1px solid var(--border)",
                            borderRadius: "4px",
                            padding: "8px 10px",
                            fontSize: "12px",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                          }}
                        >
                          <div>
                            <div style={{ fontWeight: 600 }}>{al.title || `Alert ${al.alert_id}`}</div>
                            <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                              {al.source_uc?.toUpperCase()} • Severity: {al.severity}
                            </div>
                          </div>
                          {canOperate && (
                            <button
                              type="button"
                              onClick={() =>
                                unlinkAlertMutation.mutate({
                                  incidentId: selectedIncidentDetail.incident.id,
                                  alertId: al.alert_id,
                                })
                              }
                              style={{
                                background: "none",
                                border: "none",
                                color: "var(--danger)",
                                fontSize: "11px",
                                cursor: "pointer",
                                fontWeight: 600,
                              }}
                            >
                              Unlink
                            </button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Link alert input */}
                  {canOperate && (
                    <div style={{ display: "flex", gap: "6px" }}>
                      <input
                        type="text"
                        placeholder="Paste Alert ID to link..."
                        value={alertIdToLink}
                        onChange={(e) => setAlertIdToLink(e.target.value)}
                        style={{ flex: 1, padding: "6px 8px", fontSize: "12px", borderRadius: "4px", border: "1px solid var(--border)" }}
                      />
                      <button
                        type="button"
                        disabled={!alertIdToLink || linkAlertMutation.isPending}
                        onClick={() =>
                          linkAlertMutation.mutate({
                            incidentId: selectedIncidentDetail.incident.id,
                            alertId: alertIdToLink,
                          })
                        }
                        style={{
                          background: "var(--primary)",
                          color: "#fff",
                          border: "none",
                          borderRadius: "4px",
                          padding: "6px 10px",
                          fontSize: "12px",
                          fontWeight: 600,
                          cursor: "pointer",
                        }}
                      >
                        Link
                      </button>
                    </div>
                  )}
                </div>

                {/* Timeline */}
                <div>
                  <h4 style={{ fontSize: "13px", fontWeight: 700, marginBottom: "8px", color: "var(--text-primary)" }}>Activity & Audit Timeline</h4>
                  <div style={{ borderLeft: "2px solid var(--border)", paddingLeft: "12px", display: "grid", gap: "10px" }}>
                    {selectedIncidentDetail.timeline.map((entry, idx) => (
                      <div key={idx} style={{ fontSize: "11px" }}>
                        <div style={{ color: "var(--text-secondary)" }}>
                          {new Date(entry.timestamp).toLocaleString()} — <strong style={{ color: "var(--text-primary)" }}>{entry.action}</strong>
                        </div>
                        {entry.note && <div style={{ color: "var(--text-muted)", marginTop: "2px" }}>{entry.note}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            ) : (
              <LoadingState message="Loading incident details..." />
            )}
          </aside>
        )}
      </div>

      {/* Create Incident Modal */}
      {isCreateModalOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.5)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "24px",
              width: "500px",
              maxWidth: "90vw",
              boxShadow: "0 10px 25px rgba(0,0,0,0.2)",
            }}
          >
            <h3 style={{ fontSize: "18px", fontWeight: 700, marginBottom: "16px", color: "var(--text-primary)" }}>
              Create New Incident
            </h3>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                createMutation.mutate({
                  ...createForm,
                  organization_id: activeOrgId,
                });
              }}
              style={{ display: "grid", gap: "14px" }}
            >
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>Title *</label>
                <input
                  type="text"
                  required
                  value={createForm.title}
                  onChange={(e) => setCreateForm({ ...createForm, title: e.target.value })}
                  style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", fontSize: "13px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>Description</label>
                <textarea
                  rows={3}
                  value={createForm.description}
                  onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                  style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", fontSize: "13px" }}
                />
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>Severity</label>
                  <select
                    value={createForm.severity}
                    onChange={(e) => setCreateForm({ ...createForm, severity: e.target.value })}
                    style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", fontSize: "13px" }}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>Source Type</label>
                  <select
                    value={createForm.source_type}
                    onChange={(e) => setCreateForm({ ...createForm, source_type: e.target.value })}
                    style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", fontSize: "13px" }}
                  >
                    <option value="manual">Manual</option>
                    <option value="alert">Alert</option>
                  </select>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>Site</label>
                  <select
                    value={createForm.site_id}
                    onChange={(e) => setCreateForm({ ...createForm, site_id: e.target.value })}
                    style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", fontSize: "13px" }}
                  >
                    <option value="">-- Unspecified --</option>
                    {sites?.map((s) => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>Camera</label>
                  <select
                    value={createForm.camera_id}
                    onChange={(e) => setCreateForm({ ...createForm, camera_id: e.target.value })}
                    style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", fontSize: "13px" }}
                  >
                    <option value="">-- Unspecified --</option>
                    {cameras?.map((c) => (
                      <option key={c.id} value={c.id}>{c.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, marginBottom: "4px" }}>Assigned User</label>
                <select
                  value={createForm.assigned_to}
                  onChange={(e) => setCreateForm({ ...createForm, assigned_to: e.target.value })}
                  style={{ width: "100%", padding: "8px", borderRadius: "4px", border: "1px solid var(--border)", fontSize: "13px" }}
                >
                  <option value="">-- Unassigned --</option>
                  {users?.map((u) => (
                    <option key={u.id} value={u.id}>{u.name} ({u.role})</option>
                  ))}
                </select>
              </div>

              {createForm.alert_ids.length > 0 && (
                <div style={{ fontSize: "12px", color: "var(--primary)", background: "var(--surface-hover)", padding: "8px", borderRadius: "4px" }}>
                  Pre-associated Alert ID: <strong>{createForm.alert_ids.join(", ")}</strong>
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "12px" }}>
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  style={{ padding: "8px 16px", borderRadius: "4px", border: "1px solid var(--border)", background: "none", cursor: "pointer", fontSize: "13px" }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending}
                  style={{ padding: "8px 16px", borderRadius: "4px", border: "none", background: "var(--primary)", color: "#fff", cursor: "pointer", fontWeight: 600, fontSize: "13px" }}
                >
                  {createMutation.isPending ? "Creating..." : "Create Incident"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}

export default Incidents;