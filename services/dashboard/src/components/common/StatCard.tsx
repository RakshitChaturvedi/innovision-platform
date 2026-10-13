import type { ReactNode } from "react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: ReactNode;
  icon?: ReactNode;
  trend?: {
    value: string;
    isPositive?: boolean;
  };
  color?: string;
  onClick?: () => void;
  className?: string;
}

export function StatCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  color = "#A646BD",
  onClick,
  className = "",
}: StatCardProps) {
  return (
    <div
      className={`stat-card ${onClick ? "clickable" : ""} ${className}`}
      onClick={onClick}
      style={{
        background: "var(--surface, #15171e)",
        border: "1px solid var(--border, #292d36)",
        borderRadius: "12px",
        padding: "18px 20px",
        display: "flex",
        flexDirection: "column",
        gap: "12px",
        position: "relative",
        overflow: "hidden",
        transition: "border-color 0.15s, transform 0.15s",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: "3px",
          backgroundColor: color,
        }}
      />

      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span
          style={{
            fontSize: "13px",
            fontWeight: 500,
            color: "var(--text-secondary, #a2a8b5)",
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          {title}
        </span>
        {icon && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: "32px",
              height: "32px",
              borderRadius: "8px",
              backgroundColor: `${color}18`,
              color: color,
              fontSize: "16px",
            }}
          >
            {icon}
          </div>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: "10px" }}>
        <span
          style={{
            fontSize: "28px",
            fontWeight: 700,
            color: "var(--text-primary, #f1f3f5)",
            fontFamily: "var(--mono, monospace)",
            letterSpacing: "-0.02em",
          }}
        >
          {value}
        </span>
        {trend && (
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: trend.isPositive ? "#4ade80" : "#f87171",
            }}
          >
            {trend.value}
          </span>
        )}
      </div>

      {subtitle && (
        <span
          style={{
            fontSize: "12px",
            color: "var(--text-muted, #707786)",
          }}
        >
          {subtitle}
        </span>
      )}
    </div>
  );
}
export default StatCard;
