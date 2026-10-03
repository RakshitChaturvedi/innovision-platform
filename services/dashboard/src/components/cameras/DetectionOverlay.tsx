import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getLatestDetections } from "@/api/detections";

interface DetectionOverlayProps {
  cameraId: string;
  width: number;
  height: number;
}

const OVERLAY_POLL_MS = Number(import.meta.env.VITE_OVERLAY_POLL_MS) || 2000;
const STALE_THRESHOLD_MS = 5000;

export default function DetectionOverlay({
  cameraId,
  width,
  height,
}: DetectionOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [age, setAge] = useState<number | null>(null);
  const [isStale, setIsStale] = useState<boolean>(false);

  const { data } = useQuery({
    queryKey: ["detections", cameraId],
    queryFn: () => getLatestDetections(cameraId),
    refetchInterval: OVERLAY_POLL_MS,
    // Don't throw on error — overlay is best-effort
    retry: false,
  });

  // Tick every 100ms to keep the age counter visibly counting up and track staleness
  useEffect(() => {
    if (!data) {
      setAge(null);
      setIsStale(false);
      return;
    }

    const fetchedAt = data.timestamp
      ? new Date(data.timestamp as string).getTime()
      : Date.now();

    const updateAge = () => {
      const elapsedMs = Date.now() - fetchedAt;
      if (elapsedMs > STALE_THRESHOLD_MS) {
        setIsStale(true);
      } else {
        setIsStale(false);
      }
      setAge(Math.round(elapsedMs / 100) / 10);
    };

    updateAge();
    const id = setInterval(updateAge, 100);

    return () => clearInterval(id);
  }, [data]);

  // Redraw canvas whenever detections, dimensions, or staleness changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Clear previous frame
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Clear bounding boxes if response is older than 5s
    if (isStale) return;

    const detections = data?.detections ?? [];
    if (detections.length === 0) return;

    ctx.lineWidth = 2;
    ctx.font = "13px sans-serif";

    for (const detection of detections) {
      const { x1, y1, x2, y2 } = detection.bbox;

      // Scale normalized coords to canvas pixel coords
      const px1 = x1 * width;
      const py1 = y1 * height;
      const px2 = x2 * width;
      const py2 = y2 * height;

      const boxWidth = px2 - px1;
      const boxHeight = py2 - py1;

      // Draw bounding box
      ctx.strokeStyle = detection.color ?? "#00ff00";
      ctx.strokeRect(px1, py1, boxWidth, boxHeight);

      // Draw label above the box
      ctx.fillStyle = detection.color ?? "#00ff00";
      ctx.fillText(detection.label, px1, py1 > 16 ? py1 - 4 : py1 + 14);
    }
  }, [data, width, height, isStale]);

  return (
    <div
      aria-hidden="true"
      style={{ position: "absolute", top: 0, left: 0, pointerEvents: "none" }}
    >
      <canvas
        ref={canvasRef}
        width={width}
        height={height}
        style={{ display: "block" }}
      />

      {age !== null && (
        <p
          style={{
            position: "absolute",
            bottom: 6,
            left: 8,
            margin: 0,
            fontSize: "11px",
            color: isStale ? "#ff4d4f" : "#fff",
            textShadow: "0 0 4px #000",
          }}
        >
          Detection age: {age.toFixed(1)}s {isStale ? "(stale)" : ""}
        </p>
      )}
    </div>
  );
}
