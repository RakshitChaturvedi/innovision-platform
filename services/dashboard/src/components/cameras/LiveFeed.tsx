import { useEffect, useRef, useState, type ReactNode } from "react";
import CameraOverlay from "./CameraOverlay";

interface DetectionBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

interface DetectionItem {
  label: string;
  confidence: number;
  color: string;
  box: DetectionBox;
}

interface LiveFeedProps {
  cameraId: string;
  cameraName: string;
  isOnline: boolean;
  overlay?: ReactNode;
}

const STREAM_URL = import.meta.env.VITE_INGESTION_API_URL || "http://localhost:8020";
const UC3_API_URL = import.meta.env.VITE_UC3_API_URL || "http://localhost:8040";

export default function LiveFeed({
  cameraId,
  cameraName,
  isOnline,
  overlay,
}: LiveFeedProps) {
  const [detections, setDetections] = useState<DetectionItem[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);

  const [containerDim, setContainerDim] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const [imageRatio, setImageRatio] = useState<number>(16 / 9);

  // Track container dimension changes
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerDim({
          w: entry.contentRect.width,
          h: entry.contentRect.height,
        });
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Poll latest detections from UC3 service
  useEffect(() => {
    if (!isOnline || !cameraId) return;

    let isMounted = true;
    const fetchDetections = async () => {
      try {
        const res = await fetch(`${UC3_API_URL}/uc3/cameras/${cameraId}/latest-detections`);
        if (res.ok) {
          const data = await res.json();
          if (isMounted && data.detections) {
            setDetections(data.detections);
          }
        }
      } catch (err) {
        // Fallback or handle offline
      }
    };

    fetchDetections();
    const interval = setInterval(fetchDetections, 300);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [cameraId, isOnline]);

  // Compute exact pixel bounding box relative to letterboxed video image
  const getBoxStyle = (box: DetectionBox) => {
    const cw = containerDim.w;
    const ch = containerDim.h;
    if (cw === 0 || ch === 0) return { display: "none" };

    const containerRatio = cw / ch;

    let renderedW = cw;
    let renderedH = ch;
    let offsetX = 0;
    let offsetY = 0;

    if (containerRatio > imageRatio) {
      // Height-constrained (black bars on left/right)
      renderedH = ch;
      renderedW = ch * imageRatio;
      offsetX = (cw - renderedW) / 2;
    } else {
      // Width-constrained (black bars on top/bottom)
      renderedW = cw;
      renderedH = cw / imageRatio;
      offsetY = (ch - renderedH) / 2;
    }

    const left = offsetX + box.x1 * renderedW;
    const top = offsetY + box.y1 * renderedH;
    const width = (box.x2 - box.x1) * renderedW;
    const height = (box.y2 - box.y1) * renderedH;

    return {
      left: `${left.toFixed(1)}px`,
      top: `${top.toFixed(1)}px`,
      width: `${width.toFixed(1)}px`,
      height: `${height.toFixed(1)}px`,
    };
  };

  return (
    <section
      ref={containerRef}
      className="live-feed"
      aria-label={`${cameraName} live feed`}
      style={{
        position: "relative",
        width: "100%",
        height: "100%",
        aspectRatio: "16 / 9",
        overflow: "hidden",
        backgroundColor: "#000",
      }}
    >
      {isOnline ? (
        <img
          ref={imgRef}
          className="live-feed-image"
          src={`${STREAM_URL}/stream/${cameraId}`}
          alt={`Live feed from ${cameraName}`}
          onLoad={(e) => {
            const img = e.currentTarget;
            if (img.naturalWidth && img.naturalHeight) {
              setImageRatio(img.naturalWidth / img.naturalHeight);
            }
          }}
          style={{ width: "100%", height: "100%", objectFit: "contain" }}
        />
      ) : (
        <div className="live-feed-content">
          <strong>Camera Offline</strong>
          <p>No live feed available</p>
        </div>
      )}

      <CameraOverlay>
        {overlay}
        {isOnline &&
          detections.map((det, idx) => {
            const boxStyle = getBoxStyle(det.box);

            return (
              <div
                key={idx}
                style={{
                  position: "absolute",
                  ...boxStyle,
                  border: `2px solid ${det.color || "#FF8A3D"}`,
                  backgroundColor: `${det.color || "#FF8A3D"}20`,
                  boxSizing: "border-box",
                  pointerEvents: "none",
                  borderRadius: "2px",
                  transition: "all 0.1s ease-out",
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    top: "-22px",
                    left: "-2px",
                    backgroundColor: det.color || "#FF8A3D",
                    color: "#000",
                    fontWeight: "bold",
                    fontSize: "11px",
                    padding: "2px 6px",
                    borderRadius: "3px",
                    whiteSpace: "nowrap",
                    boxShadow: "0 1px 3px rgba(0,0,0,0.5)",
                  }}
                >
                  {det.label}
                </span>
              </div>
            );
          })}
      </CameraOverlay>
    </section>
  );
}