import { useEffect, useState, useTransition } from "react";
import { fetchAuditLogs, type AuditLogItem, type AuditQueryParams } from "../api/audit";

export function AuditLogPage() {
  const [items, setItems] = useState<AuditLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [search, setSearch] = useState("");
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  // Drawer modal state
  const [selectedLog, setSelectedLog] = useState<AuditLogItem | null>(null);

  const [, startTransition] = useTransition();

  useEffect(() => {
    let isMounted = true;

    const params: AuditQueryParams = {
      page,
      page_size: pageSize,
    };
    if (search.trim()) params.search = search.trim();
    if (action) params.action = action;
    if (resourceType) params.resource_type = resourceType;
    if (startDate) params.start_date = new Date(startDate).toISOString();
    if (endDate) params.end_date = new Date(`${endDate}T23:59:59`).toISOString();

    fetchAuditLogs(params)
      .then((res) => {
        if (isMounted) {
          setItems(res.items);
          setTotal(res.total);
          setTotalPages(res.total_pages);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          const errorObj = err as { response?: { data?: { detail?: string } } };
          setError(errorObj?.response?.data?.detail || "Failed to load audit logs from enterprise audit service.");
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [page, pageSize, action, resourceType, search, startDate, endDate]);

  const handleApplySearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
  };

  const handleResetFilters = () => {
    startTransition(() => {
      setSearch("");
      setAction("");
      setResourceType("");
      setStartDate("");
      setEndDate("");
      setPage(1);
    });
  };

  const formatDate = (isoStr: string) => {
    try {
      const d = new Date(isoStr);
      return d.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoStr;
    }
  };

  const getActionBadgeColor = (act: string) => {
    if (act.includes("created") || act.includes("login")) return "var(--success)";
    if (act.includes("updated") || act.includes("assigned") || act.includes("changed")) return "var(--accent)";
    if (act.includes("deleted") || act.includes("disabled") || act.includes("logout")) return "var(--warning)";
    return "var(--text-secondary)";
  };

  return (
    <div className="page" style={{ padding: "24px" }}>
      <header className="page-header" style={{ marginBottom: "24px" }}>
        <div>
          <h1 className="page-title" style={{ margin: 0, fontSize: "24px", fontWeight: 600 }}>
            Enterprise Audit Log
          </h1>
          <p className="page-description" style={{ margin: "4px 0 0 0", color: "var(--text-secondary)", fontSize: "14px" }}>
            Append-only governance, security, and administrative system audit trail.
          </p>
        </div>
      </header>

      {/* Filter Toolbar */}
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "20px",
        }}
      >
        <form onSubmit={handleApplySearch} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "12px", alignItems: "center" }}>
            {/* Search Input */}
            <div style={{ flex: "1 1 240px" }}>
              <input
                type="text"
                placeholder="Search action, user, resource ID, metadata..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "var(--background)",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                }}
              />
            </div>

            {/* Action Filter */}
            <div style={{ minWidth: "160px" }}>
              <select
                value={action}
                onChange={(e) => {
                  setAction(e.target.value);
                  setPage(1);
                }}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "var(--background)",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                }}
              >
                <option value="">All Actions</option>
                <option value="user_login">User Login</option>
                <option value="user_created">User Created</option>
                <option value="user_updated">User Updated</option>
                <option value="organization_updated">Organization Updated</option>
                <option value="site_created">Site Created</option>
                <option value="zone_created">Zone Created</option>
                <option value="zone_analytics_changed">Zone Analytics Changed</option>
                <option value="camera_created">Camera Created</option>
                <option value="camera_assigned">Camera Assigned</option>
                <option value="camera_disabled">Camera Disabled</option>
                <option value="camera_enabled">Camera Enabled</option>
                <option value="subscription_updated">Subscription Updated</option>
                <option value="incident_created">Incident Created</option>
                <option value="incident_status_changed">Incident Status Changed</option>
              </select>
            </div>

            {/* Resource Type Filter */}
            <div style={{ minWidth: "160px" }}>
              <select
                value={resourceType}
                onChange={(e) => {
                  setResourceType(e.target.value);
                  setPage(1);
                }}
                style={{
                  width: "100%",
                  padding: "8px 12px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "var(--background)",
                  color: "var(--text-primary)",
                  fontSize: "14px",
                }}
              >
                <option value="">All Resource Types</option>
                <option value="user">User</option>
                <option value="organization">Organization</option>
                <option value="site">Site</option>
                <option value="zone">Zone</option>
                <option value="camera">Camera</option>
                <option value="subscription">Subscription</option>
                <option value="incident">Incident</option>
              </select>
            </div>

            {/* Date Pickers */}
            <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                title="Start Date"
                style={{
                  padding: "7px 10px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "var(--background)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                }}
              />
              <span style={{ color: "var(--text-muted)", fontSize: "12px" }}>to</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                title="End Date"
                style={{
                  padding: "7px 10px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "var(--background)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                }}
              />
            </div>

            {/* Buttons */}
            <button
              type="submit"
              className="btn btn-primary"
              style={{
                padding: "8px 16px",
                borderRadius: "6px",
                fontSize: "13px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              Filter
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleResetFilters}
              style={{
                padding: "8px 14px",
                borderRadius: "6px",
                fontSize: "13px",
                cursor: "pointer",
              }}
            >
              Reset
            </button>
          </div>
        </form>
      </div>

      {/* Error Message */}
      {error && (
        <div
          style={{
            padding: "12px 16px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "6px",
            color: "#ef4444",
            marginBottom: "16px",
            fontSize: "14px",
          }}
        >
          {error}
        </div>
      )}

      {/* Main Audit Table */}
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          overflow: "hidden",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
          <thead>
            <tr style={{ background: "var(--surface-hover)", borderBottom: "1px solid var(--border)" }}>
              <th style={{ padding: "12px 16px", fontWeight: 600, color: "var(--text-secondary)" }}>Timestamp</th>
              <th style={{ padding: "12px 16px", fontWeight: 600, color: "var(--text-secondary)" }}>Actor</th>
              <th style={{ padding: "12px 16px", fontWeight: 600, color: "var(--text-secondary)" }}>Action</th>
              <th style={{ padding: "12px 16px", fontWeight: 600, color: "var(--text-secondary)" }}>Resource</th>
              <th style={{ padding: "12px 16px", fontWeight: 600, color: "var(--text-secondary)" }}>Description</th>
              <th style={{ padding: "12px 16px", fontWeight: 600, color: "var(--text-secondary)", textAlign: "right" }}>
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)" }}>
                  Loading audit logs...
                </td>
              </tr>
            ) : items.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
                  No audit log entries match the selected criteria.
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr
                  key={item.id}
                  style={{
                    borderBottom: "1px solid var(--border)",
                    transition: "background 0.15s ease",
                  }}
                  className="table-row-hover"
                >
                  <td style={{ padding: "12px 16px", whiteSpace: "nowrap", color: "var(--text-secondary)" }}>
                    {formatDate(item.timestamp)}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ fontWeight: 500, color: "var(--text-primary)" }}>
                      {item.user_name || "System"}
                    </div>
                    {item.user_email && (
                      <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>{item.user_email}</div>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span
                      style={{
                        padding: "3px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.5px",
                        background: "rgba(255, 255, 255, 0.05)",
                        border: `1px solid ${getActionBadgeColor(item.action)}`,
                        color: getActionBadgeColor(item.action),
                      }}
                    >
                      {item.action.replace(/_/g, " ")}
                    </span>
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ fontWeight: 500, color: "var(--text-primary)" }}>{item.resource_type}</div>
                    <div style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "monospace" }}>
                      {item.resource_id.length > 18 ? `${item.resource_id.substring(0, 18)}...` : item.resource_id}
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--text-primary)", maxWidth: "320px" }}>
                    {item.description}
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "right" }}>
                    <button
                      className="btn btn-secondary"
                      onClick={() => setSelectedLog(item)}
                      style={{
                        padding: "4px 10px",
                        borderRadius: "4px",
                        fontSize: "12px",
                        cursor: "pointer",
                      }}
                    >
                      Inspect
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Pagination Bar */}
        <div
          style={{
            padding: "12px 16px",
            background: "var(--surface)",
            borderTop: "1px solid var(--border)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>
            Showing {items.length > 0 ? (page - 1) * pageSize + 1 : 0} to{" "}
            {Math.min(page * pageSize, total)} of {total} entries
          </div>

          <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
            <select
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              style={{
                padding: "4px 8px",
                borderRadius: "4px",
                border: "1px solid var(--border)",
                background: "var(--background)",
                color: "var(--text-primary)",
                fontSize: "12px",
              }}
            >
              <option value={20}>20 per page</option>
              <option value={50}>50 per page</option>
              <option value={100}>100 per page</option>
            </select>

            <button
              className="btn btn-secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              style={{ padding: "4px 10px", fontSize: "12px", cursor: page <= 1 ? "not-allowed" : "pointer" }}
            >
              Previous
            </button>
            <span style={{ fontSize: "13px", color: "var(--text-primary)", padding: "0 6px" }}>
              Page {page} of {totalPages}
            </span>
            <button
              className="btn btn-secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              style={{ padding: "4px 10px", fontSize: "12px", cursor: page >= totalPages ? "not-allowed" : "pointer" }}
            >
              Next
            </button>
          </div>
        </div>
      </div>

      {/* Audit Entry Slide-over Detail Modal */}
      {selectedLog && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0, 0, 0, 0.6)",
            backdropFilter: "blur(3px)",
            zIndex: 1000,
            display: "flex",
            justifyContent: "flex-end",
          }}
          onClick={() => setSelectedLog(null)}
        >
          <div
            style={{
              width: "100%",
              maxWidth: "540px",
              height: "100%",
              background: "var(--surface)",
              borderLeft: "1px solid var(--border)",
              boxShadow: "-8px 0 24px rgba(0, 0, 0, 0.4)",
              display: "flex",
              flexDirection: "column",
              padding: "24px",
              overflowY: "auto",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
              <h2 style={{ margin: 0, fontSize: "18px", fontWeight: 600 }}>Audit Event Details</h2>
              <button
                onClick={() => setSelectedLog(null)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--text-muted)",
                  fontSize: "20px",
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "16px", fontSize: "13px" }}>
              <div>
                <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Timestamp</label>
                <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                  {formatDate(selectedLog.timestamp)}
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Action</label>
                  <div style={{ fontWeight: 600, color: getActionBadgeColor(selectedLog.action), marginTop: "2px" }}>
                    {selectedLog.action}
                  </div>
                </div>

                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Service</label>
                  <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                    {selectedLog.service}
                  </div>
                </div>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Actor Name</label>
                  <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                    {selectedLog.user_name || "System"}
                  </div>
                </div>

                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Actor Role</label>
                  <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                    {selectedLog.actor_role || "system"}
                  </div>
                </div>
              </div>

              <div>
                <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Resource Type & ID</label>
                <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px", fontFamily: "monospace" }}>
                  {selectedLog.resource_type} ({selectedLog.resource_id})
                </div>
              </div>

              {selectedLog.organization_id && (
                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Organization ID</label>
                  <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px", fontFamily: "monospace" }}>
                    {selectedLog.organization_id}
                  </div>
                </div>
              )}

              <div>
                <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block" }}>Summary Description</label>
                <div style={{ color: "var(--text-primary)", marginTop: "2px" }}>{selectedLog.description}</div>
              </div>

              <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "8px 0" }} />

              <div>
                <label style={{ color: "var(--text-muted)", fontSize: "12px", display: "block", marginBottom: "6px" }}>
                  Event Metadata (JSON)
                </label>
                <pre
                  style={{
                    background: "var(--background)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    padding: "12px",
                    fontFamily: "monospace",
                    fontSize: "12px",
                    color: "var(--text-primary)",
                    overflowX: "auto",
                    margin: 0,
                  }}
                >
                  {JSON.stringify(selectedLog.metadata, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
