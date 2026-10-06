import { useState, type ReactNode } from "react";

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
  const [retryCount, setRetryCount] = useState(0);

  const handleStreamError = () => {
    // Retry stream connection if dropped
    setTimeout(() => {
      setRetryCount((c) => c + 1);
    }, 2000);
  };

  const streamSrc = isOnline
    ? `${STREAM_URL}/stream/${cameraId}${retryCount > 0 ? `?retry=${retryCount}` : ""}`
    : undefined;

  return (
    <section
      className="live-feed"
      aria-label={`${cameraName} live feed`}
    >
      {isOnline ? (
        <img
          key={retryCount}
          className="live-feed-image"
          src={streamSrc}
          onError={handleStreamError}
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