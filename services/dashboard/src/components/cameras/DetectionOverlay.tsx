import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getLatestDetections } from "@/api/detections";

interface DetectionOverlayProps {
  cameraId: string;
  width: number;
  height: number;
}

export default function DetectionOverlay({
  cameraId,
  width,
  height,
}: DetectionOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [age, setAge] = useState<number | null>(null);

  const { data } = useQuery({
    queryKey: ["detections", cameraId],
    queryFn: () => getLatestDetections(cameraId),
    refetchInterval: 2000,
    retry: false,
  });

  // Tick every 100ms to keep the age counter visibly counting up
  useEffect(() => {
    if (!data?.timestamp) {
      setAge(null);
      return;
    }

    const fetchedAt = new Date(data.timestamp as string).getTime();

    const id = setInterval(() => {
      setAge(
        Math.round((Date.now() - fetchedAt) / 100) / 10,
      );
    }, 100);

    return () => clearInterval(id);
  }, [data?.timestamp]);

  // Redraw canvas whenever detections or dimensions change
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Clear previous frame
    ctx.clearRect(0, 0, canvas.width, canvas.height);

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
  }, [data, width, height]);

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
            color: "#fff",
            textShadow: "0 0 4px #000",
          }}
        >
          Detection age: {age.toFixed(1)}s
        </p>
      )}
    </div>
  );
}
