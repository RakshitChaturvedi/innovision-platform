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
const UC2_API_URL =
  import.meta.env.VITE_UC2_API_URL || `http://${DEFAULT_HOST}:8022`;
const UC3_API_URL =
  import.meta.env.VITE_UC3_API_URL || `http://${DEFAULT_HOST}:8023`;
const UC4_API_URL =
  import.meta.env.VITE_UC4_API_URL || `http://${DEFAULT_HOST}:8024`;

function resolveStreamUrl(cameraId: string, useCases: string[] = [], retryCount = 0): string {
  const normalized = useCases.map((u) => u.toLowerCase().trim());
  const retryParam = retryCount > 0 ? `?retry=${retryCount}` : "";

  // If retried more than once, fall back to raw ingestion stream
  if (retryCount >= 2) {
    return `${STREAM_URL}/stream/${cameraId}${retryParam}`;
  }

  if (normalized.some((u) => u === "uc2" || u.includes("fire") || u.includes("smoke"))) {
    return `${UC2_API_URL}/uc2/cameras/${cameraId}/annotated-stream${retryParam}`;
  }
  if (normalized.some((u) => u === "uc3" || u.includes("ppe") || u.includes("safety") || u.includes("compliance"))) {
    return `${UC3_API_URL}/uc3/cameras/${cameraId}/annotated-stream${retryParam}`;
  }
  if (normalized.some((u) => u === "uc4" || u.includes("traffic") || u.includes("anpr") || u.includes("vehicle") || u.includes("speed"))) {
    return `${UC4_API_URL}/uc4/cameras/${cameraId}/annotated-stream${retryParam}`;
  }
  return `${STREAM_URL}/stream/${cameraId}${retryParam}`;
}

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
  useCases = [],
  overlay,
}: LiveFeedProps) {
  const [retryCount, setRetryCount] = useState(0);

  const handleStreamError = () => {
    // Retry stream connection or fall back if dropped
    setTimeout(() => {
      setRetryCount((c) => c + 1);
    }, 2000);
  };

  const streamSrc = isOnline
    ? resolveStreamUrl(cameraId, useCases, retryCount)
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