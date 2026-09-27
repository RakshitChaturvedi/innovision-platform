import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  acknowledgeAlert,
  getAlerts,
  resolveAlert,
  type AlertFilters,
} from "@/api/alerts";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";

interface AlertListProps {
  filters: AlertFilters;
}

function getSeverityLabel(
  severity: string,
) {
  return severity.charAt(0).toUpperCase() +
    severity.slice(1);
}

function getStatusLabel(status: string) {
  return status
    .split("_")
    .map(
      (part) =>
        part.charAt(0).toUpperCase() +
        part.slice(1),
    )
    .join(" ");
}

function formatCameraId(
  cameraId: string | null,
) {
  if (!cameraId) {
    return "Unknown camera";
  }

  return `Camera ${cameraId.slice(-4)}`;
}

function formatTimestamp(
  timestamp: string,
) {
  return new Date(timestamp).toLocaleString(
    undefined,
    {
      dateStyle: "medium",
      timeStyle: "short",
    },
  );
}

export default function AlertList({
  filters,
}: AlertListProps) {
  const {
    data,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["alerts", filters],
    queryFn: () => getAlerts(filters),
  });

  const queryClient = useQueryClient();

  const acknowledgeMutation = useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["alerts"],
      });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: resolveAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["alerts"],
      });
    },
  });

  if (isLoading) {
    return <LoadingState message="Loading alerts..." />;
  }

  if (isError) {
    return (
      <ErrorState message="Failed to load alerts." />
    );
  }

  if (!data || data.length === 0) {
    return (
      <EmptyState message="No alerts match the current filters." />
    );
  }

  return (
    <div className="alert-list">
      {data.map((alert) => (
        <article
          key={alert.id}
          className="alert-row"
        >
          <div
            className={`alert-severity-marker severity-${alert.severity}`}
            aria-hidden="true"
          />

          <div className="alert-main">
            <div className="alert-heading">
              <h3>{alert.title}</h3>

              <span
                className={`severity-badge severity-${alert.severity}`}
              >
                {getSeverityLabel(alert.severity)}
              </span>
            </div>

            <div className="alert-meta">
              <span>
                {formatCameraId(alert.camera_id)}
              </span>

              <span className="meta-divider" />

              <span>
                {alert.source_uc.toUpperCase()}
              </span>

              <span className="meta-divider" />

              <time dateTime={alert.created_at}>
                {formatTimestamp(alert.created_at)}
              </time>
            </div>
          </div>

          <div className="alert-actions">
            <span
              className={`alert-status status-${alert.status}`}
            >
              {getStatusLabel(alert.status)}
            </span>

            {alert.status === "pending" && (
              <button
                type="button"
                className="alert-action-button"
                disabled={acknowledgeMutation.isPending}
                onClick={() =>
                  acknowledgeMutation.mutate(alert.alert_id)
                }
              >
                Acknowledge
              </button>
            )}

            {(alert.status === "acknowledged" ||
              alert.status === "in_progress") && (
              <button
                type="button"
                className="alert-action-button"
                disabled={resolveMutation.isPending}
                onClick={() =>
                  resolveMutation.mutate(alert.alert_id)
                }
              >
                Resolve
              </button>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}