import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import {
  getCameras,
  getCameraStatus,
} from "@/api/cameras";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { useAuth } from "@/store/useAuth";
import { canSeeCamera } from "@/lib/rbac";

export default function CameraDetail() {
  const { cameraId } = useParams<{ cameraId: string }>();
  const { user } = useAuth();

  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });

  const statusQuery = useQuery({
    queryKey: ["camera", cameraId, "status"],
    queryFn: () => getCameraStatus(cameraId as string),
    enabled: Boolean(cameraId),
  });

  if (!cameraId) {
    return <ErrorState message="Camera ID is missing." />;
  }

  if (!user || !canSeeCamera(user, cameraId)) {
    return (
      <ErrorState message="You do not have access to this camera." />
    );
  }

  if (camerasQuery.isLoading) {
    return <LoadingState />;
  }

  if (camerasQuery.isError) {
    return <ErrorState message="Failed to load cameras." />;
  }

  const camera = camerasQuery.data?.find(
    (item) => item.id === cameraId,
  );

  if (!camera) {
    return <ErrorState message="Camera not found." />;
  }

  const status = statusQuery.data ?? camera.status;

  return (
    <main>
      <header>
        <Link to="/">← Back to Dashboard</Link>

        <h1>{camera.name}</h1>

        <p>
          Status: <strong>{status}</strong>
        </p>
      </header>

      <section
        aria-label="Camera feed"
        style={{
          marginTop: "24px",
          minHeight: "400px",
          border: "1px solid #ddd",
          borderRadius: "8px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <p>Live camera feed will be integrated here.</p>
      </section>

      <section
        aria-label="Camera information"
        style={{
          marginTop: "24px",
          display: "grid",
          gridTemplateColumns:
            "repeat(auto-fit, minmax(240px, 1fr))",
          gap: "16px",
        }}
      >
        <article>
          <h2>Camera Information</h2>
          <p>Camera ID: {camera.id}</p>
          <p>FPS: {camera.fps}</p>
        </article>

        <article>
          <h2>Assigned Use Cases</h2>

          {camera.use_cases.length > 0 ? (
            <ul>
              {camera.use_cases.map((useCase) => (
                <li key={useCase}>{useCase}</li>
              ))}
            </ul>
          ) : (
            <p>No use cases assigned.</p>
          )}
        </article>
      </section>

      <section
        aria-label="Alert status"
        style={{
          marginTop: "24px",
          border: "1px solid #ddd",
          borderRadius: "8px",
          padding: "16px",
        }}
      >
        <h2>Alert Status</h2>
        <p>Alert summary will be integrated in D5.</p>
      </section>

      <section
        aria-label="Incident status"
        style={{
          marginTop: "24px",
          border: "1px solid #ddd",
          borderRadius: "8px",
          padding: "16px",
        }}
      >
        <h2>Incident Status</h2>
        <p>Incident summary will be integrated in D6.</p>
      </section>

      <section
        aria-label="Use case metrics"
        style={{
          marginTop: "24px",
          border: "1px solid #ddd",
          borderRadius: "8px",
          padding: "16px",
        }}
      >
        <h2>Use Case Metrics</h2>
        <p>UC-specific metrics will be integrated later.</p>
      </section>
    </main>
  );
}