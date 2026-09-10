import { useQuery } from "@tanstack/react-query";

import { getCameras } from "@/api/cameras";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { EmptyState } from "@/components/common/EmptyState";
import { useAuth } from "@/store/useAuth";
import CameraTile from "@/components/cameras/CameraTile";

export default function MasterDashboard() {
  const { user } = useAuth();

  const {
    data: cameras,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
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

  const visibleCameras =
    user?.role === "admin" || user?.role === "superadmin"
      ? cameras
      : cameras.filter((camera) =>
          user?.camera_ids.includes(camera.id),
        );

  if (visibleCameras.length === 0) {
    return <EmptyState message="No cameras assigned to you." />;
  }

  return (
    <main>
      <header>
        <h1>Master Dashboard</h1>
        <p>{visibleCameras.length} cameras</p>
      </header>

      <section
        aria-label="Camera grid"
        style={{
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fill, minmax(320px, 1fr))",
          gap: "16px",
          marginTop: "24px",
        }}
      >
        {visibleCameras.map((camera) => (
            <CameraTile key={camera.id} camera={camera} />
        ))}
      </section>
    </main>
  );
}