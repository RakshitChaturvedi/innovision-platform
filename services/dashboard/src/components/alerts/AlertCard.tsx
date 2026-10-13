import { useState } from "react";
import type { Alert } from "@/types/alert";
import { Badge } from "@/components/common/Badge";

interface AlertCardProps {
  alert: Alert;
  onAcknowledge?: (alertId: string) => void;
  onResolve?: (alertId: string) => void;
  isAcknowledging?: boolean;
  isResolving?: boolean;
}

function getRelativeTime(timestamp: string): string {
  try {
    const diffMs = Date.now() - new Date(timestamp).getTime();
    const diffSec = Math.floor(diffMs / 1000);
    if (diffSec < 10) return "Just now";
    if (diffSec < 60) return `${diffSec}s ago`;
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDays = Math.floor(diffHr / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return new Date(timestamp).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return timestamp;
  }
}

function formatFullTimestamp(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "medium",
    });
  } catch {
    return timestamp;
  }
}

function formatCameraId(cameraId: string | null): string {
  if (!cameraId) return "Unknown Camera";
  return `Camera ${cameraId.slice(0, 8)}...${cameraId.slice(-4)}`;
}

export default function AlertCard({
  alert,
  onAcknowledge,
  onResolve,
  isAcknowledging = false,
  isResolving = false,
}: AlertCardProps) {
  const [showMetadata, setShowMetadata] = useState(false);
  const metadataEntries = Object.entries(alert.metadata || {});

  return (
    <article
      className="alert-card-row"
      style={{
        background: "var(--surface, #15171e)",
        border: "1px solid var(--border, #292d36)",
        borderRadius: "10px",
        padding: "16px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        transition: "border-color 0.15s, background-color 0.15s",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: "12px",
          flexWrap: "wrap",
        }}
      >
        {/* Left Title and Badges */}
        <div style={{ display: "flex", flexDirection: "column", gap: "6px", flex: 1, minWidth: "260px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
            <Badge variant="severity" severity={alert.severity} />
            <Badge variant="uc" ucId={alert.source_uc} />
            <Badge variant="status" status={alert.status} />

            <span
              style={{
                fontSize: "11px",
                fontFamily: "var(--mono, monospace)",
                color: "var(--text-muted, #707786)",
                padding: "2px 6px",
                borderRadius: "4px",
                backgroundColor: "var(--surface-raised, #191c24)",
                border: "1px solid var(--border, #292d36)",
              }}
            >
              {alert.alert_type}
            </span>
          </div>

          <h3
            style={{
              fontSize: "15px",
              fontWeight: 600,
              color: "var(--text-primary, #f1f3f5)",
              margin: 0,
            }}
          >
            {alert.title}
          </h3>

          <p
            style={{
              fontSize: "13px",
              color: "var(--text-secondary, #a2a8b5)",
              margin: 0,
              lineHeight: 1.45,
            }}
          >
            {alert.description}
          </p>

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              fontSize: "12px",
              color: "var(--text-muted, #707786)",
              marginTop: "2px",
              flexWrap: "wrap",
            }}
          >
            <span>📹 {formatCameraId(alert.camera_id)}</span>
            <span>•</span>
            <time
              dateTime={alert.created_at}
              title={formatFullTimestamp(alert.created_at)}
              style={{ cursor: "help" }}
            >
              🕒 {getRelativeTime(alert.created_at)} ({formatFullTimestamp(alert.created_at)})
            </time>
          </div>
        </div>

        {/* Right Actions & Snapshot Preview */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            gap: "10px",
          }}
        >
          {alert.frame_reference && (
            <div
              style={{
                width: "90px",
                height: "56px",
                borderRadius: "6px",
                overflow: "hidden",
                border: "1px solid var(--border, #292d36)",
                backgroundColor: "#000",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <img
                src={alert.frame_reference}
                alt="Alert Snapshot"
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
                onError={(e) => {
                  (e.currentTarget as HTMLElement).style.display = "none";
                }}
              />
            </div>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            {alert.status === "pending" && onAcknowledge && (
              <button
                type="button"
                disabled={isAcknowledging}
                onClick={() => onAcknowledge(alert.alert_id)}
                style={{
                  padding: "6px 12px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: 600,
                  backgroundColor: "rgba(59, 130, 246, 0.15)",
                  color: "#60a5fa",
                  border: "1px solid rgba(59, 130, 246, 0.4)",
                  cursor: isAcknowledging ? "not-allowed" : "pointer",
                  opacity: isAcknowledging ? 0.6 : 1,
                }}
              >
                {isAcknowledging ? "Acknowledging..." : "Acknowledge"}
              </button>
            )}

            {(alert.status === "acknowledged" || alert.status === "in_progress") &&
              onResolve && (
                <button
                  type="button"
                  disabled={isResolving}
                  onClick={() => onResolve(alert.alert_id)}
                  style={{
                    padding: "6px 12px",
                    borderRadius: "6px",
                    fontSize: "12px",
                    fontWeight: 600,
                    backgroundColor: "rgba(34, 197, 94, 0.15)",
                    color: "#4ade80",
                    border: "1px solid rgba(34, 197, 94, 0.4)",
                    cursor: isResolving ? "not-allowed" : "pointer",
                    opacity: isResolving ? 0.6 : 1,
                  }}
                >
                  {isResolving ? "Resolving..." : "Resolve"}
                </button>
              )}

            {metadataEntries.length > 0 && (
              <button
                type="button"
                onClick={() => setShowMetadata((prev) => !prev)}
                style={{
                  padding: "5px 10px",
                  borderRadius: "6px",
                  fontSize: "11px",
                  fontWeight: 500,
                  backgroundColor: "var(--surface-raised, #191c24)",
                  color: "var(--text-secondary, #a2a8b5)",
                  border: "1px solid var(--border, #292d36)",
                  cursor: "pointer",
                }}
              >
                {showMetadata ? "Hide Meta ▲" : `Meta (${metadataEntries.length}) ▼`}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Expandable Metadata Key-Values */}
      {showMetadata && metadataEntries.length > 0 && (
        <div
          style={{
            marginTop: "6px",
            padding: "12px",
            borderRadius: "6px",
            backgroundColor: "rgba(0, 0, 0, 0.35)",
            border: "1px solid var(--border, #292d36)",
            fontSize: "12px",
            fontFamily: "var(--mono, monospace)",
          }}
        >
          <div style={{ fontWeight: 600, color: "var(--text-muted, #707786)", marginBottom: "8px", fontSize: "11px", textTransform: "uppercase" }}>
            Alert Payload Metadata
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
              gap: "8px",
            }}
          >
            {metadataEntries.map(([key, val]) => (
              <div
                key={key}
                style={{
                  display: "flex",
                  gap: "8px",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  backgroundColor: "var(--surface-raised, #191c24)",
                  overflow: "hidden",
                }}
              >
                <span style={{ color: "var(--text-secondary, #a2a8b5)", fontWeight: 500 }}>
                  {key}:
                </span>
                <span
                  style={{
                    color: "var(--text-primary, #f1f3f5)",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                  title={typeof val === "object" ? JSON.stringify(val) : String(val)}
                >
                  {typeof val === "object" ? JSON.stringify(val) : String(val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
