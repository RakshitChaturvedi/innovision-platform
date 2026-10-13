interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  message = "Something went wrong while fetching data.",
  onRetry,
}: ErrorStateProps) {
  return (
    <div
      className="error-state"
      style={{
        padding: "24px",
        borderRadius: "10px",
        backgroundColor: "rgba(239, 68, 68, 0.08)",
        border: "1px solid rgba(239, 68, 68, 0.25)",
        color: "#f87171",
        textAlign: "center",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "12px",
      }}
    >
      <div style={{ fontSize: "24px" }}>⚠️</div>
      <div style={{ fontSize: "14px", fontWeight: 500 }}>{message}</div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={{
            marginTop: "6px",
            padding: "6px 14px",
            borderRadius: "6px",
            border: "1px solid rgba(239, 68, 68, 0.4)",
            backgroundColor: "rgba(239, 68, 68, 0.15)",
            color: "#fca5a5",
            fontSize: "12px",
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Try Again
        </button>
      )}
    </div>
  );
}
export default ErrorState;