import { useQuery } from "@tanstack/react-query";

import { getAlertStatusCounts } from "@/api/alerts";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";

export default function AlertStatusSummary() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["alerts", "status-counts"],
    queryFn: getAlertStatusCounts,
  });

  if (isLoading) {
    return <LoadingState />;
  }

  if (isError) {
    return (
      <ErrorState message="Failed to load alert status." />
    );
  }

  if (!data) {
    return null;
  }

  return (
    <section aria-label="Alert status summary">
      <h2>Alert Status</h2>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: "12px",
        }}
      >
        <div>
          <strong>{data.pending}</strong>
          <p>Pending</p>
        </div>

        <div>
          <strong>{data.acknowledged}</strong>
          <p>Acknowledged</p>
        </div>

        <div>
          <strong>{data.resolved}</strong>
          <p>Resolved</p>
        </div>
      </div>
    </section>
  );
}