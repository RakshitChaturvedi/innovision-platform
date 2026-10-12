import type { ReactNode } from "react";

import CameraOverlay from "./CameraOverlay";

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  useCases?: string[];
  overlay?: ReactNode;
  sessionId?: string;
  sessionFilename?: string;
}

const DEFAULT_HOST =
  typeof window !== "undefined" && window.location.hostname
    ? window.location.hostname
    : "localhost";

const STREAM_URL =
  import.meta.env.VITE_INGESTION_API_URL || `http://${DEFAULT_HOST}:8020`;

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
  useCases = [],
  overlay,
  sessionId,
  sessionFilename,
}: LiveFeedProps) {
  const isStreamActive = Boolean(sessionId) || isOnline;
  const streamSrc = sessionId
    ? `${STREAM_URL}/stream/${cameraId}?session_id=${encodeURIComponent(sessionId)}`
    : `${STREAM_URL}/stream/${cameraId}`;

  return (
    <section
      className="live-feed"
      aria-label={`${cameraName} live feed`}
      style={{ position: "relative" }}
    >
      {sessionId && (
        <div
          style={{
            position: "absolute",
            top: "10px",
            left: "10px",
            zIndex: 10,
            background: "rgba(15, 23, 42, 0.85)",
            border: "1px solid var(--accent, #6366f1)",
            color: "#e2e8f0",
            padding: "4px 10px",
            borderRadius: "6px",
            fontSize: "11px",
            fontWeight: 650,
            display: "flex",
            alignItems: "center",
            gap: "6px",
            backdropFilter: "blur(4px)",
          }}
        >
          <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#10b981", display: "inline-block" }} />
          <span>SESSION: {sessionFilename || sessionId.slice(0, 8)}</span>
        </div>
      )}

      {isStreamActive ? (
        <img
          className="live-feed-image"
          src={streamSrc}
          alt={`Feed from ${cameraName}`}
        />
      ) : (
        <div className="live-feed-content">
          <strong>Camera Offline</strong>
          <p>No live feed or active video session</p>
        </div>
      )}

      <CameraOverlay
        cameraId={cameraId}
        useCases={useCases}
        isOnline={isStreamActive}
        sessionId={sessionId}
      >
        {overlay}
      </CameraOverlay>
    </section>
  );
}