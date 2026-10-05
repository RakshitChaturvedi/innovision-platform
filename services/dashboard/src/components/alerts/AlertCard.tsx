import type { Alert } from "@/types/alert";

interface AlertCardProps {
  alert: Alert;
  onAcknowledge?: (alertId: string) => void;
  onResolve?: (alertId: string) => void;
  isAcknowledging?: boolean;
  isResolving?: boolean;
}

function getSeverityLabel(severity: string) {
  return severity.charAt(0).toUpperCase() + severity.slice(1);
}

function getStatusLabel(status: string) {
  return status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatCameraId(cameraId: string | null) {
  if (!cameraId) {
    return "Unknown camera";
  }

  return `Camera ${cameraId.slice(-4)}`;
}

function formatTimestamp(timestamp: string) {
  return new Date(timestamp).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function AlertCard({
  alert,
  onAcknowledge,
  onResolve,
  isAcknowledging = false,
  isResolving = false,
}: AlertCardProps) {
  const sourceUcNormalized = (alert.source_uc || "unknown").toLowerCase();

  return (
    <article className="alert-row">
      <div
        className={`alert-severity-marker severity-${alert.severity}`}
        aria-hidden="true"
      />

      <div className="alert-main">
        <div className="alert-heading">
          <h3>{alert.title}</h3>

          <span className={`severity-badge severity-${alert.severity}`}>
            {getSeverityLabel(alert.severity)}
          </span>
        </div>

        <div className="alert-meta">
          <span>{formatCameraId(alert.camera_id)}</span>

          <span className="meta-divider" />

          {/* Generic metadata-driven badge: driven purely by alert.source_uc without UC-specific branches */}
          <span className={`source-badge source-${sourceUcNormalized}`}>
            {alert.source_uc.toUpperCase()}
          </span>

          <span className="meta-divider" />

          <time dateTime={alert.created_at}>
            {formatTimestamp(alert.created_at)}
          </time>
        </div>
      </div>

      <div className="alert-actions">
        <span className={`alert-status status-${alert.status}`}>
          {getStatusLabel(alert.status)}
        </span>

        {alert.status === "pending" && onAcknowledge && (
          <button
            type="button"
            className="alert-action-button"
            disabled={isAcknowledging}
            onClick={() => onAcknowledge(alert.alert_id)}
          >
            Acknowledge
          </button>
        )}

        {(alert.status === "acknowledged" || alert.status === "in_progress") &&
          onResolve && (
            <button
              type="button"
              className="alert-action-button"
              disabled={isResolving}
              onClick={() => onResolve(alert.alert_id)}
            >
              Resolve
            </button>
          )}
      </div>
    </article>
  );
}
