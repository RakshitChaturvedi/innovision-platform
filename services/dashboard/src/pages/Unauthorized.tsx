export function Unauthorized() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">Access Denied</h1>
        <p className="mt-2 text-sm text-slate-500">
          You do not have permission to access this page.
        </p>
      </div>
    </div>
  );
}