export function Unauthorized() {
  return (
    <div style={{ display: "flex", minHeight: "60vh", alignItems: "center", justifyContent: "center" }}>
      <div style={{ textAlign: "center" }}>
        <h1 style={{ fontSize: "24px", fontWeight: 700, color: "var(--text-primary)" }}>Access Denied</h1>
        <p style={{ marginTop: "8px", fontSize: "14px", color: "var(--text-muted)" }}>
          You do not have permission to access this page.
        </p>
      </div>
    </div>
  );
}