import type { CSSProperties, ReactNode } from "react";
import { getUCBadgeStyle, getUCModule } from "@/modules/registry";
import type { AlertSeverity, AlertStatus } from "@/types/alert";

export type BadgeVariant = "severity" | "status" | "uc" | "default";

interface BadgeProps {
  children?: ReactNode;
  variant?: BadgeVariant;
  severity?: AlertSeverity | string;
  status?: AlertStatus | string;
  ucId?: string;
  className?: string;
  style?: CSSProperties;
}

export function Badge({
  children,
  variant = "default",
  severity,
  status,
  ucId,
  className = "",
  style,
}: BadgeProps) {
  if (variant === "uc" && ucId) {
    const ucStyle = getUCBadgeStyle(ucId);
    const mod = getUCModule(ucId);
    const label = children ?? mod?.shortName ?? ucId.toUpperCase();

    return (
      <span
        className={`custom-badge uc-badge ${className}`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          padding: "2px 8px",
          borderRadius: "6px",
          fontSize: "11px",
          fontWeight: 600,
          letterSpacing: "0.02em",
          color: ucStyle.color,
          backgroundColor: ucStyle.backgroundColor,
          border: `1px solid ${ucStyle.borderColor}`,
          textTransform: "uppercase",
          ...style,
        }}
      >
        {mod?.icon && <span style={{ fontSize: "10px" }}>{mod.icon}</span>}
        {label}
      </span>
    );
  }

  if (variant === "severity" && severity) {
    const sev = severity.toLowerCase();
    const severityColors: Record<string, { bg: string; color: string; border: string }> = {
      critical: {
        bg: "rgba(239, 68, 68, 0.18)",
        color: "#f87171",
        border: "rgba(239, 68, 68, 0.4)",
      },
      high: {
        bg: "rgba(245, 158, 11, 0.18)",
        color: "#fbbf24",
        border: "rgba(245, 158, 11, 0.4)",
      },
      medium: {
        bg: "rgba(234, 179, 8, 0.15)",
        color: "#facc15",
        border: "rgba(234, 179, 8, 0.35)",
      },
      low: {
        bg: "rgba(148, 163, 184, 0.12)",
        color: "#94a3b8",
        border: "rgba(148, 163, 184, 0.25)",
      },
    };

    const scheme = severityColors[sev] ?? severityColors.low;
    const label = children ?? (sev.charAt(0).toUpperCase() + sev.slice(1));

    return (
      <span
        className={`custom-badge severity-badge severity-${sev} ${className}`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          padding: "2px 8px",
          borderRadius: "6px",
          fontSize: "11px",
          fontWeight: 600,
          color: scheme.color,
          backgroundColor: scheme.bg,
          border: `1px solid ${scheme.border}`,
          textTransform: "capitalize",
          ...style,
        }}
      >
        <span
          style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            backgroundColor: scheme.color,
          }}
        />
        {label}
      </span>
    );
  }

  if (variant === "status" && status) {
    const st = status.toLowerCase();
    const statusColors: Record<string, { bg: string; color: string; border: string }> = {
      pending: {
        bg: "rgba(245, 158, 11, 0.15)",
        color: "#fbbf24",
        border: "rgba(245, 158, 11, 0.35)",
      },
      acknowledged: {
        bg: "rgba(59, 130, 246, 0.15)",
        color: "#60a5fa",
        border: "rgba(59, 130, 246, 0.35)",
      },
      in_progress: {
        bg: "rgba(168, 85, 247, 0.15)",
        color: "#c084fc",
        border: "rgba(168, 85, 247, 0.35)",
      },
      resolved: {
        bg: "rgba(34, 197, 94, 0.15)",
        color: "#4ade80",
        border: "rgba(34, 197, 94, 0.35)",
      },
      closed: {
        bg: "rgba(100, 116, 139, 0.15)",
        color: "#94a3b8",
        border: "rgba(100, 116, 139, 0.3)",
      },
      active: {
        bg: "rgba(239, 68, 68, 0.15)",
        color: "#f87171",
        border: "rgba(239, 68, 68, 0.35)",
      },
    };

    const scheme = statusColors[st] ?? {
      bg: "rgba(148, 163, 184, 0.12)",
      color: "#94a3b8",
      border: "rgba(148, 163, 184, 0.25)",
    };

    const formattedLabel =
      children ??
      st
        .split("_")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ");

    return (
      <span
        className={`custom-badge status-badge status-${st} ${className}`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "4px",
          padding: "2px 8px",
          borderRadius: "6px",
          fontSize: "11px",
          fontWeight: 600,
          color: scheme.color,
          backgroundColor: scheme.bg,
          border: `1px solid ${scheme.border}`,
          ...style,
        }}
      >
        {formattedLabel}
      </span>
    );
  }

  return (
    <span
      className={`custom-badge ${className}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "2px 8px",
        borderRadius: "6px",
        fontSize: "11px",
        fontWeight: 500,
        backgroundColor: "var(--surface-raised, #191c24)",
        color: "var(--text-secondary, #a2a8b5)",
        border: "1px solid var(--border, #292d36)",
        ...style,
      }}
    >
      {children}
    </span>
  );
}
export default Badge;
