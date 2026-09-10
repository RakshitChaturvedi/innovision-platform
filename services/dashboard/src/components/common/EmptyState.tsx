export function EmptyState({
  message = "No data available.",
}: {
  message?: string;
}) {
  return (
    <div className="p-8 text-center text-sm text-slate-500">
      {message}
    </div>
  );
}