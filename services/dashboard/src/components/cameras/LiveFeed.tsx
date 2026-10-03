import { useState, useRef, type ReactNode } from "react";

import CameraOverlay from "./CameraOverlay";
import DetectionOverlay from "./DetectionOverlay";

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  useCases?: string[];
  overlay?: ReactNode;
}

const STREAM_URL =
  import.meta.env.VITE_INGESTION_API_URL;

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
  useCases = [],
  overlay,
}: LiveFeedProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgDimensions, setImgDimensions] = useState({ width: 0, height: 0 });

  const hasDetections = useCases.some((uc) =>
    ["uc1", "uc2", "uc3", "uc4"].includes(uc.toLowerCase()),
  );

  function handleImgLoad() {
    const img = imgRef.current;
    if (img) {
      setImgDimensions({
        width: img.offsetWidth,
        height: img.offsetHeight,
      });
    }
  }

  return (
    <section
      className="live-feed"
      aria-label={`${cameraName} live feed`}
    >
      {isOnline ? (
        // position: relative container so the canvas can be absolutely placed on top
        <div style={{ position: "relative", display: "inline-block" }}>
          <img
            ref={imgRef}
            className="live-feed-image"
            src={`${STREAM_URL}/stream/${cameraId}`}
            alt={`Live feed from ${cameraName}`}
            onLoad={handleImgLoad}
            style={{ display: "block" }}
          />

          {hasDetections && imgDimensions.width > 0 && (
            <DetectionOverlay
              cameraId={cameraId}
              width={imgDimensions.width}
              height={imgDimensions.height}
            />
          )}
        </div>
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
