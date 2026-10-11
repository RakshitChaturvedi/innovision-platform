export function EmptyState({
  message = "No data available.",
}: {
  message?: string;
}) {
  return (
    <div
      style={{
        padding: "32px",
        textAlign: "center",
        fontSize: "14px",
        color: "var(--text-muted)",
      }}
    >
      {message}
    </div>
  );
}