import { useState, type ReactNode } from "react";
import CameraOverlay from "./CameraOverlay";

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  useCases?: string[];
  zoneId?: string;
  zoneName?: string;
  zoneType?: string;
  demoVideo?: string;
  overlay?: ReactNode;
}

const STREAM_URL =
  import.meta.env.VITE_INGESTION_API_URL || "http://localhost:8000";

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
  useCases = [],
  demoVideo,
  overlay,
}: LiveFeedProps) {
  const [streamError, setStreamError] = useState(false);

  // Default demo video fallbacks based on use cases if none specified
  const effectiveDemoVideo =
    demoVideo ||
    (useCases.includes("uc2")
      ? "/videos/uc2_demo.mp4"
      : useCases.includes("uc4")
        ? "/videos/uc4_demo.mp4"
        : useCases.includes("uc1")
          ? "/videos/uc1_demo.mp4"
          : useCases.includes("uc3")
            ? "/videos/uc3_demo.mp4"
            : undefined);

  return (
    <section
      className="live-feed"
      aria-label={`${cameraName} live feed`}
      style={{ position: "relative", width: "100%", height: "100%", overflow: "hidden", background: "#000" }}
    >
      {isOnline ? (
        !streamError ? (
          <img
            className="live-feed-image"
            src={`${STREAM_URL}/stream/${cameraId}`}
            alt={`Live feed from ${cameraName}`}
            onError={() => setStreamError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : effectiveDemoVideo ? (
          <video
            src={effectiveDemoVideo}
            autoPlay
            loop
            muted
            playsInline
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : (
          <div className="live-feed-content">
            <strong>Stream Offline</strong>
            <p>Awaiting ingestion frames for {cameraName}</p>
          </div>
        )
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