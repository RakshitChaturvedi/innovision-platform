import { useQuery } from "@tanstack/react-query";

import { getCameras } from "@/api/cameras";

import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { EmptyState } from "@/components/common/EmptyState";

import CameraTile from "@/components/cameras/CameraTile";

export default function MasterDashboard() {
  const {
    data: cameras,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    refetchInterval: 5000,
  });

  if (isLoading) {
    return <LoadingState />;
  }

  if (isError) {
    return <ErrorState message="Failed to load cameras." />;
  }

  if (!cameras || cameras.length === 0) {
    return <EmptyState message="No cameras available." />;
  }

  const onlineCount = cameras.filter(
    (camera) => camera.status === "online",
  ).length;

  const offlineCount = cameras.filter(
    (camera) => camera.status === "offline",
  ).length;

  const useCaseCount = new Set(
    cameras.flatMap((camera) => camera.use_cases),
  ).size;

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Master Dashboard</h1>
          <p className="page-description">
            System overview and live camera monitoring.
          </p>
        </div>
      </header>

      <section
        className="dashboard-stats"
        aria-label="Dashboard statistics"
      >
        <div className="stat">
          <span className="stat-label">Cameras</span>
          <strong className="stat-value">
            {cameras.length}
          </strong>
        </div>

        <div className="stat">
          <span className="stat-label">Online</span>
          <strong className="stat-value stat-success">
            {onlineCount}
          </strong>
        </div>

        <div className="stat">
          <span className="stat-label">Offline</span>
          <strong className="stat-value stat-danger">
            {offlineCount}
          </strong>
        </div>

        <div className="stat">
          <span className="stat-label">Use Cases</span>
          <strong className="stat-value">
            {useCaseCount}
          </strong>
        </div>
      </section>

      <section aria-labelledby="cameras-heading">
        <div className="section-header">
          <div>
            <h2 id="cameras-heading" className="section-title">
              Cameras
            </h2>
            <p className="section-description">
              Live status and monitoring feeds.
            </p>
          </div>

          <span className="section-count">
            {cameras.length}{" "}
            {cameras.length === 1 ? "camera" : "cameras"}
          </span>
        </div>

        <div className="camera-grid">
          {cameras.map((camera) => (
            <CameraTile
              key={camera.id}
              camera={camera}
            />
          ))}
        </div>
      </section>
    </main>
  );
}