import type { ReactNode } from "react";

import CameraOverlay from "./CameraOverlay";

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  overlay?: ReactNode;
}

const STREAM_URL =
  import.meta.env.VITE_INGESTION_API_URL;

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
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

      <CameraOverlay>
        {overlay}
      </CameraOverlay>
    </section>
  );
}