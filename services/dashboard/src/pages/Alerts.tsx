import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import AlertList from "@/components/alerts/AlertList";
import { getAnalyticsCatalog } from "@/api/platform";
import type { AlertFilters } from "@/api/alerts";
import type { Alert } from "@/types/alert";

export default function Alerts() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState<AlertFilters>({});

  const { data: catalog } = useQuery({
    queryKey: ["analyticsCatalog"],
    queryFn: getAnalyticsCatalog,
  });

  const handleCreateIncident = (alert: Alert) => {
    navigate("/incidents", { state: { createForAlert: alert } });
  };

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
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Alerts & Incidents</h1>
          <p className="page-description">
            Monitor and manage real-time platform security, safety, and operational alerts.
          </p>
        </div>
      </header>

      <section className="alert-filters" aria-label="Alert filters">
        <div className="filter-field">
          <label htmlFor="camera-filter">Camera</label>
          <input
            id="camera-filter"
            type="text"
            placeholder="Camera ID"
            value={filters.cameraId ?? ""}
            onChange={(event) => updateFilter("cameraId", event.target.value)}
          />
        </div>

        <div className="filter-field">
          <label htmlFor="uc-filter">Analytic Capability</label>
          <select
            id="uc-filter"
            value={filters.ucId ?? ""}
            onChange={(event) => updateFilter("ucId", event.target.value)}
          >
            <option value="">All Analytic Capabilities</option>
            {catalog && catalog.length > 0 ? (
              catalog.map((item) => (
                <option key={item.id} value={item.internal_code}>
                  {item.internal_code.toUpperCase()} — {item.display_name}
                </option>
              ))
            ) : (
              <>
                <option value="uc1">UC1 — Intrusion & Perimeter</option>
                <option value="uc2">UC2 — Fire & Smoke</option>
                <option value="uc3">UC3 — PPE Detection</option>
                <option value="uc4">UC4 — ANPR & Speed</option>
              </>
            )}
          </select>
        </div>

        <div className="filter-field">
          <label htmlFor="severity-filter">Severity</label>
          <select
            id="severity-filter"
            value={filters.severity ?? ""}
            onChange={(event) => updateFilter("severity", event.target.value)}
          >
            <option value="">All Severities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>

        <div className="filter-field">
          <label htmlFor="status-filter">Status</label>
          <select
            id="status-filter"
            value={filters.status ?? ""}
            onChange={(event) => updateFilter("status", event.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="in_progress">In Progress</option>
            <option value="resolved">Resolved</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        {hasFilters && (
          <button
            type="button"
            className="clear-filters-button"
            onClick={clearFilters}
          >
            Clear Filters
          </button>
        )}
      </section>

      <section className="alerts-section" aria-label="Alert results">
        <div className="section-header">
          <div>
            <h2 className="section-title">Alert Feed</h2>
            <p className="section-description">
              Real-time platform alerts received from active analytics.
            </p>
          </div>
        </div>

        <AlertList filters={filters} onCreateIncident={handleCreateIncident} />
      </section>
    </main>
  );
}