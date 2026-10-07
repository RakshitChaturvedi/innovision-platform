import type { ReactNode } from "react";

import CameraOverlay from "./CameraOverlay";

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  useCases?: string[];
  overlay?: ReactNode;
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
}: LiveFeedProps) {
  return (
    <section
      className="live-feed"
      aria-label={`${cameraName} live feed`}
    >
      {isOnline ? (
        <img
          className="live-feed-image"
          src={`${STREAM_URL}/stream/${cameraId}`}
          alt={`Live feed from ${cameraName}`}
        />
      ) : (
        <div className="live-feed-content">
          <strong>Camera Offline</strong>
          <p>No live feed available</p>
        </div>
      )}

      <CameraOverlay
        cameraId={cameraId}
        useCases={useCases}
        isOnline={isOnline}
      >
        {overlay}
      </CameraOverlay>
    </section>
  );
}