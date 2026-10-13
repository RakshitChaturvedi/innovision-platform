import type { ReactNode } from "react";

interface EmptyStateProps {
  message?: string;
  icon?: ReactNode;
  action?: ReactNode;
}

export function EmptyState({
  message = "No data available.",
  icon = "📭",
  action,
}: EmptyStateProps) {
  return (
    <div
      className="empty-state"
      style={{
        padding: "36px 24px",
        borderRadius: "10px",
        backgroundColor: "var(--surface, #15171e)",
        border: "1px dashed var(--border, #292d36)",
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "10px",
      }}
    >
      <div style={{ fontSize: "28px", opacity: 0.8 }}>{icon}</div>
      <div style={{ fontSize: "14px", color: "var(--text-secondary, #a2a8b5)", maxWidth: "360px" }}>
        {message}
      </div>
      {action && <div style={{ marginTop: "8px" }}>{action}</div>}
    </div>
  );
}
export default EmptyState;