export function LoadingState({
  message = "Loading...",
}: {
  message?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "32px",
        fontSize: "14px",
        color: "var(--text-muted)",
        gap: "10px",
      }}
    >
      <span
        style={{
          width: "14px",
          height: "14px",
          border: "2px solid var(--border)",
          borderTopColor: "var(--primary)",
          borderRadius: "50%",
          display: "inline-block",
          animation: "spin 0.8s linear infinite",
        }}
      />
      <span>{message}</span>
    </div>
  );
}