import { useEffect, useRef, useState, type ReactNode } from "react";

export interface DetectionBBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface DetectionItem {
  track_id?: number | string;
  bbox: DetectionBBox;
  label: string;
  color?: string;
  metadata?: Record<string, unknown>;
}

export interface LatestDetectionsResponse {
  timestamp: string;
  camera_id: string;
  detections: DetectionItem[];
  zones?: unknown[];
}

export interface CameraOverlayProps {
  cameraId: string;
  useCases?: string[];
  isOnline?: boolean;
  children?: ReactNode;
}

const DEFAULT_HOST =
  typeof window !== "undefined" && window.location.hostname
    ? window.location.hostname
    : "localhost";

const UC2_API_URL =
  import.meta.env.VITE_UC2_API_URL || `http://${DEFAULT_HOST}:8022`;
const UC3_API_URL =
  import.meta.env.VITE_UC3_API_URL || `http://${DEFAULT_HOST}:8023`;
const UC4_API_URL =
  import.meta.env.VITE_UC4_API_URL || `http://${DEFAULT_HOST}:8024`;

function parseHexToRgba(hex: string, alpha: number): string {
  if (!hex || !hex.startsWith("#")) {
    return hex || "rgba(0, 255, 0, 0.15)";
  }
  let c = hex.slice(1);
  if (c.length === 3) {
    c = c
      .split("")
      .map((char) => char + char)
      .join("");
  }
  const num = parseInt(c, 16);
  if (isNaN(num) || c.length !== 6) {
    return `rgba(0, 255, 0, ${alpha})`;
  }
  const r = (num >> 16) & 255;
  const g = (num >> 8) & 255;
  const b = num & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function resolveEndpoints(cameraId: string, useCases: string[] = []): string[] {
  const normalized = useCases.map((u) => u.toLowerCase().trim());
  const urls: string[] = [];

  const isUc2 = normalized.some(
    (u) => u === "uc2" || u.includes("fire") || u.includes("smoke")
  );
  const isUc3 = normalized.some(
    (u) =>
      u === "uc3" ||
      u.includes("ppe") ||
      u.includes("safety") ||
      u.includes("compliance") ||
      u.includes("helmet") ||
      u.includes("vest")
  );
  const isUc4 = normalized.some(
    (u) =>
      u === "uc4" ||
      u.includes("traffic") ||
      u.includes("anpr") ||
      u.includes("vehicle") ||
      u.includes("speed")
  );

  if (isUc2) {
    urls.push(`${UC2_API_URL}/uc2/cameras/${cameraId}/latest-detections`);
  }
  if (isUc3) {
    urls.push(`${UC3_API_URL}/uc3/cameras/${cameraId}/latest-detections`);
  }
  if (isUc4) {
    urls.push(`${UC4_API_URL}/uc4/cameras/${cameraId}/latest-detections`);
  }

  // If no matching use case tag provided or list empty, poll candidate services
  if (urls.length === 0) {
    urls.push(`${UC2_API_URL}/uc2/cameras/${cameraId}/latest-detections`);
    urls.push(`${UC3_API_URL}/uc3/cameras/${cameraId}/latest-detections`);
    urls.push(`${UC4_API_URL}/uc4/cameras/${cameraId}/latest-detections`);
  }

  return urls;
}

export default function CameraOverlay({
  cameraId,
  useCases = [],
  isOnline = true,
  children,
}: CameraOverlayProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const detectionsRef = useRef<DetectionItem[]>([]);
  const [, setTick] = useState(0);

  // Poll latest-detections at ~10 FPS (every 100ms)
  useEffect(() => {
    if (!isOnline || !cameraId) {
      detectionsRef.current = [];
      return;
    }

    let isMounted = true;
    const abortController = new AbortController();
    const urls = resolveEndpoints(cameraId, useCases);

    const fetchDetections = async () => {
      try {
        const fetchPromises = urls.map(async (url) => {
          const res = await fetch(url, {
            signal: abortController.signal,
            headers: { Accept: "application/json" },
          });
          if (!res.ok) return null;
          return (await res.json()) as LatestDetectionsResponse;
        });

        const results = await Promise.allSettled(fetchPromises);
        if (!isMounted) return;

        const mergedDetections: DetectionItem[] = [];
        for (const r of results) {
          if (r.status === "fulfilled" && r.value?.detections) {
            mergedDetections.push(...r.value.detections);
          }
        }

        detectionsRef.current = mergedDetections;
        setTick((t) => (t + 1) % 10000);
      } catch {
        // Ignore aborted or network poll errors silently
      }
    };

    // Initial immediate fetch
    fetchDetections();
    const intervalId = setInterval(fetchDetections, 100);

    return () => {
      isMounted = false;
      abortController.abort();
      clearInterval(intervalId);
    };
  }, [cameraId, useCases, isOnline]);

  // Render bounding boxes on HTML5 canvas
  useEffect(() => {
    const container = containerRef.current;
    const canvas = canvasRef.current;
    if (!container || !canvas) return;

    const width = container.clientWidth;
    const height = container.clientHeight;
    if (width === 0 || height === 0) return;

    const dpr = window.devicePixelRatio || 1;
    if (canvas.width !== width * dpr || canvas.height !== height * dpr) {
      canvas.width = width * dpr;
      canvas.height = height * dpr;
    }

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.resetTransform();
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);

    const detections = detectionsRef.current;
    if (!detections || detections.length === 0) {
      return;
    }

    // Inspect underlying img element for letterbox/pillarbox calculation
    const imgEl = container.parentElement?.querySelector<HTMLImageElement>("img.live-feed-image");

    // If source is already an annotated stream, server annotations are rendered directly onto frames
    if (imgEl?.src?.includes("annotated-stream")) {
      return;
    }

    let renderW = width;
    let renderH = height;
    let offsetX = 0;
    let offsetY = 0;

    if (imgEl && imgEl.naturalWidth > 0 && imgEl.naturalHeight > 0) {
      const imgAspect = imgEl.naturalWidth / imgEl.naturalHeight;
      const containerAspect = width / height;
      if (containerAspect > imgAspect) {
        // Pillarboxed: black bars on left & right
        renderW = height * imgAspect;
        renderH = height;
        offsetX = (width - renderW) / 2;
        offsetY = 0;
      } else {
        // Letterboxed: black bars on top & bottom
        renderW = width;
        renderH = width / imgAspect;
        offsetX = 0;
        offsetY = (height - renderH) / 2;
      }
    }

    for (const det of detections) {
      if (!det.bbox) continue;

      const { bbox, label, color = "#00FF00" } = det;
      // Correct coordinate mapping onto rendered image rectangle inside container
      const x = offsetX + Math.max(0, Math.min(renderW, bbox.x1 * renderW));
      const y = offsetY + Math.max(0, Math.min(renderH, bbox.y1 * renderH));
      const w = Math.max(0, Math.min(renderW - (x - offsetX), (bbox.x2 - bbox.x1) * renderW));
      const h = Math.max(0, Math.min(renderH - (y - offsetY), (bbox.y2 - bbox.y1) * renderH));

      if (w <= 0 || h <= 0) continue;

      // Fill semi-transparent interior
      ctx.fillStyle = parseHexToRgba(color, 0.15);
      ctx.fillRect(x, y, w, h);

      // Stroke bounding rectangle
      ctx.lineWidth = 2;
      ctx.strokeStyle = color;
      ctx.strokeRect(x, y, w, h);

      // Text label tag
      const displayLabel = (label || "OBJECT").toUpperCase();
      ctx.font = "bold 11px Inter, system-ui, -apple-system, sans-serif";
      const metrics = ctx.measureText(displayLabel);
      const padX = 6;
      const tagH = 18;
      const tagW = metrics.width + padX * 2;

      // Position badge on top of box or inside if too close to ceiling
      const tagY = y >= tagH ? y - tagH : y;

      ctx.fillStyle = color;
      ctx.fillRect(x, tagY, tagW, tagH);

      ctx.fillStyle = "#FFFFFF";
      ctx.fillText(displayLabel, x + padX, tagY + 13);
    }
  });

  return (
    <div
      ref={containerRef}
      className="camera-overlay-container"
      aria-label="Camera analytics overlay"
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
        overflow: "hidden",
      }}
    >
      <canvas
        ref={canvasRef}
        className="camera-canvas-overlay"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
        }}
      />
      {children}
    </div>
  );
}