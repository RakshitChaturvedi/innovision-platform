import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getAnalyticsCatalog, getOrganizationSubscriptions, getOrganizations, updateOrganizationSubscription, createOrganizationSubscription } from "@/api/platform";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";

export function AnalyticsPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isUserAdmin = hasMinimumRole(user, "admin");

  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [editingSub, setEditingSub] = useState<{ analytic_id: string; max_cameras: number; is_enabled: boolean } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Fetch Analytics Catalog
  const { data: catalog, isLoading: loadingCatalog, isError: catalogError } = useQuery({
    queryKey: ["analyticsCatalog"],
    queryFn: getAnalyticsCatalog,
  });

  // Fetch Organizations
  const { data: orgs } = useQuery({
    queryKey: ["organizations"],
    queryFn: getOrganizations,
  });

  const activeOrgId = selectedOrgId || (orgs && orgs.length > 0 ? orgs[0].id : "");

  // Fetch Subscriptions for Active Org
  const { data: subscriptions } = useQuery({
    queryKey: ["organizationSubscriptions", activeOrgId],
    queryFn: () => getOrganizationSubscriptions(activeOrgId),
    enabled: Boolean(activeOrgId),
  });

  // Mutation for update subscription
  const updateSubMutation = useMutation({
    mutationFn: async ({ analyticId, payload }: { analyticId: string; payload: { is_enabled: boolean; max_cameras_allowed: number } }) => {
      const existing = subscriptions?.find((s) => s.analytic_id === analyticId || s.analytic_code === analyticId);
      if (existing) {
        return updateOrganizationSubscription(activeOrgId, analyticId, payload);
      } else {
        return createOrganizationSubscription(activeOrgId, {
          analytic_id: analyticId,
          is_enabled: payload.is_enabled,
          max_cameras_allowed: payload.max_cameras_allowed,
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organizationSubscriptions", activeOrgId] });
      setEditingSub(null);
      setErrorMsg(null);
    },
    onError: (err: Error) => {
      setErrorMsg(err.message || "Failed to update subscription");
    },
  });

  if (loadingCatalog) return <LoadingState />;
  if (catalogError) return <ErrorState message="Failed to load analytics catalog." />;

  const subsMap = new Map((subscriptions || []).map((s) => [s.analytic_id, s]));

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Analytics Catalog & Subscriptions</h1>
          <p className="page-description">
            Platform analytics capabilities and organization entitlement rules.
          </p>
        </div>

        {orgs && orgs.length > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "13px", color: "var(--text-secondary)" }}>Organization:</span>
            <select
              value={activeOrgId}
              onChange={(e) => setSelectedOrgId(e.target.value)}
              style={{
                background: "var(--surface-raised)",
                color: "var(--text-primary)",
                border: "1px solid var(--border)",
                borderRadius: "4px",
                padding: "6px 12px",
              }}
            >
              {orgs.map((org) => (
                <option key={org.id} value={org.id}>
                  {org.name} ({org.code})
                </option>
              ))}
            </select>
          </div>
        )}
      </header>

      {errorMsg && (
        <div style={{ padding: "12px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: "6px", marginBottom: "16px" }}>
          {errorMsg}
        </div>
      )}

      <section aria-labelledby="catalog-heading" style={{ marginBottom: "32px" }}>
        <h2 id="catalog-heading" className="section-title" style={{ marginBottom: "16px" }}>
          Platform Analytics Capabilities
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" }}>
          {catalog?.map((item) => {
            const sub = subsMap.get(item.id);
            const isSubscribed = sub && sub.status === "enabled";

            return (
              <div
                key={item.id}
                style={{
                  background: "var(--surface)",
                  border: "1px solid var(--border)",
                  borderRadius: "8px",
                  padding: "20px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
                    <span style={{ fontSize: "12px", fontWeight: "600", color: "var(--primary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                      {item.category} • {item.internal_code.toUpperCase()}
                    </span>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: "600",
                        padding: "3px 8px",
                        borderRadius: "12px",
                        background: isSubscribed ? "var(--success-bg)" : "var(--danger-bg)",
                        color: isSubscribed ? "var(--success)" : "var(--danger)",
                      }}
                    >
                      {isSubscribed ? "Subscribed" : sub?.status === "expired" ? "Expired" : "Not Subscribed"}
                    </span>
                  </div>

                  <h3 style={{ fontSize: "16px", fontWeight: "600", margin: "0 0 8px 0" }}>{item.display_name}</h3>
                  <p style={{ fontSize: "13px", color: "var(--text-secondary)", lineHeight: "1.4", margin: "0 0 16px 0" }}>
                    {item.description || "Enterprise video intelligence analytic module."}
                  </p>
                </div>

                <div style={{ borderTop: "1px solid var(--border)", paddingTop: "12px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                    Limit: <strong>{sub?.max_cameras_allowed ?? "N/A"}</strong> cameras
                  </div>

                  {isUserAdmin && activeOrgId && (
                    <button
                      type="button"
                      onClick={() =>
                        setEditingSub({
                          analytic_id: item.id,
                          max_cameras: sub?.max_cameras_allowed ?? 20,
                          is_enabled: sub ? sub.is_enabled : true,
                        })
                      }
                      style={{
                        background: "var(--surface-raised)",
                        border: "1px solid var(--border-hover)",
                        color: "var(--text-primary)",
                        padding: "4px 10px",
                        borderRadius: "4px",
                        fontSize: "12px",
                      }}
                    >
                      Configure Limit
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Edit Subscription Modal */}
      {editingSub && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.7)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "24px",
              width: "100%",
              maxWidth: "420px",
            }}
          >
            <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Configure Subscription Entitlement</h3>

            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "14px", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={editingSub.is_enabled}
                  onChange={(e) => setEditingSub({ ...editingSub, is_enabled: e.target.checked })}
                />
                Enable Subscription for Organization
              </label>
            </div>

            <div style={{ marginBottom: "20px" }}>
              <label style={{ display: "block", fontSize: "13px", color: "var(--text-secondary)", marginBottom: "6px" }}>
                Max Cameras Allowed:
              </label>
              <input
                type="number"
                min="1"
                max="500"
                value={editingSub.max_cameras}
                onChange={(e) => setEditingSub({ ...editingSub, max_cameras: parseInt(e.target.value) || 0 })}
                style={{
                  width: "100%",
                  background: "var(--surface-raised)",
                  border: "1px solid var(--border)",
                  color: "var(--text-primary)",
                  padding: "8px 12px",
                  borderRadius: "4px",
                }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button
                type="button"
                onClick={() => setEditingSub(null)}
                style={{
                  background: "transparent",
                  border: "1px solid var(--border)",
                  color: "var(--text-secondary)",
                  padding: "6px 16px",
                  borderRadius: "4px",
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={updateSubMutation.isPending}
                onClick={() =>
                  updateSubMutation.mutate({
                    analyticId: editingSub.analytic_id,
                    payload: {
                      is_enabled: editingSub.is_enabled,
                      max_cameras_allowed: editingSub.max_cameras,
                    },
                  })
                }
                style={{
                  background: "var(--primary)",
                  border: "none",
                  color: "#fff",
                  padding: "6px 16px",
                  borderRadius: "4px",
                  fontWeight: "600",
                }}
              >
                {updateSubMutation.isPending ? "Saving..." : "Save Settings"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
