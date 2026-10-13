import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { incidentClient } from "@/api/client";
import { PageHeader } from "@/components/common/PageHeader";
import { DataTable, type Column } from "@/components/common/DataTable";
import { Badge } from "@/components/common/Badge";
import { StatCard } from "@/components/common/StatCard";

export interface Incident {
  id: string;
  title?: string;
  status: "active" | "acknowledged" | "in_progress" | "resolved" | "closed";
  severity?: string;
  created_at: string;
  updated_at?: string;
  assigned_to?: string | null;
  description?: string;
}

async function fetchIncidents(status?: string): Promise<Incident[]> {
  try {
    const { data } = await incidentClient.get<Incident[]>("/incidents", {
      params: status ? { status } : undefined,
    });
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export function Incidents() {
  const [selectedStatus, setSelectedStatus] = useState<string>("all");

  const { data: incidents = [], isLoading } = useQuery({
    queryKey: ["incidents", selectedStatus],
    queryFn: () => fetchIncidents(selectedStatus === "all" ? undefined : selectedStatus),
    refetchInterval: 15000,
  });

  const activeCount = incidents.filter((i) => i.status === "active").length;
  const inProgressCount = incidents.filter((i) => i.status === "in_progress" || i.status === "acknowledged").length;
  const resolvedCount = incidents.filter((i) => i.status === "resolved" || i.status === "closed").length;

  const columns: Column<Incident>[] = [
    {
      key: "id",
      header: "Incident ID",
      width: "160px",
      render: (row) => (
        <span style={{ fontFamily: "var(--mono, monospace)", fontSize: "12px", color: "var(--primary, #A646BD)" }}>
          {row.id.slice(0, 8)}...{row.id.slice(-4)}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      width: "140px",
      render: (row) => <Badge variant="status" status={row.status} />,
    },
    {
      key: "title",
      header: "Title / Summary",
      render: (row) => (
        <div>
          <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
            {row.title || `Incident #${row.id.slice(0, 8)}`}
          </div>
          {row.description && (
            <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "2px" }}>
              {row.description}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "assigned_to",
      header: "Assigned To",
      width: "160px",
      render: (row) => (
        <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
          {row.assigned_to ? `Operator #${row.assigned_to.slice(0, 6)}` : "Unassigned"}
        </span>
      ),
    },
    {
      key: "created_at",
      header: "Created At",
      width: "180px",
      render: (row) => (
        <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>
          {new Date(row.created_at).toLocaleString(undefined, {
            dateStyle: "short",
            timeStyle: "short",
          })}
        </span>
      ),
    },
  ];

  return (
    <main className="page incidents-page">
      <PageHeader
        title="Incident Manager"
        description="Track escalated security and hazard incident tickets across operational facilities."
        badges={
          <Badge variant="status" status={activeCount > 0 ? "active" : "resolved"}>
            {activeCount} Active Incidents
          </Badge>
        }
      />

      <section className="stats-grid" style={{ marginBottom: "24px" }}>
        <StatCard
          title="Active Escalations"
          value={activeCount}
          subtitle="Requiring immediate dispatch"
          icon="🚨"
          color="#ef4444"
        />
        <StatCard
          title="In Progress"
          value={inProgressCount}
          subtitle="Under operator investigation"
          icon="⏳"
          color="#f59e0b"
        />
        <StatCard
          title="Resolved"
          value={resolvedCount}
          subtitle="Closed tickets"
          icon="✅"
          color="#4ade80"
        />
      </section>

      {/* Filter Tabs */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          marginBottom: "16px",
          borderBottom: "1px solid var(--border, #292d36)",
          paddingBottom: "12px",
        }}
      >
        {["all", "active", "in_progress", "resolved"].map((st) => (
          <button
            key={st}
            type="button"
            onClick={() => setSelectedStatus(st)}
            style={{
              padding: "6px 14px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 600,
              border: selectedStatus === st ? "1px solid var(--primary, #A646BD)" : "1px solid var(--border, #292d36)",
              backgroundColor: selectedStatus === st ? "var(--primary-bg, rgba(166, 70, 189, 0.12))" : "transparent",
              color: selectedStatus === st ? "var(--text-primary, #f1f3f5)" : "var(--text-secondary, #a2a8b5)",
              textTransform: "capitalize",
              cursor: "pointer",
            }}
          >
            {st === "all" ? "All Incidents" : st.replace("_", " ")}
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        data={incidents}
        keyExtractor={(item) => item.id}
        isLoading={isLoading}
        emptyMessage="No incidents found for the selected status filter."
      />
    </main>
  );
}
export default Incidents;