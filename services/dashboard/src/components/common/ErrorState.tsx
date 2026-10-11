export function ErrorState({
  message = "Something went wrong.",
}: {
  message?: string;
}) {
  return (
    <div
      style={{
        borderRadius: "8px",
        border: "1px solid rgba(239, 68, 68, 0.35)",
        background: "var(--danger-bg)",
        padding: "16px",
        fontSize: "14px",
        color: "var(--danger)",
      }}
    >
      {message}
    </div>
  );
}