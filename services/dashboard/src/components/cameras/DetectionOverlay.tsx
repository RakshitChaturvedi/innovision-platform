import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { getLatestDetections } from "@/api/detections";
import { isTimestampStale } from "@/lib/overlay";

interface DetectionOverlayProps {
  cameraId: string;
  useCase?: string;
  width: number;
  height: number;
}

const OVERLAY_POLL_MS = Number(import.meta.env.VITE_OVERLAY_POLL_MS) || 2000;
const STALE_THRESHOLD_MS = 5000;

export default function DetectionOverlay({
  cameraId,
  useCase = "uc3",
  width,
  height,
}: DetectionOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isStale, setIsStale] = useState<boolean>(false);
  const [has404, setHas404] = useState<boolean>(false);

  const lastTimestampRef = useRef<string | null>(null);
  const lastObservedChangeTimeRef = useRef<number>(Date.now());

  const { data } = useQuery({
    queryKey: ["detections", cameraId, useCase],
    queryFn: async () => {
      try {
        return await getLatestDetections(cameraId, useCase);
      } catch (err: any) {
        if (err?.response?.status === 404 || err?.status === 404) {
          setHas404(true);
        }
        throw err;
      }
    },
    enabled: !has404,
    refetchInterval: has404 ? false : OVERLAY_POLL_MS,
    retry: false,
  });

  // Track when data timestamp changes and reset observed change time
  useEffect(() => {
    if (!data) return;

    const currentTs = data.timestamp
      ? String(data.timestamp)
      : JSON.stringify(data.detections ?? []);

    if (currentTs !== lastTimestampRef.current) {
      lastTimestampRef.current = currentTs;
      lastObservedChangeTimeRef.current = Date.now();
      setIsStale(false);
    }
  }, [data]);

  // Tick every 100ms to check if response timestamp hasn't changed for > STALE_THRESHOLD_MS of local time
  useEffect(() => {
    if (has404) return;

    const intervalId = setInterval(() => {
      if (
        isTimestampStale(
          lastObservedChangeTimeRef.current,
          Date.now(),
          STALE_THRESHOLD_MS,
        )
      ) {
        setIsStale(true);
      }
    }, 100);

    return () => clearInterval(intervalId);
  }, [has404]);

  // Redraw canvas whenever detections, dimensions, or staleness changes
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Clear previous frame
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Stop rendering boxes if 404 or stale
    if (has404 || isStale) return;

    const detections = data?.detections ?? [];
    if (detections.length === 0) return;

    ctx.lineWidth = 2;
    ctx.font = "13px sans-serif";

    for (const detection of detections) {
      const { x1, y1, x2, y2 } = detection.bbox;

      const px1 = x1 * width;
      const py1 = y1 * height;
      const px2 = x2 * width;
      const py2 = y2 * height;

      const boxWidth = px2 - px1;
      const boxHeight = py2 - py1;

      ctx.strokeStyle = detection.color ?? "#00ff00";
      ctx.strokeRect(px1, py1, boxWidth, boxHeight);

      ctx.fillStyle = detection.color ?? "#00ff00";
      ctx.fillText(detection.label, px1, py1 > 16 ? py1 - 4 : py1 + 14);
    }
  }, [data, width, height, isStale, has404]);

  if (has404) {
    return null;
  }

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
    </div>
  );
}
