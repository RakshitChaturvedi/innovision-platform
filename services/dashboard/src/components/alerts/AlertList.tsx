import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import {
  acknowledgeAlert,
  getAlerts,
  resolveAlert,
  type AlertFilters,
} from "@/api/alerts";

import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import AlertCard from "@/components/alerts/AlertCard";

interface AlertListProps {
  filters: AlertFilters;
}

export default function AlertList({
  filters,
}: AlertListProps) {
  const queryClient = useQueryClient();

  // Primary 30s polling fallback; Socket.IO invalidates this on push events
  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useQuery({
    queryKey: ["alerts", filters],
    queryFn: () => getAlerts(filters),
    refetchInterval: 30000,
  });

  const acknowledgeMutation = useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alerts-pending-count"] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: resolveAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alerts-pending-count"] });
    },
  });

  if (isLoading) {
    return <LoadingState message="Fetching platform alerts..." />;
  }

  if (isError) {
    return (
      <ErrorState
        message="Failed to load alerts from platform alert_management service."
        onRetry={() => refetch()}
      />
    );
  }

  if (!data || data.length === 0) {
    return (
      <EmptyState
        message="No alerts match the current filter criteria."
        icon="🛡️"
      />
    );
  }

  return (
    <div
      className="alert-list"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "12px",
      }}
    >
      {data.map((alert) => (
        <AlertCard
          key={alert.id || alert.alert_id}
          alert={alert}
          onAcknowledge={(alertId) => acknowledgeMutation.mutate(alertId)}
          onResolve={(alertId) => resolveMutation.mutate(alertId)}
          isAcknowledging={acknowledgeMutation.isPending}
          isResolving={resolveMutation.isPending}
        />
      ))}
    </div>
  );
}