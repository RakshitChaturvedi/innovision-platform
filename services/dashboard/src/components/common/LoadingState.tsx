export function LoadingState({
  message = "Loading...",
}: {
  message?: string;
}) {
  return (
    <div className="flex items-center justify-center p-8 text-sm text-slate-500">
      {message}
    </div>
  );
}