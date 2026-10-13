import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import {
  getCameras,
  getCameraStatus,
} from "@/api/cameras";
import { getAlerts } from "@/api/alerts";

import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { PageHeader } from "@/components/common/PageHeader";
import { Badge } from "@/components/common/Badge";
import AlertCard from "@/components/alerts/AlertCard";
import LiveFeed from "@/components/cameras/LiveFeed";
import { getUCModule, getUCBadgeStyle } from "@/modules/registry";

export default function CameraDetail() {
  const { cameraId } = useParams<{ cameraId: string }>();

  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });

  const statusQuery = useQuery({
    queryKey: ["camera", cameraId, "status"],
    queryFn: () => getCameraStatus(cameraId as string),
    enabled: Boolean(cameraId),
    refetchInterval: 5000,
  });

  const cameraAlertsQuery = useQuery({
    queryKey: ["camera-alerts", cameraId],
    queryFn: () => getAlerts({ cameraId: cameraId as string, limit: 10 }),
    enabled: Boolean(cameraId),
    refetchInterval: 15000,
  });

  if (!cameraId) {
    return <ErrorState message="Camera ID is missing." />;
  }

  if (camerasQuery.isLoading) {
    return <LoadingState message="Loading camera configuration..." />;
  }

  if (camerasQuery.isError) {
    return <ErrorState message="Failed to load cameras." onRetry={() => camerasQuery.refetch()} />;
  }

  const camera = camerasQuery.data?.find((item) => item.id === cameraId);

  if (!camera) {
    return (
      <div className="page">
        <Link to="/" className="back-link" style={{ marginBottom: "16px", display: "inline-block", color: "var(--text-secondary)" }}>
          ← Back to Dashboard
        </Link>
        <ErrorState message={`Camera with ID "${cameraId}" not found.`} />
      </div>
    );
  }

  const status = statusQuery.data ?? camera.status;
  const recentAlerts = cameraAlertsQuery.data ?? [];

  return (
    <main className="page camera-detail-page">
      <div style={{ marginBottom: "12px" }}>
        <Link
          to="/"
          style={{
            fontSize: "13px",
            color: "var(--text-secondary, #a2a8b5)",
            textDecoration: "none",
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          ← Back to Master Dashboard
        </Link>
      </div>

      <PageHeader
        title={camera.name}
        description={camera.zone_name ?? camera.location ?? "Zone Monitoring Node"}
        actions={
          camera.use_cases.some((u) => u.toLowerCase() === "uc4") ? (
            <Link
              to={`/uc4/configurator?camera=${camera.id}`}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                borderRadius: "6px",
                background: "#0D9488",
                color: "#ffffff",
                fontSize: "12px",
                fontWeight: 700,
                textDecoration: "none",
                boxShadow: "0 2px 8px rgba(13, 148, 136, 0.3)",
              }}
            >
              <span>📐 Configure Speed Polygon & Tripwires →</span>
            </Link>
          ) : undefined
        }
        badges={
          <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
            <Badge variant="status" status={status} />
            {camera.use_cases.map((ucId) => {
              const mod = getUCModule(ucId);
              const style = getUCBadgeStyle(ucId);
              return (
                <span
                  key={ucId}
                  style={{
                    padding: "3px 8px",
                    borderRadius: "6px",
                    fontSize: "11px",
                    fontWeight: 700,
                    backgroundColor: style.backgroundColor,
                    color: style.color,
                    border: `1px solid ${style.borderColor}`,
                    textTransform: "uppercase",
                  }}
                >
                  {mod?.icon} {mod?.shortName ?? ucId.toUpperCase()}
                </span>
              );
            })}
          </div>
        }
      />

      {/* Main Live Video & Canvas Overlay Section */}
      <section
        className="camera-detail-feed"
        aria-label={`${camera.name} live feed`}
        style={{
          borderRadius: "12px",
          overflow: "hidden",
          border: "1px solid var(--border, #292d36)",
          backgroundColor: "#000",
          height: "480px",
          position: "relative",
          marginBottom: "24px",
        }}
      >
        <LiveFeed
          cameraId={camera.id}
          cameraName={camera.name}
          isOnline={status === "online"}
          useCases={camera.use_cases}
          zoneId={camera.zone_id}
          zoneName={camera.zone_name}
          zoneType={camera.zone_type}
          demoVideo={camera.demo_video}
        />
      </section>

      {/* Camera Metadata Grid */}
      <section
        className="camera-detail-info"
        aria-label="Camera specifications"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: "16px",
          padding: "20px",
          borderRadius: "12px",
          backgroundColor: "var(--surface, #15171e)",
          border: "1px solid var(--border, #292d36)",
          marginBottom: "24px",
        }}
      >
        <div>
          <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
            Camera Identifier
          </span>
          <div style={{ fontSize: "13px", fontFamily: "var(--mono, monospace)", color: "var(--text-primary)", marginTop: "4px" }}>
            {camera.id}
          </div>
        </div>

        <div>
          <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
            Operational Zone
          </span>
          <div style={{ fontSize: "13px", color: "var(--text-primary)", marginTop: "4px", fontWeight: 500 }}>
            {camera.zone_name ?? camera.location ?? "Standard Zone"}
          </div>
        </div>

        <div>
          <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
            Zone AI Policy
          </span>
          <div style={{ fontSize: "13px", color: "var(--primary, #A646BD)", marginTop: "4px", fontWeight: 500 }}>
            {camera.zone_policy ?? "Automated Stream Inspection"}
          </div>
        </div>

        <div>
          <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
            Inference Target
          </span>
          <div style={{ fontSize: "13px", color: "var(--text-primary)", marginTop: "4px" }}>
            {camera.fps} FPS Target
          </div>
        </div>
      </section>

      {/* Recent Alerts for this camera */}
      <section className="camera-recent-alerts">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
            Recent Alerts for this Camera ({recentAlerts.length})
          </h2>
          <Link
            to={`/alerts?cameraId=${camera.id}`}
            style={{ fontSize: "12px", color: "var(--primary, #A646BD)", textDecoration: "none" }}
          >
            View all in Alert Center →
          </Link>
        </div>

        {recentAlerts.length === 0 ? (
          <div
            style={{
              padding: "24px",
              textAlign: "center",
              borderRadius: "10px",
              border: "1px dashed var(--border, #292d36)",
              color: "var(--text-muted)",
              fontSize: "13px",
            }}
          >
            No recent alerts triggered by this camera.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {recentAlerts.slice(0, 5).map((alert) => (
              <AlertCard key={alert.id || alert.alert_id} alert={alert} />
            ))}
          </div>
        )}
      </section>
    </main>
  );
}