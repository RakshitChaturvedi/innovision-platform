import { useState } from "react";
import type { ReactNode } from "react";

import CameraOverlay from "./CameraOverlay";

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  useCases?: string[];
  overlay?: ReactNode;
}

const STREAM_URL =
  import.meta.env.VITE_INGESTION_API_URL || "http://localhost:8020";
const UC2_STREAM_URL =
  import.meta.env.VITE_UC2_STREAM_URL || "http://localhost:8030";

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
  useCases = [],
  overlay,
}: LiveFeedProps) {
  const isUC2 = useCases.includes("uc2");
  const [feedMode, setFeedMode] = useState<"ai" | "raw">(isUC2 ? "ai" : "raw");

  const streamSrc =
    feedMode === "ai"
      ? `${UC2_STREAM_URL}/preview/${cameraId}`
      : `${STREAM_URL}/stream/${cameraId}`;

  return (
    <section
      className="live-feed"
      aria-label={`${cameraName} live feed`}
      style={{ position: "relative" }}
    >
      {isOnline ? (
        <div style={{ position: "relative", width: "100%", height: "100%" }}>
          <img
            className="live-feed-image"
            src={streamSrc}
            alt={`Live feed from ${cameraName}`}
            onError={(e) => {
              if (feedMode === "ai") {
                (e.target as HTMLImageElement).src = `${STREAM_URL}/stream/${cameraId}`;
              }
            }}
          />

          <div
            style={{
              position: "absolute",
              top: 8,
              right: 8,
              zIndex: 10,
              display: "flex",
              gap: "6px",
              background: "rgba(15, 23, 42, 0.75)",
              backdropFilter: "blur(4px)",
              padding: "4px 8px",
              borderRadius: "6px",
              border: "1px solid rgba(255, 255, 255, 0.15)",
            }}
          >
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setFeedMode("ai");
              }}
              style={{
                background: feedMode === "ai" ? "#e53e3e" : "transparent",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                padding: "3px 8px",
                fontSize: "11px",
                cursor: "pointer",
                fontWeight: feedMode === "ai" ? 600 : 400,
              }}
            >
              🔥 AI Detection (UC2)
            </button>
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setFeedMode("raw");
              }}
              style={{
                background: feedMode === "raw" ? "#4a5568" : "transparent",
                color: "#fff",
                border: "none",
                borderRadius: "4px",
                padding: "3px 8px",
                fontSize: "11px",
                cursor: "pointer",
                fontWeight: feedMode === "raw" ? 600 : 400,
              }}
            >
              📷 Raw Stream
            </button>
          </div>
        </div>
      ) : (
        <div className="live-feed-content">
          <strong>Camera Offline</strong>
          <p>No live feed available</p>
        </div>
      )}

      <CameraOverlay>{overlay}</CameraOverlay>
    </section>
  );
}