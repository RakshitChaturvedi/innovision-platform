import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import {
  getCameras,
  getCameraStatus,
} from "@/api/cameras";

import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";

import LiveFeed from "@/components/cameras/LiveFeed";

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

  if (!cameraId) {
    return (
      <ErrorState message="Camera ID is missing." />
    );
  }

  if (camerasQuery.isLoading) {
    return <LoadingState />;
  }

  if (camerasQuery.isError) {
    return (
      <ErrorState message="Failed to load cameras." />
    );
  }

  const camera = camerasQuery.data?.find(
    (item) => item.id === cameraId,
  );

  if (!camera) {
    return (
      <ErrorState message="Camera not found." />
    );
  }

  const status = statusQuery.data ?? camera.status;

  const statusLabel =
    status === "online"
      ? "Online"
      : status === "offline"
        ? "Offline"
        : status === "reconnecting"
          ? "Reconnecting"
          : "Disabled";

  return (
    <main className="page camera-detail-page">
      <header className="camera-detail-header">
        <Link
          to="/"
          className="back-link"
        >
          ← Back to Dashboard
        </Link>

        <div className="camera-detail-title-row">
          <div>
            <h1 className="page-title">
              {camera.name}
            </h1>

            <p className="page-description">
              {camera.location ?? "No location specified"}
              {" · "}
              {camera.use_cases.length > 0
                ? camera.use_cases.join(", ").toUpperCase()
                : "No use cases"}
            </p>
          </div>

          <span
            className={`status-badge status-${status}`}
          >
            <span className="status-dot" />
            {statusLabel}
          </span>
        </div>
      </header>

      <section
        className="camera-detail-feed"
        aria-label={`${camera.name} live feed`}
      >
        <LiveFeed
          cameraId={camera.id}
          cameraName={camera.name}
          isOnline={status === "online"}
        />
      </section>

      <section
        className="camera-detail-info"
        aria-label="Camera information"
      >
        <div className="detail-group">
          <span className="detail-label">
            Camera ID
          </span>

          <span className="detail-value detail-id">
            {camera.id}
          </span>
        </div>

        <div className="detail-group">
          <span className="detail-label">
            Location
          </span>

          <span className="detail-value">
            {camera.location ?? "Not specified"}
          </span>
        </div>

        <div className="detail-group">
          <span className="detail-label">
            Frame Rate
          </span>

          <span className="detail-value">
            {camera.fps} FPS
          </span>
        </div>

        <div className="detail-group">
          <span className="detail-label">
            Use Cases
          </span>

          <span className="detail-value">
            {camera.use_cases.length > 0
              ? camera.use_cases.join(", ")
              : "None"}
          </span>
        </div>
      </section>

      <section
        className="camera-detail-section"
        aria-label="Incident status"
      >
        <div className="section-header">
          <div>
            <h2 className="section-title">
              Incident Status
            </h2>

            <p className="section-description">
              Incident information associated with this camera.
            </p>
          </div>
        </div>

        <div className="detail-placeholder">
          Incident summary will be integrated in D6.
        </div>
      </section>

      <section
        className="camera-detail-section"
        aria-label="Use case metrics"
      >
        <div className="section-header">
          <div>
            <h2 className="section-title">
              Use Case Metrics
            </h2>

            <p className="section-description">
              Analytics metrics associated with this camera.
            </p>
          </div>
        </div>

        <div className="detail-placeholder">
          UC-specific metrics will be integrated later.
        </div>
      </section>
    </main>
  );
}