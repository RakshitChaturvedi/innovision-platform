import { useState, useRef, type ReactNode } from "react";

import CameraOverlay from "./CameraOverlay";
import DetectionOverlay from "./DetectionOverlay";
import { getActiveOverlayUseCase } from "@/lib/overlay";

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  useCases?: string[];
  overlay?: ReactNode;
}

const STREAM_URL = import.meta.env.VITE_INGESTION_API_URL;
const OVERLAY_USE_CASES_CONFIG = import.meta.env.VITE_OVERLAY_USE_CASES ?? "uc3";

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
  useCases = [],
  overlay,
}: LiveFeedProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const [imgDimensions, setImgDimensions] = useState({ width: 0, height: 0 });

  const activeUseCase = getActiveOverlayUseCase(useCases, OVERLAY_USE_CASES_CONFIG);

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
        <div style={{ position: "relative", display: "inline-block" }}>
          <img
            ref={imgRef}
            className="live-feed-image"
            src={`${STREAM_URL}/stream/${cameraId}`}
            alt={`Live feed from ${cameraName}`}
            onLoad={handleImgLoad}
            style={{ display: "block" }}
          />

          {activeUseCase && imgDimensions.width > 0 && (
            <DetectionOverlay
              cameraId={cameraId}
              useCase={activeUseCase}
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
