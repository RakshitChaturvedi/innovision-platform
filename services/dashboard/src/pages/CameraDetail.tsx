import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { getCameras, getCameraStatus } from "@/api/cameras";
import { getCameraHierarchy, getCameraEffectiveAnalytics } from "@/api/platform";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import LiveFeed from "@/components/cameras/LiveFeed";

export default function CameraDetail() {
  const { cameraId } = useParams<{ cameraId: string }>();

  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });

  const hierarchyQuery = useQuery({
    queryKey: ["cameraHierarchy", cameraId],
    queryFn: () => getCameraHierarchy(cameraId as string),
    enabled: Boolean(cameraId),
  });

  const effectiveQuery = useQuery({
    queryKey: ["cameraEffectiveAnalytics", cameraId],
    queryFn: () => getCameraEffectiveAnalytics(cameraId as string),
    enabled: Boolean(cameraId),
  });

  const statusQuery = useQuery({
    queryKey: ["camera", cameraId, "status"],
    queryFn: () => getCameraStatus(cameraId as string),
    enabled: Boolean(cameraId),
    refetchInterval: 5000,
  });

  if (!cameraId) {
    return <ErrorState message="Camera ID is missing." />;
  }

  if (camerasQuery.isLoading || hierarchyQuery.isLoading) {
    return <LoadingState />;
  }

  if (camerasQuery.isError) {
    return <ErrorState message="Failed to load camera feed." />;
  }

  const camera = camerasQuery.data?.find((item) => item.id === cameraId);

  if (!camera) {
    return <ErrorState message="Camera not found." />;
  }

  const status = statusQuery.data ?? camera.status;
  const hierarchy = hierarchyQuery.data;
  const effectiveList = effectiveQuery.data || [];

  const statusLabel =
    status === "online"
      ? "Online"
      : status === "offline"
        ? "Offline"
        : status === "reconnecting"
          ? "Reconnecting"
          : "Disabled";

  const isSimulation = hierarchy?.is_simulation || hierarchy?.source_type === "test_simulation";
  const siteName = hierarchy?.site?.name || "Unassigned Site";
  const zoneName = hierarchy?.zone?.name || "Unassigned Zone";

  return (
    <main className="page camera-detail-page">
      <header className="camera-detail-header">
        <Link to="/" className="back-link">
          ← Back to Dashboard
        </Link>

        <div className="camera-detail-title-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "12px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h1 className="page-title" style={{ margin: 0 }}>{camera.name}</h1>
              {isSimulation && (
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    padding: "3px 8px",
                    borderRadius: "4px",
                    background: "var(--warning-bg)",
                    color: "var(--warning)",
                    border: "1px solid rgba(189,154,70,0.3)",
                    letterSpacing: "0.5px",
                  }}
                >
                  TEST SIMULATION SOURCE
                </span>
              )}
            </div>

            <p className="page-description" style={{ marginTop: "4px" }}>
              📍 {siteName} • 🏢 {zoneName} • {camera.location ?? "Industrial Plant Zone"}
            </p>
          </div>

          <span className={`status-badge status-${status}`}>
            <span className="status-dot" />
            {statusLabel}
          </span>
        </div>
      </header>

      {/* Live Video Feed with Canvas Detection Overlays */}
      <section className="camera-detail-feed" aria-label={`${camera.name} live feed`} style={{ margin: "20px 0" }}>
        <LiveFeed
          cameraId={camera.id}
          cameraName={camera.name}
          isOnline={status === "online"}
          useCases={camera.use_cases}
        />
      </section>

      {/* Camera & Effective Analytics Details Panel */}
      <section className="camera-detail-info" aria-label="Camera information" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "24px" }}>
        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Plant Site</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600 }}>{siteName}</span>
        </div>

        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Zone</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600 }}>{zoneName}</span>
        </div>

        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Lifecycle State</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600, color: "var(--success)" }}>{(hierarchy?.lifecycle_state || "active").toUpperCase()}</span>
        </div>

        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Frame Rate</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600 }}>{camera.fps} FPS</span>
        </div>
      </section>

      {/* Effective Analytics Panel (Phase 4 Integration) */}
      <section style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "24px" }}>
        <h2 style={{ fontSize: "16px", fontWeight: 600, margin: "0 0 4px 0" }}>Active Effective Analytics</h2>
        <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "0 0 16px 0" }}>
          Resolved active analytics capabilities based on organization subscription, zone policy, and camera override.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px" }}>
          {effectiveList.length > 0 ? (
            effectiveList.map((eff) => {
              const sourceLabel =
                eff.source === "camera_override"
                  ? "Camera Override"
                  : eff.source === "zone"
                    ? "Zone Policy"
                    : "None";

              return (
                <div
                  key={eff.analytic_id}
                  style={{
                    background: "var(--surface-raised)",
                    border: eff.is_active ? "1px solid var(--border-hover)" : "1px solid var(--border)",
                    borderRadius: "6px",
                    padding: "14px",
                    opacity: eff.is_active ? 1 : 0.6,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <span style={{ fontSize: "13px", fontWeight: 600, color: eff.is_active ? "var(--text-primary)" : "var(--text-muted)" }}>
                      {eff.display_name}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 700,
                        padding: "2px 6px",
                        borderRadius: "4px",
                        background: eff.is_active ? "var(--success-bg)" : "var(--danger-bg)",
                        color: eff.is_active ? "var(--success)" : "var(--danger)",
                      }}
                    >
                      {eff.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>

                  <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                    Source: <strong style={{ color: "var(--primary)" }}>{sourceLabel}</strong>
                  </div>
                </div>
              );
            })
          ) : (
            <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>No analytics enabled on this camera.</div>
          )}
        </div>
      </section>
    </main>
  );
}