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

import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";
import type { Alert } from "@/types/alert";

interface AlertListProps {
  filters: AlertFilters;
  onCreateIncident?: (alert: Alert) => void;
}

export default function AlertList({
  filters,
  onCreateIncident,
}: AlertListProps) {
  const { user } = useAuth();
  const canOperate = hasMinimumRole(user, "operator");
  const {
    data,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["alerts", filters],
    queryFn: () => getAlerts(filters),
  });

  const queryClient = useQueryClient();

  const acknowledgeMutation = useMutation({
    mutationFn: acknowledgeAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["alerts"],
      });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: resolveAlert,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["alerts"],
      });
    },
  });

  if (isLoading) {
    return <LoadingState message="Loading alerts..." />;
  }

  if (isError) {
    return (
      <ErrorState message="Failed to load alerts." />
    );
  }

  if (!data || data.length === 0) {
    return (
      <EmptyState message="No alerts match the current filters." />
    );
  }

  return (
    <div className="alert-list">
      {data.map((alert) => (
        <AlertCard
          key={alert.id}
          alert={alert}
          onAcknowledge={canOperate ? ((alertId) => acknowledgeMutation.mutate(alertId)) : undefined}
          onResolve={canOperate ? ((alertId) => resolveMutation.mutate(alertId)) : undefined}
          onCreateIncident={canOperate ? onCreateIncident : undefined}
          isAcknowledging={acknowledgeMutation.isPending}
          isResolving={resolveMutation.isPending}
        />
      ))}
    </div>
  );
}