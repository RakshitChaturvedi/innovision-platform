interface LoadingStateProps {
  message?: string;
}

export function LoadingState({
  message = "Loading...",
}: LoadingStateProps) {
  return (
    <div
      className="loading-state"
      style={{
        padding: "36px 24px",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "12px",
        color: "var(--text-secondary, #a2a8b5)",
      }}
    >
      <div
        className="loading-spinner"
        style={{
          width: "28px",
          height: "28px",
          border: "2px solid var(--border, #292d36)",
          borderTopColor: "var(--primary, #A646BD)",
          borderRadius: "50%",
          animation: "spin 0.8s linear infinite",
        }}
      />
      <div style={{ fontSize: "13px", fontWeight: 500 }}>{message}</div>
    </div>
  );
}
export default LoadingState;