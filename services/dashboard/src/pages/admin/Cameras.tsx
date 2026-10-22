import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getOrganizations,
  getSites,
  getZones,
  getCameraEffectiveAnalytics,
  getCameraAnalyticsOverrides,
  setCameraAnalyticsOverride,
  deleteCameraAnalyticsOverride,
  assignCameraZone,
  getAnalyticsCatalog,
} from "@/api/platform";
import { getCameras, createCamera, decommissionCamera } from "@/api/cameras";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";
import type { CameraExtendedHierarchy } from "@/types/platform";

export function Cameras() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isUserAdmin = hasMinimumRole(user, "admin");

  const [selectedCamera, setSelectedCamera] = useState<CameraExtendedHierarchy | null>(null);
  const [showOverrideDrawer, setShowOverrideDrawer] = useState<boolean>(false);
  const [showAssignZoneModal, setShowAssignZoneModal] = useState<boolean>(false);
  const [showCreateCameraModal, setShowCreateCameraModal] = useState<boolean>(false);
  const [decommissioningCamera, setDecommissioningCamera] = useState<CameraExtendedHierarchy | null>(null);

  // New Camera Form State
  const [newCameraName, setNewCameraName] = useState("");
  const [newCameraLocation, setNewCameraLocation] = useState("");
  const [newCameraRtspUrl, setNewCameraRtspUrl] = useState("");
  const [newCameraSiteId, setNewCameraSiteId] = useState("");
  const [newCameraZoneId, setNewCameraZoneId] = useState("");
  const [newCameraFps, setNewCameraFps] = useState(15);
  const [newCameraUseCases, setNewCameraUseCases] = useState<string[]>(["uc2", "uc3", "uc4"]);

  // Assign Zone form state
  const [assignSiteId, setAssignSiteId] = useState<string>("");
  const [assignZoneId, setAssignZoneId] = useState<string>("");
  const [assignLifecycle, setAssignLifecycle] = useState<string>("active");

  // Error/Success state
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Queries - Strictly scoped to user's organization
  const { data: orgs } = useQuery({ queryKey: ["organizations"], queryFn: getOrganizations });
  const activeOrgId = user?.organization_id || (orgs && orgs.length > 0 ? orgs[0].id : "");

  const { data: catalog } = useQuery({ queryKey: ["analyticsCatalog"], queryFn: getAnalyticsCatalog });
  const { data: sites } = useQuery({ queryKey: ["sites", activeOrgId], queryFn: () => getSites(activeOrgId), enabled: Boolean(activeOrgId) });

  const { data: cameras, isLoading: loadingCameras, isError: camerasError } = useQuery({
    queryKey: ["camerasExtended"],
    queryFn: async () => {
      // Fetch cameras and complement with hierarchy data
      const baseCameras = await getCameras();
      return baseCameras as unknown as CameraExtendedHierarchy[];
    },
  });

  const { data: assignZones } = useQuery({
    queryKey: ["zones", assignSiteId],
    queryFn: () => getZones(assignSiteId),
    enabled: Boolean(assignSiteId),
  });

  const { data: newCamZones } = useQuery({
    queryKey: ["zones", newCameraSiteId],
    queryFn: () => getZones(newCameraSiteId),
    enabled: Boolean(newCameraSiteId),
  });

  // Create Camera Mutation
  const createCameraMutation = useMutation({
    mutationFn: () => {
      const trimmedName = newCameraName.trim();
      if (!trimmedName) {
        throw new Error("Camera name is required.");
      }
      const streamUrl = newCameraRtspUrl.trim() || `upload://${encodeURIComponent(trimmedName.toLowerCase().replace(/[^a-z0-9]+/g, "_"))}`;
      return createCamera({
        name: trimmedName,
        location: newCameraLocation.trim() || undefined,
        rtsp_url: streamUrl,
        fps: Number(newCameraFps) || 15,
        use_cases: newCameraUseCases,
        site_id: newCameraSiteId || undefined,
        zone_id: newCameraZoneId || undefined,
        organization_id: user?.organization_id || undefined,
        lifecycle_state: newCameraZoneId ? "active" : "unassigned",
        source_type: streamUrl.startsWith("rtsp://") ? "rtsp" : "uploaded_video",
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["camerasExtended"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setShowCreateCameraModal(false);
      setNewCameraName("");
      setNewCameraLocation("");
      setNewCameraRtspUrl("");
      setNewCameraSiteId("");
      setNewCameraZoneId("");
      setSuccessMsg("Camera registered successfully.");
      setErrorMsg(null);
    },
    onError: (err: any) => {
      setErrorMsg(err?.response?.data?.detail || err.message || "Failed to register camera.");
    },
  });

  // Camera Effective Analytics Query (when camera selected)
  const selectedCameraId = selectedCamera?.id || "";
  const { data: effectiveAnalytics, isLoading: loadingEffective } = useQuery({
    queryKey: ["cameraEffectiveAnalytics", selectedCameraId],
    queryFn: () => getCameraEffectiveAnalytics(selectedCameraId),
    enabled: Boolean(selectedCameraId && showOverrideDrawer),
  });

  // Camera Overrides Query (when camera selected)
  const { data: overrides } = useQuery({
    queryKey: ["cameraAnalyticsOverrides", selectedCameraId],
    queryFn: () => getCameraAnalyticsOverrides(selectedCameraId),
    enabled: Boolean(selectedCameraId && showOverrideDrawer),
  });

  // Assign Zone Mutation
  const assignZoneMutation = useMutation({
    mutationFn: () =>
      assignCameraZone(selectedCameraId, {
        site_id: assignSiteId || null,
        zone_id: assignZoneId || null,
        lifecycle_state: assignLifecycle,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["camerasExtended"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setShowAssignZoneModal(false);
      setSuccessMsg(`Camera zone assignment updated successfully.`);
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to assign zone"),
  });

  // Set Override Mutation
  const setOverrideMutation = useMutation({
    mutationFn: ({ analyticId, isEnabled }: { analyticId: string; isEnabled: boolean }) =>
      setCameraAnalyticsOverride(selectedCameraId, analyticId, isEnabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameraEffectiveAnalytics", selectedCameraId] });
      queryClient.invalidateQueries({ queryKey: ["cameraAnalyticsOverrides", selectedCameraId] });
      queryClient.invalidateQueries({ queryKey: ["camerasExtended"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setSuccessMsg("Camera analytics override saved.");
      setErrorMsg(null);
    },
    onError: (err: unknown) => {
      const errorObj = err as { response?: { status?: number; data?: { detail?: string } }; message?: string };
      if (errorObj?.response?.status === 409 || errorObj?.response?.data?.detail?.includes("limit")) {
        setErrorMsg("This analytic has reached its configured camera limit. Disable another camera or increase the organization's subscription limit.");
      } else {
        setErrorMsg(errorObj?.response?.data?.detail || errorObj?.message || "Failed to set override");
      }
    },
  });

  // Remove Override Mutation
  const removeOverrideMutation = useMutation({
    mutationFn: (analyticId: string) => deleteCameraAnalyticsOverride(selectedCameraId, analyticId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameraEffectiveAnalytics", selectedCameraId] });
      queryClient.invalidateQueries({ queryKey: ["cameraAnalyticsOverrides", selectedCameraId] });
      queryClient.invalidateQueries({ queryKey: ["camerasExtended"] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setSuccessMsg("Override removed. Reverted to zone analytics policy.");
      setErrorMsg(null);
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to remove override"),
  });

  // Decommission Camera Mutation
  const decommissionCameraMutation = useMutation({
    mutationFn: (cameraId: string) => decommissionCamera(cameraId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      queryClient.invalidateQueries({ queryKey: ["camerasExtended"] });
      setDecommissioningCamera(null);
      setSuccessMsg("Camera safely decommissioned. Historical alerts, incidents, and audit trails remain permanently preserved.");
      setErrorMsg(null);
    },
    onError: (err: any) => {
      setErrorMsg(err?.response?.data?.detail || err.message || "Failed to decommission camera");
    },
  });

  if (loadingCameras) return <LoadingState />;
  if (camerasError) return <ErrorState message="Failed to load camera registry." />;

  const overridesMap = new Map((overrides || []).map((o) => [o.analytic_id, o]));

  return (
    <div className="page">
      <header className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px", marginBottom: "20px" }}>
        <div>
          <h1 className="page-title">Camera Administration & Analytics Overrides</h1>
          <p className="page-description">
            Manage camera registry, physical zone placement, and camera-level analytics overrides.
          </p>
        </div>

        {isUserAdmin && (
          <button
            type="button"
            onClick={() => setShowCreateCameraModal(true)}
            style={{
              background: "var(--primary, #3b82f6)",
              color: "#ffffff",
              border: "none",
              borderRadius: "6px",
              padding: "8px 16px",
              fontSize: "13px",
              fontWeight: 600,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span>+</span>
            <span>Register Camera</span>
          </button>
        )}
      </header>

      {errorMsg && (
        <div style={{ padding: "12px", background: "var(--danger-bg)", border: "1px solid rgba(248,113,113,0.3)", color: "var(--danger)", borderRadius: "6px", marginBottom: "16px" }}>
          {errorMsg}
          <button onClick={() => setErrorMsg(null)} style={{ float: "right", background: "none", border: "none", color: "var(--danger)" }}>✕</button>
        </div>
      )}

      {successMsg && (
        <div style={{ padding: "12px", background: "var(--success-bg)", border: "1px solid rgba(70,189,146,0.3)", color: "var(--success)", borderRadius: "6px", marginBottom: "16px" }}>
          {successMsg}
          <button onClick={() => setSuccessMsg(null)} style={{ float: "right", background: "none", border: "none", color: "var(--success)" }}>✕</button>
        </div>
      )}

      {/* Camera Table */}
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "13px" }}>
          <thead>
            <tr style={{ background: "var(--surface-raised)", borderBottom: "1px solid var(--border)", color: "var(--text-muted)" }}>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>CAMERA NAME & ID</th>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>SITE & ZONE</th>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>STATE & SOURCE</th>
              <th style={{ padding: "12px 16px", fontWeight: 650 }}>EFFECTIVE ANALYTICS</th>
              <th style={{ padding: "12px 16px", fontWeight: 650, textAlign: "right" }}>ACTIONS</th>
            </tr>
          </thead>
          <tbody>
            {cameras && cameras.length > 0 ? (
              cameras.map((cam) => {
                const siteName = cam.site?.name || "Unassigned Site";
                const zoneName = cam.zone?.name || "Unassigned Zone";
                const isSimulation = cam.is_simulation || cam.source_type === "test_simulation";

                return (
                  <tr key={cam.id} style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "14px 16px" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{cam.name}</div>
                      <div style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--mono)" }}>{cam.id}</div>
                    </td>

                    <td style={{ padding: "14px 16px" }}>
                      <div style={{ color: "var(--text-primary)" }}>📍 {siteName}</div>
                      <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>🏢 {zoneName}</div>
                    </td>

                    <td style={{ padding: "14px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "4px" }}>
                        <span style={{ fontSize: "11px", fontWeight: 600, padding: "2px 6px", borderRadius: "4px", background: cam.lifecycle_state === "active" ? "var(--success-bg)" : "var(--surface-raised)", color: cam.lifecycle_state === "active" ? "var(--success)" : "var(--text-muted)" }}>
                          {(cam.lifecycle_state || "active").toUpperCase()}
                        </span>
                        <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>{(cam.source_type || "RTSP").toUpperCase()}</span>
                      </div>
                      {isSimulation && (
                        <span style={{ fontSize: "10px", fontWeight: 700, padding: "2px 6px", borderRadius: "4px", background: "var(--warning-bg)", color: "var(--warning)", border: "1px solid rgba(189,154,70,0.3)" }}>
                          TEST SIMULATION SOURCE
                        </span>
                      )}
                    </td>

                    <td style={{ padding: "14px 16px" }}>
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                        {cam.use_cases && cam.use_cases.length > 0 ? (
                          cam.use_cases.map((uc) => (
                            <span key={uc} style={{ fontSize: "11px", fontWeight: 600, padding: "2px 6px", borderRadius: "4px", background: "var(--primary-bg)", color: "var(--primary)", border: "1px solid rgba(166,70,189,0.3)" }}>
                              {uc.toUpperCase()}
                            </span>
                          ))
                        ) : (
                          <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>None active</span>
                        )}
                      </div>
                    </td>

                    <td style={{ padding: "14px 16px", textAlign: "right" }}>
                      <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
                        {isUserAdmin && (
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedCamera(cam);
                              setAssignSiteId(cam.site_id || "");
                              setAssignZoneId(cam.zone_id || "");
                              setAssignLifecycle(cam.lifecycle_state || "active");
                              setShowAssignZoneModal(true);
                            }}
                            style={{ background: "var(--surface-raised)", border: "1px solid var(--border-hover)", color: "var(--text-primary)", padding: "4px 10px", borderRadius: "4px", fontSize: "12px" }}
                          >
                            Assign Zone
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedCamera(cam);
                            setShowOverrideDrawer(true);
                          }}
                          style={{ background: "var(--primary-bg)", border: "1px solid var(--primary)", color: "var(--primary)", padding: "4px 10px", borderRadius: "4px", fontSize: "12px" }}
                        >
                          Overrides
                        </button>
                        {isUserAdmin && (
                          <button
                            type="button"
                            onClick={() => setDecommissioningCamera(cam)}
                            style={{
                              background: "rgba(239, 68, 68, 0.1)",
                              border: "1px solid rgba(239, 68, 68, 0.3)",
                              color: "var(--danger)",
                              padding: "4px 10px",
                              borderRadius: "4px",
                              fontSize: "12px",
                              cursor: "pointer",
                            }}
                          >
                            Decommission
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td colSpan={5} style={{ padding: "48px 24px", textAlign: "center" }}>
                  <div style={{ maxWidth: "440px", margin: "0 auto", display: "flex", flexDirection: "column", alignItems: "center", gap: "10px" }}>
                    <div style={{ width: "44px", height: "44px", borderRadius: "50%", background: "var(--surface-raised)", border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "20px" }}>
                      📹
                    </div>
                    <div style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary)" }}>
                      No Cameras Registered
                    </div>
                    <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: 0, lineHeight: 1.5 }}>
                      No operational cameras are currently registered for your organization. Register an RTSP camera stream or a designated video upload ingestion source to begin live safety monitoring.
                    </p>
                    {isUserAdmin && (
                      <button
                        type="button"
                        onClick={() => setShowCreateCameraModal(true)}
                        style={{
                          background: "var(--primary, #3b82f6)",
                          color: "#ffffff",
                          border: "none",
                          borderRadius: "6px",
                          padding: "8px 18px",
                          fontSize: "13px",
                          fontWeight: 600,
                          cursor: "pointer",
                          marginTop: "6px",
                        }}
                      >
                        + Register First Camera
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Camera Analytics Override Drawer / Modal */}
      {showOverrideDrawer && selectedCamera && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", justifyContent: "flex-end", zIndex: 1000 }}>
          <div style={{ background: "var(--surface)", borderLeft: "1px solid var(--border)", width: "100%", maxWidth: "520px", height: "100%", padding: "24px", overflowY: "auto", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid var(--border)" }}>
                <div>
                  <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--primary)", textTransform: "uppercase" }}>CAMERA ANALYTICS RESOLVER</span>
                  <h3 style={{ margin: "2px 0 0 0", fontSize: "18px", fontWeight: 600 }}>{selectedCamera.name}</h3>
                  <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>{selectedCamera.id}</div>
                </div>
                <button onClick={() => setShowOverrideDrawer(false)} style={{ background: "none", border: "none", color: "var(--text-muted)", fontSize: "18px" }}>✕</button>
              </div>

              <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "6px", padding: "12px", marginBottom: "20px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: "1.4" }}>
                💡 <strong>Camera overrides</strong> allow this specific camera to enable or disable analytics independently from its assigned zone policy, subject to organization subscription limits.
              </div>

              {loadingEffective ? (
                <LoadingState />
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
                  {catalog?.map((catItem) => {
                    const eff = effectiveAnalytics?.find((e) => e.analytic_id === catItem.id || e.code === catItem.code);
                    const overrideObj = overridesMap.get(catItem.id);
                    const hasOverride = overrideObj !== undefined;
                    const isActive = Boolean(eff?.is_active);
                    const isSubscribed = eff ? eff.subscription_active : true;

                    let sourceBadgeText = "Inherited from Zone";
                    let sourceBadgeBg = "var(--surface-raised)";
                    let sourceBadgeColor = "var(--text-secondary)";

                    if (!isSubscribed) {
                      sourceBadgeText = "Not Subscribed";
                      sourceBadgeBg = "var(--danger-bg)";
                      sourceBadgeColor = "var(--danger)";
                    } else if (hasOverride) {
                      sourceBadgeText = "Camera Override";
                      sourceBadgeBg = "var(--warning-bg)";
                      sourceBadgeColor = "var(--warning)";
                    }

                    return (
                      <div key={catItem.id} style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "6px", padding: "16px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "8px" }}>
                          <div>
                            <span style={{ fontSize: "10px", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                              {catItem.category} • {catItem.internal_code.toUpperCase()}
                            </span>
                            <h4 style={{ margin: "2px 0 0 0", fontSize: "14px", fontWeight: 600 }}>{catItem.display_name}</h4>
                          </div>

                          <span style={{ fontSize: "11px", fontWeight: 600, padding: "3px 8px", borderRadius: "12px", background: sourceBadgeBg, color: sourceBadgeColor }}>
                            {sourceBadgeText}
                          </span>
                        </div>

                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "12px", paddingTop: "10px", borderTop: "1px solid var(--border)" }}>
                          <span style={{ fontSize: "12px", fontWeight: 600, color: isActive ? "var(--success)" : "var(--text-muted)" }}>
                            Status: {isActive ? "✓ ACTIVE ON CAMERA" : "INACTIVE"}
                          </span>

                          {isUserAdmin && isSubscribed && (
                            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                              {hasOverride ? (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => setOverrideMutation.mutate({ analyticId: catItem.id, isEnabled: !overrideObj.is_enabled })}
                                    disabled={setOverrideMutation.isPending}
                                    style={{ background: "var(--surface)", border: "1px solid var(--border-hover)", color: "var(--text-primary)", padding: "3px 8px", borderRadius: "4px", fontSize: "11px" }}
                                  >
                                    Set to {overrideObj.is_enabled ? "Disabled" : "Enabled"}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => removeOverrideMutation.mutate(catItem.id)}
                                    disabled={removeOverrideMutation.isPending}
                                    style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--danger)", padding: "3px 8px", borderRadius: "4px", fontSize: "11px" }}
                                  >
                                    Revert to Zone
                                  </button>
                                </>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => setOverrideMutation.mutate({ analyticId: catItem.id, isEnabled: !isActive })}
                                  disabled={setOverrideMutation.isPending}
                                  style={{ background: "var(--primary-bg)", border: "1px solid var(--primary)", color: "var(--primary)", padding: "3px 8px", borderRadius: "4px", fontSize: "11px" }}
                                >
                                  Override to {isActive ? "Disable" : "Enable"}
                                </button>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            <div style={{ paddingTop: "16px", borderTop: "1px solid var(--border)", display: "flex", justifyContent: "flex-end" }}>
              <button onClick={() => setShowOverrideDrawer(false)} style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 20px", borderRadius: "4px", fontWeight: 600 }}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Assign Zone Modal */}
      {showAssignZoneModal && selectedCamera && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "440px" }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Assign Camera to Zone</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Site</label>
                <select
                  value={assignSiteId}
                  onChange={(e) => {
                    setAssignSiteId(e.target.value);
                    setAssignZoneId("");
                  }}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                >
                  <option value="">-- Select Plant Site --</option>
                  {sites?.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.code})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Zone</label>
                <select
                  value={assignZoneId}
                  onChange={(e) => setAssignZoneId(e.target.value)}
                  disabled={!assignSiteId}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                >
                  <option value="">-- Select Zone --</option>
                  {assignZones?.map((z) => (
                    <option key={z.id} value={z.id}>
                      {z.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Lifecycle State</label>
                <select
                  value={assignLifecycle}
                  onChange={(e) => setAssignLifecycle(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                >
                  <option value="active">Active</option>
                  <option value="unassigned">Unassigned</option>
                  <option value="maintenance">Maintenance</option>
                  <option value="decommissioned">Decommissioned</option>
                </select>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button onClick={() => setShowAssignZoneModal(false)} style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "6px 14px", borderRadius: "4px" }}>
                Cancel
              </button>
              <button
                onClick={() => assignZoneMutation.mutate()}
                disabled={assignZoneMutation.isPending}
                style={{ background: "var(--primary)", border: "none", color: "#fff", padding: "6px 16px", borderRadius: "4px", fontWeight: 600 }}
              >
                {assignZoneMutation.isPending ? "Assigning..." : "Save Assignment"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Register Camera */}
      {showCreateCameraModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: "20px" }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "480px", maxHeight: "90vh", overflowY: "auto" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid var(--border)" }}>
              <div>
                <h3 style={{ margin: 0, fontSize: "17px", fontWeight: 700 }}>Register Operational Camera</h3>
                <p style={{ margin: "2px 0 0 0", fontSize: "12px", color: "var(--text-muted)" }}>
                  Add a plant camera feed for safety analytics and PPE compliance.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowCreateCameraModal(false)}
                style={{ background: "none", border: "none", color: "var(--text-muted)", fontSize: "18px", cursor: "pointer" }}
              >
                ✕
              </button>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "14px", marginBottom: "20px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                  Camera Name *
                </label>
                <input
                  type="text"
                  placeholder="e.g. Loading Dock Gate 01"
                  value={newCameraName}
                  onChange={(e) => setNewCameraName(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px", fontSize: "13px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                  Physical Location
                </label>
                <input
                  type="text"
                  placeholder="e.g. North Warehouse Sector B"
                  value={newCameraLocation}
                  onChange={(e) => setNewCameraLocation(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px", fontSize: "13px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                  RTSP Stream URL (or leave blank for Upload-Only Testing)
                </label>
                <input
                  type="text"
                  placeholder="rtsp://192.168.1.100:554/live or leave blank"
                  value={newCameraRtspUrl}
                  onChange={(e) => setNewCameraRtspUrl(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px", fontSize: "13px" }}
                />
                <span style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "2px", display: "block" }}>
                  Leave blank if you will test analytics strictly by uploading recorded video files.
                </span>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                    Plant Site
                  </label>
                  <select
                    value={newCameraSiteId}
                    onChange={(e) => {
                      setNewCameraSiteId(e.target.value);
                      setNewCameraZoneId("");
                    }}
                    style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px", fontSize: "13px" }}
                  >
                    <option value="">-- Unassigned Site --</option>
                    {sites?.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name} ({s.code})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                    Physical Zone
                  </label>
                  <select
                    value={newCameraZoneId}
                    onChange={(e) => setNewCameraZoneId(e.target.value)}
                    disabled={!newCameraSiteId}
                    style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px", fontSize: "13px" }}
                  >
                    <option value="">-- Unassigned Zone --</option>
                    {newCamZones?.map((z) => (
                      <option key={z.id} value={z.id}>
                        {z.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "4px" }}>
                  Capture Frame Rate (FPS)
                </label>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={newCameraFps}
                  onChange={(e) => setNewCameraFps(Math.max(1, Math.min(60, Number(e.target.value) || 15)))}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px", fontSize: "13px" }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "6px" }}>
                  Assigned AI Capabilities
                </label>
                <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
                  {[
                    { id: "uc2", label: "UC2 (Person Tracking)" },
                    { id: "uc3", label: "UC3 (PPE Compliance)" },
                    { id: "uc4", label: "UC4 (Forklift Proximity)" },
                  ].map((uc) => {
                    const isChecked = newCameraUseCases.includes(uc.id);
                    return (
                      <label key={uc.id} style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "12px", color: "var(--text-primary)", cursor: "pointer" }}>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setNewCameraUseCases([...newCameraUseCases, uc.id]);
                            } else {
                              setNewCameraUseCases(newCameraUseCases.filter((id) => id !== uc.id));
                            }
                          }}
                        />
                        <span>{uc.label}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button
                type="button"
                onClick={() => setShowCreateCameraModal(false)}
                style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "7px 16px", borderRadius: "4px", fontSize: "13px", cursor: "pointer" }}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => createCameraMutation.mutate()}
                disabled={!newCameraName.trim() || createCameraMutation.isPending}
                style={{
                  background: newCameraName.trim() && !createCameraMutation.isPending ? "var(--primary, #3b82f6)" : "var(--border)",
                  border: "none",
                  color: "#ffffff",
                  padding: "7px 18px",
                  borderRadius: "4px",
                  fontWeight: 600,
                  fontSize: "13px",
                  cursor: newCameraName.trim() && !createCameraMutation.isPending ? "pointer" : "not-allowed",
                }}
              >
                {createCameraMutation.isPending ? "Registering..." : "Register Camera"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal: Decommission Camera */}
      {decommissioningCamera && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000, padding: "16px" }}>
          <div style={{ background: "var(--surface)", border: "1px solid rgba(239,68,68,0.4)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "460px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
              <span style={{ fontSize: "24px" }}>⚠️</span>
              <h3 style={{ margin: 0, fontSize: "18px", color: "var(--danger)" }}>Confirm Camera Decommissioning</h3>
            </div>
            <p style={{ margin: "0 0 12px 0", fontSize: "13.5px", color: "var(--text-primary)", lineHeight: 1.5 }}>
              Are you sure you want to decommission camera <strong>{decommissioningCamera.name}</strong>?
            </p>
            <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: "6px", padding: "12px", marginBottom: "20px", fontSize: "12px", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              <div style={{ color: "var(--text-primary)", fontWeight: 600, marginBottom: "4px" }}>
                Forensic &amp; Data Integrity Safeguards:
              </div>
              <ul style={{ margin: 0, paddingLeft: "18px" }}>
                <li>Live camera stream and video ingestion will be safely disabled.</li>
                <li>Historical alerts, incident records, and evidence files are permanently preserved.</li>
                <li>Administrative mutation is logged to the forensic audit ledger.</li>
              </ul>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button
                type="button"
                onClick={() => setDecommissioningCamera(null)}
                style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "7px 16px", borderRadius: "4px", fontSize: "13px", cursor: "pointer" }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={decommissionCameraMutation.isPending}
                onClick={() => decommissionCameraMutation.mutate(decommissioningCamera.id)}
                style={{ background: "var(--danger)", border: "none", color: "#fff", padding: "7px 18px", borderRadius: "4px", fontWeight: 600, fontSize: "13px", cursor: "pointer" }}
              >
                {decommissionCameraMutation.isPending ? "Decommissioning..." : "Confirm Decommission"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}