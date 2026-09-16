import { useNavigate } from "react-router-dom";

import LiveFeed from "./LiveFeed";

import type { Camera } from "@/types/camera";

interface CameraTileProps {
  camera: Camera;
}

function getStatusLabel(status: Camera["status"]) {
  switch (status) {
    case "online":
      return "Online";

    case "offline":
      return "Offline";

    case "reconnecting":
      return "Reconnecting";

    case "disabled":
      return "Disabled";

    default:
      return status;
  }
}

export default function CameraTile({
  camera,
}: CameraTileProps) {
  const navigate = useNavigate();

  return (
    <article className="camera-tile">
      <button
        type="button"
        className="camera-tile-button"
        onClick={() => navigate(`/cameras/${camera.id}`)}
        aria-label={`Open ${camera.name}`}
      >
        <header className="camera-tile-header">
          <div className="camera-tile-heading">
            <h3>{camera.name}</h3>

            {camera.location && (
              <span>{camera.location}</span>
            )}
          </div>

          <span
            className={`status-badge status-${camera.status}`}
          >
            <span className="status-dot" />
            {getStatusLabel(camera.status)}
          </span>
        </header>

        <div className="camera-tile-feed">
          <LiveFeed
            cameraId={camera.id}
            cameraName={camera.name}
            isOnline={camera.status === "online"}
          />
        </div>

        <footer className="camera-tile-footer">
          <div className="camera-meta">
            <span>
              <strong>{camera.fps}</strong> FPS
            </span>

            <span className="meta-divider" />

            <span>
              {camera.use_cases.length > 0
                ? camera.use_cases.join(", ")
                : "No use cases"}
            </span>
          </div>

          <span className="camera-view">
            View
            <span aria-hidden="true">→</span>
          </span>
        </footer>
      </button>
    </article>
  );
}