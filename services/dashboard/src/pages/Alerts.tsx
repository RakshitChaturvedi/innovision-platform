import { useState } from "react";

import AlertList from "@/components/alerts/AlertList";

import type { AlertFilters } from "@/api/alerts";

export default function Alerts() {
  const [filters, setFilters] = useState<AlertFilters>({});

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

  const hasFilters = Object.values(filters).some(
    Boolean,
  );

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Alerts</h1>

          <p className="page-description">
            Monitor and manage platform alerts.
          </p>
        </div>
      </header>

      <section
        className="alert-filters"
        aria-label="Alert filters"
      >
        <div className="filter-field">
          <label htmlFor="camera-filter">
            Camera
          </label>

          <input
            id="camera-filter"
            type="text"
            placeholder="Camera ID"
            value={filters.cameraId ?? ""}
            onChange={(event) =>
              updateFilter(
                "cameraId",
                event.target.value,
              )
            }
          />
        </div>

        <div className="filter-field">
          <label htmlFor="uc-filter">
            Use Case
          </label>

          <select
            id="uc-filter"
            value={filters.ucId ?? ""}
            onChange={(event) =>
              updateFilter(
                "ucId",
                event.target.value,
              )
            }
          >
            <option value="">All use cases</option>
            <option value="uc1">UC1</option>
            <option value="uc2">UC2</option>
            <option value="uc3">UC3</option>
            <option value="uc4">UC4</option>
          </select>
        </div>

        <div className="filter-field">
          <label htmlFor="severity-filter">
            Severity
          </label>

          <select
            id="severity-filter"
            value={filters.severity ?? ""}
            onChange={(event) =>
              updateFilter(
                "severity",
                event.target.value,
              )
            }
          >
            <option value="">All severities</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
        </div>

        <div className="filter-field">
          <label htmlFor="status-filter">
            Status
          </label>

          <select
            id="status-filter"
            value={filters.status ?? ""}
            onChange={(event) =>
              updateFilter(
                "status",
                event.target.value,
              )
            }
          >
            <option value="">All statuses</option>
            <option value="pending">Pending</option>
            <option value="acknowledged">
              Acknowledged
            </option>
            <option value="in_progress">
              In Progress
            </option>
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
            Clear
          </button>
        )}
      </section>

      <section
        className="alerts-section"
        aria-label="Alert results"
      >
        <div className="section-header">
          <div>
            <h2 className="section-title">
              Alert Feed
            </h2>

            <p className="section-description">
              Platform alerts received from analytics.
            </p>
          </div>
        </div>

        <AlertList filters={filters} />
      </section>
    </main>
  );
}