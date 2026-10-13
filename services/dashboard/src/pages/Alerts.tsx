import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import AlertList from "@/components/alerts/AlertList";
import { PageHeader } from "@/components/common/PageHeader";
import { getPendingAlertsCount, type AlertFilters } from "@/api/alerts";
import { getAllUCModules, getUCBadgeStyle } from "@/modules/registry";

export default function Alerts() {
  const [filters, setFilters] = useState<AlertFilters>({});

  const allModules = getAllUCModules();

  const { data: pendingCount = 0 } = useQuery({
    queryKey: ["alerts-pending-count"],
    queryFn: getPendingAlertsCount,
    refetchInterval: 10000,
  });

  const updateFilter = (
    key: keyof AlertFilters,
    value: string,
  ) => {
    setFilters((current) => ({
      ...current,
      [key]: value || undefined,
    }));
  };

  const clearFilters = () => {
    setFilters({});
  };

  const hasFilters = Object.values(filters).some(Boolean);

  return (
    <main className="page alerts-page">
      <PageHeader
        title="Alert Center"
        description="Real-time incident and anomaly alerts across all integrated video analytics pipelines."
        badges={
          <span
            style={{
              padding: "4px 10px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 700,
              backgroundColor: pendingCount > 0 ? "rgba(245, 158, 11, 0.18)" : "rgba(34, 197, 94, 0.18)",
              color: pendingCount > 0 ? "#fbbf24" : "#4ade80",
              border: `1px solid ${pendingCount > 0 ? "rgba(245, 158, 11, 0.4)" : "rgba(34, 197, 94, 0.4)"}`,
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span>🔔</span>
            <span>{pendingCount} Pending Action</span>
          </span>
        }
      />

      {/* UC Tabs (Dynamically driven by registry) */}
      <div
        className="uc-tabs-bar"
        style={{
          display: "flex",
          gap: "8px",
          borderBottom: "1px solid var(--border, #292d36)",
          paddingBottom: "12px",
          marginBottom: "18px",
          overflowX: "auto",
        }}
      >
        <button
          type="button"
          onClick={() => updateFilter("ucId", "")}
          style={{
            padding: "8px 16px",
            borderRadius: "6px",
            fontSize: "13px",
            fontWeight: 600,
            border: !filters.ucId ? "1px solid var(--primary, #A646BD)" : "1px solid var(--border, #292d36)",
            backgroundColor: !filters.ucId ? "var(--primary-bg, rgba(166, 70, 189, 0.12))" : "var(--surface, #15171e)",
            color: !filters.ucId ? "var(--text-primary, #f1f3f5)" : "var(--text-secondary, #a2a8b5)",
            cursor: "pointer",
          }}
        >
          All Use Cases
        </button>

        {allModules.map((module) => {
          const isSelected = filters.ucId === module.id;
          const style = getUCBadgeStyle(module.id);
          return (
            <button
              key={module.id}
              type="button"
              onClick={() => updateFilter("ucId", module.id)}
              style={{
                padding: "8px 16px",
                borderRadius: "6px",
                fontSize: "13px",
                fontWeight: 600,
                border: isSelected ? `1px solid ${module.color}` : "1px solid var(--border, #292d36)",
                backgroundColor: isSelected ? style.backgroundColor : "var(--surface, #15171e)",
                color: isSelected ? module.color : "var(--text-secondary, #a2a8b5)",
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                cursor: "pointer",
              }}
            >
              <span>{module.icon}</span>
              <span>{module.shortName}</span>
            </button>
          );
        })}
      </div>

      {/* Secondary Filter Bar */}
      <section
        className="alert-filters"
        aria-label="Alert filters"
        style={{
          display: "flex",
          gap: "12px",
          alignItems: "flex-end",
          flexWrap: "wrap",
          padding: "16px",
          borderRadius: "10px",
          backgroundColor: "var(--surface, #15171e)",
          border: "1px solid var(--border, #292d36)",
          marginBottom: "20px",
        }}
      >
        <div className="filter-field" style={{ minWidth: "160px" }}>
          <label htmlFor="severity-filter" style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "4px", textTransform: "uppercase" }}>
            Severity
          </label>
          <select
            id="severity-filter"
            value={filters.severity ?? ""}
            onChange={(e) => updateFilter("severity", e.target.value)}
            style={{
              width: "100%",
              padding: "7px 10px",
              borderRadius: "6px",
              backgroundColor: "var(--bg, #0f1117)",
              border: "1px solid var(--border, #292d36)",
              color: "var(--text-primary, #f1f3f5)",
              fontSize: "12px",
            }}
          >
            <option value="">All Severities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>

        <div className="filter-field" style={{ minWidth: "160px" }}>
          <label htmlFor="status-filter" style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "4px", textTransform: "uppercase" }}>
            Status
          </label>
          <select
            id="status-filter"
            value={filters.status ?? ""}
            onChange={(e) => updateFilter("status", e.target.value)}
            style={{
              width: "100%",
              padding: "7px 10px",
              borderRadius: "6px",
              backgroundColor: "var(--bg, #0f1117)",
              border: "1px solid var(--border, #292d36)",
              color: "var(--text-primary, #f1f3f5)",
              fontSize: "12px",
            }}
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        <div className="filter-field" style={{ minWidth: "200px" }}>
          <label htmlFor="camera-filter" style={{ display: "block", fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", marginBottom: "4px", textTransform: "uppercase" }}>
            Camera ID
          </label>
          <input
            id="camera-filter"
            type="text"
            placeholder="Search camera UUID..."
            value={filters.cameraId ?? ""}
            onChange={(e) => updateFilter("cameraId", e.target.value)}
            style={{
              width: "100%",
              padding: "7px 10px",
              borderRadius: "6px",
              backgroundColor: "var(--bg, #0f1117)",
              border: "1px solid var(--border, #292d36)",
              color: "var(--text-primary, #f1f3f5)",
              fontSize: "12px",
            }}
          />
        </div>

        {hasFilters && (
          <button
            type="button"
            className="clear-filters-button"
            onClick={clearFilters}
            style={{
              padding: "7px 14px",
              borderRadius: "6px",
              backgroundColor: "var(--surface-raised, #191c24)",
              border: "1px solid var(--border, #292d36)",
              color: "var(--text-secondary, #a2a8b5)",
              fontSize: "12px",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Clear Filters
          </button>
        )}
      </section>

      {/* Alert List */}
      <section className="alerts-feed-container">
        <AlertList filters={filters} />
      </section>
    </main>
  );
}