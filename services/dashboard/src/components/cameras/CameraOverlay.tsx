import { useEffect, useRef, type ReactNode } from "react";
import { getUCModule, getEnabledUCModules } from "@/modules/registry";

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

export interface ZonePolygonItem {
  zone_id: string;
  zone_name: string;
  priority?: string;
  is_deliberate?: boolean;
  color?: string;
  polygon: Array<[number, number]>;
}

export interface LatestDetectionsResponse {
  timestamp: string;
  camera_id: string;
  frame_seq?: number;
  detections: DetectionItem[];
  zones?: ZonePolygonItem[];
}

export interface CameraOverlayProps {
  cameraId: string;
  useCases?: string[];
  isOnline?: boolean;
  children?: ReactNode;
}

interface TrackedDetection {
  key: string;
  trackId?: number | string;
  label: string;
  color: string;
  targetBbox: DetectionBBox;
  currentBbox: DetectionBBox;
  lastSeen: number;
  metadata?: Record<string, unknown>;
}

// Detection persistence timing
const PERSISTENCE_TTL_MS = 500; // Keep detection alive for 500ms after last positive poll
const FADE_START_MS = 250;      // Start smooth fade-out after 250ms without update
const LERP_FACTOR = 0.35;        // Smooth bbox interpolation factor per animation frame
const POLL_INTERVAL_MS = 100;    // Poll interval (~10 FPS matches standard CV inference)

function parseHexToRgba(hex: string, alpha: number): string {
  if (!hex || !hex.startsWith("#")) {
    return hex || `rgba(0, 255, 0, ${alpha})`;
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
  return `rgba(${r}, ${g}, ${b}, ${Math.max(0, Math.min(1, alpha))})`;
}

function computeIoU(boxA: DetectionBBox, boxB: DetectionBBox): number {
  const xA = Math.max(boxA.x1, boxB.x1);
  const yA = Math.max(boxA.y1, boxB.y1);
  const xB = Math.min(boxA.x2, boxB.x2);
  const yB = Math.min(boxA.y2, boxB.y2);

  const interArea = Math.max(0, xB - xA) * Math.max(0, yB - yA);
  const boxAArea = Math.max(1e-5, (boxA.x2 - boxA.x1) * (boxA.y2 - boxA.y1));
  const boxBArea = Math.max(1e-5, (boxB.x2 - boxB.x1) * (boxB.y2 - boxB.y1));

  return interArea / (boxAArea + boxBArea - interArea);
}

/**
 * Dynamically resolves detection endpoints driven purely by the UC module registry.
 * Zero hardcoded UC branching.
 */
function resolveEndpoints(cameraId: string, useCases: string[] = []): string[] {
  const normalized = useCases.map((u) => u.toLowerCase().trim());
  const urls: string[] = [];

  for (const ucId of normalized) {
    const mod = getUCModule(ucId);
    if (mod && mod.overlayBaseUrl) {
      urls.push(`${mod.overlayBaseUrl}/${mod.id}/cameras/${cameraId}/latest-detections`);
    }
  }

  // Fallback to all enabled modules in the registry if camera has no specific use cases
  if (urls.length === 0) {
    const enabledMods = getEnabledUCModules();
    for (const mod of enabledMods) {
      urls.push(`${mod.overlayBaseUrl}/${mod.id}/cameras/${cameraId}/latest-detections`);
    }
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
  const trackedMapRef = useRef<Map<string, TrackedDetection>>(new Map());
  const isFetchingRef = useRef<boolean>(false);
  const zonesRef = useRef<ZonePolygonItem[]>([]);

  // ── 1. HTTP Polling Loop with In-Flight Guard & Persistence Ingestion ──
  useEffect(() => {
    if (!isOnline || !cameraId) {
      trackedMapRef.current.clear();
      return;
    }

    let isMounted = true;
    const abortController = new AbortController();

    const pollDetections = async () => {
      if (isFetchingRef.current || !isMounted) return;
      isFetchingRef.current = true;

      const endpoints = resolveEndpoints(cameraId, useCases);

      try {
        const fetchPromises = endpoints.map((url) =>
          fetch(url, { signal: abortController.signal })
            .then((res) => (res.ok ? res.json() : null))
            .catch(() => null),
        );

        const results = await Promise.all(fetchPromises);
        if (!isMounted) return;

        const now = Date.now();
        const incomingDetections: DetectionItem[] = [];
        const incomingZones: ZonePolygonItem[] = [];

        for (const res of results as (LatestDetectionsResponse | null)[]) {
          if (!res) continue;
          if (Array.isArray(res.detections)) {
            incomingDetections.push(...res.detections);
          }
          if (Array.isArray(res.zones)) {
            incomingZones.push(...res.zones);
          }
        }

        zonesRef.current = incomingZones;

        // Match incoming detections with persistent tracked map
        const tracked = trackedMapRef.current;
        const matchedKeys = new Set<string>();

        for (let i = 0; i < incomingDetections.length; i++) {
          const item = incomingDetections[i];
          let matchedKey: string | null = null;

          if (item.track_id !== undefined && item.track_id !== null) {
            const explicitKey = `track_${item.track_id}`;
            if (tracked.has(explicitKey)) {
              matchedKey = explicitKey;
            } else {
              matchedKey = explicitKey;
            }
          } else {
            // Match by IoU proximity with existing active detections
            let bestIoU = 0.3;
            for (const [key, existing] of tracked.entries()) {
              if (matchedKeys.has(key)) continue;
              const iou = computeIoU(existing.targetBbox, item.bbox);
              if (iou > bestIoU) {
                bestIoU = iou;
                matchedKey = key;
              }
            }
            if (!matchedKey) {
              matchedKey = `box_${now}_${i}`;
            }
          }

          matchedKeys.add(matchedKey);
          const existing = tracked.get(matchedKey);

          if (existing) {
            existing.targetBbox = item.bbox;
            existing.label = item.label;
            existing.color = item.color || existing.color;
            existing.lastSeen = now;
            existing.metadata = item.metadata;
          } else {
            tracked.set(matchedKey, {
              key: matchedKey,
              trackId: item.track_id,
              label: item.label,
              color: item.color || "#00FF00",
              targetBbox: item.bbox,
              currentBbox: { ...item.bbox },
              lastSeen: now,
              metadata: item.metadata,
            });
          }
        }
      } catch {
        // Network errors handled gracefully without UI crashing
      } finally {
        isFetchingRef.current = false;
      }
    };

    const intervalId = setInterval(pollDetections, POLL_INTERVAL_MS);
    pollDetections();

    return () => {
      isMounted = false;
      clearInterval(intervalId);
      abortController.abort();
    };
  }, [cameraId, isOnline, useCases]);

  // ── 2. requestAnimationFrame Rendering Loop (Smooth 60fps Interpolation & Decoupled Drawing) ──
  useEffect(() => {
    let animId: number;

    const render = () => {
      const canvas = canvasRef.current;
      const container = containerRef.current;
      if (!canvas || !container) {
        animId = requestAnimationFrame(render);
        return;
      }

      // Sync canvas dimensions with parent container
      const rect = container.getBoundingClientRect();
      const width = Math.floor(rect.width);
      const height = Math.floor(rect.height);

      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      const ctx = canvas.getContext("2d");
      if (!ctx || width === 0 || height === 0) {
        animId = requestAnimationFrame(render);
        return;
      }

      ctx.clearRect(0, 0, width, height);

      const now = Date.now();
      const tracked = trackedMapRef.current;

      // ── A. Render Zone Polygons (ROI) ──
      for (const zone of zonesRef.current) {
        if (!zone.polygon || zone.polygon.length < 3) continue;

        const zoneColor = zone.color || "#EF4444";
        ctx.beginPath();
        const startX = zone.polygon[0][0] * width;
        const startY = zone.polygon[0][1] * height;
        ctx.moveTo(startX, startY);

        for (let p = 1; p < zone.polygon.length; p++) {
          ctx.lineTo(zone.polygon[p][0] * width, zone.polygon[p][1] * height);
        }
        ctx.closePath();

        ctx.fillStyle = parseHexToRgba(zoneColor, 0.12);
        ctx.fill();

        ctx.lineWidth = 1.5;
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = parseHexToRgba(zoneColor, 0.6);
        ctx.stroke();
        ctx.setLineDash([]);

        // Zone Tag
        if (zone.zone_name) {
          ctx.font = "bold 10px monospace";
          ctx.fillStyle = zoneColor;
          ctx.fillText(`⬡ ${zone.zone_name}`, startX + 4, Math.max(14, startY - 4));
        }
      }

      // ── B. Render Tracked Detections (Smooth Interpolation & Fade-out) ──
      for (const [key, item] of Array.from(tracked.entries())) {
        const age = now - item.lastSeen;

        // Purge expired detections
        if (age > PERSISTENCE_TTL_MS) {
          tracked.delete(key);
          continue;
        }

        // Compute opacity
        let opacity = 1.0;
        if (age > FADE_START_MS) {
          opacity = 1.0 - (age - FADE_START_MS) / (PERSISTENCE_TTL_MS - FADE_START_MS);
          opacity = Math.max(0, Math.min(1, opacity));
        }

        // Lerp coordinates
        const cur = item.currentBbox;
        const tgt = item.targetBbox;
        cur.x1 += (tgt.x1 - cur.x1) * LERP_FACTOR;
        cur.y1 += (tgt.y1 - cur.y1) * LERP_FACTOR;
        cur.x2 += (tgt.x2 - cur.x2) * LERP_FACTOR;
        cur.y2 += (tgt.y2 - cur.y2) * LERP_FACTOR;

        // Convert normalized coordinates to pixel coords
        const px1 = Math.max(0, Math.min(width, cur.x1 * width));
        const py1 = Math.max(0, Math.min(height, cur.y1 * height));
        const px2 = Math.max(0, Math.min(width, cur.x2 * width));
        const py2 = Math.max(0, Math.min(height, cur.y2 * height));
        const bw = px2 - px1;
        const bh = py2 - py1;

        if (bw <= 0 || bh <= 0) continue;

        const mainColor = item.color || "#00FF00";

        // Bounding Box Background
        ctx.fillStyle = parseHexToRgba(mainColor, 0.12 * opacity);
        ctx.fillRect(px1, py1, bw, bh);

        // Bounding Box Outline
        ctx.strokeStyle = parseHexToRgba(mainColor, 0.85 * opacity);
        ctx.lineWidth = 2;
        ctx.strokeRect(px1, py1, bw, bh);

        // Corner Accents
        const cornerLen = Math.min(12, Math.max(6, Math.min(bw, bh) * 0.25));
        ctx.lineWidth = 3;
        ctx.strokeStyle = parseHexToRgba(mainColor, 1.0 * opacity);

        // Top-Left Corner
        ctx.beginPath();
        ctx.moveTo(px1, py1 + cornerLen);
        ctx.lineTo(px1, py1);
        ctx.lineTo(px1 + cornerLen, py1);
        ctx.stroke();

        // Top-Right Corner
        ctx.beginPath();
        ctx.moveTo(px2 - cornerLen, py1);
        ctx.lineTo(px2, py1);
        ctx.lineTo(px2, py1 + cornerLen);
        ctx.stroke();

        // Bottom-Left Corner
        ctx.beginPath();
        ctx.moveTo(px1, py2 - cornerLen);
        ctx.lineTo(px1, py2);
        ctx.lineTo(px1 + cornerLen, py2);
        ctx.stroke();

        // Bottom-Right Corner
        ctx.beginPath();
        ctx.moveTo(px2 - cornerLen, py2);
        ctx.lineTo(px2, py2);
        ctx.lineTo(px2, py2 - cornerLen);
        ctx.stroke();

        // Label Pill
        const labelText = item.label ? item.label.toUpperCase() : "DETECTED";
        ctx.font = "bold 11px monospace";
        const textMetrics = ctx.measureText(labelText);
        const textW = textMetrics.width;
        const pillH = 18;
        const pillW = textW + 12;
        const pillX = px1;
        const pillY = Math.max(0, py1 - pillH);

        ctx.fillStyle = parseHexToRgba(mainColor, 0.9 * opacity);
        ctx.fillRect(pillX, pillY, pillW, pillH);

        ctx.fillStyle = "#FFFFFF";
        ctx.fillText(labelText, pillX + 6, pillY + 13);
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animId);
  }, []);

  return (
    <div
      ref={containerRef}
      className="camera-overlay-container"
      style={{
        position: "absolute",
        top: 0,
        left: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
        zIndex: 5,
      }}
    >
      <canvas
        ref={canvasRef}
        style={{
          width: "100%",
          height: "100%",
          display: "block",
        }}
      />
      {children}
    </div>
  );
}