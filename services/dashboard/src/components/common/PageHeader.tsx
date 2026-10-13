import type { ReactNode } from "react";

interface PageHeaderProps {
  title: string;
  description?: string;
  actions?: ReactNode;
  badges?: ReactNode;
}

export function PageHeader({
  title,
  description,
  actions,
  badges,
}: PageHeaderProps) {
  return (
    <header className="page-header" style={{ marginBottom: "24px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "16px", flexWrap: "wrap" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
            <h1 className="page-title" style={{ margin: 0 }}>
              {title}
            </h1>
            {badges}
          </div>
          {description && (
            <p className="page-description" style={{ marginTop: "6px", color: "var(--text-secondary, #a2a8b5)" }}>
              {description}
            </p>
          )}
        </div>
        {actions && (
          <div style={{ display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap" }}>
            {actions}
          </div>
        )}
      </div>
    </header>
  );
}
export default PageHeader;
