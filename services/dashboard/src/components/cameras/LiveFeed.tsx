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
  compliant?: boolean;
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
  const [activeToast, setActiveToast] = useState<{ id: string; title: string; subtitle: string } | null>(null);

  const containerRef = useRef<HTMLDivElement>(null);
  const imgRef = useRef<HTMLImageElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

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

            // Check for violations to trigger toast alert banner
            const violation = data.detections.find(
              (d: DetectionItem) =>
                d.compliant === false ||
                d.label.toLowerCase().includes("missing") ||
                d.label.toLowerCase().startsWith("no-")
            );
            if (violation) {
              setActiveToast({
                id: Date.now().toString(),
                title: "Safety Violation Alert",
                subtitle: `${cameraName} — ${violation.label}`,
              });
            }
          }
        }
      } catch {
        // Fallback or handle offline
      }
    };

    fetchDetections();
    const interval = setInterval(fetchDetections, 300);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [cameraId, isOnline, cameraName]);

  // Auto-dismiss toast alert after 4 seconds
  useEffect(() => {
    if (!activeToast) return;
    const t = setTimeout(() => {
      setActiveToast(null);
    }, 4000);
    return () => clearTimeout(t);
  }, [activeToast]);

  // Canvas drawing for crisp HiDPI bounding boxes with rounded pill labels & red attention outlines
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || containerDim.w === 0 || containerDim.h === 0) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(containerDim.w * dpr);
    canvas.height = Math.round(containerDim.h * dpr);
    canvas.style.width = `${containerDim.w}px`;
    canvas.style.height = `${containerDim.h}px`;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, containerDim.w, containerDim.h);

    if (!isOnline || detections.length === 0) return;

    const cw = containerDim.w;
    const ch = containerDim.h;
    const containerRatio = cw / ch;

    let renderedW = cw;
    let renderedH = ch;
    let offsetX = 0;
    let offsetY = 0;

    if (containerRatio > imageRatio) {
      renderedH = ch;
      renderedW = ch * imageRatio;
      offsetX = (cw - renderedW) / 2;
    } else {
      renderedW = cw;
      renderedH = cw / imageRatio;
      offsetY = (ch - renderedH) / 2;
    }

    const CLASS_COLORS: Record<string, string> = {
      helmet: "#FFC53D",
      "hard-hat": "#FFC53D",
      hardhat: "#FFC53D",
      vest: "#FF8A3D",
      "safety-vest": "#FF8A3D",
      safety_vest: "#FF8A3D",
      gloves: "#4ADE80",
      glove: "#4ADE80",
      shoe: "#38BDF8",
      shoes: "#38BDF8",
      boots: "#38BDF8",
      boot: "#38BDF8",
      glasses: "#F472B6",
      goggles: "#F472B6",
      mask: "#2DD4BF",
      "face-mask": "#2DD4BF",
      person: "#94A3B8",
      worker: "#94A3B8",
    };

    detections.forEach((det) => {
      let x1 = 0, y1 = 0, x2 = 0, y2 = 0;
      if (Array.isArray(det.box)) {
        [x1, y1, x2, y2] = det.box as unknown as number[];
      } else if (det.box && typeof det.box === "object") {
        x1 = det.box.x1;
        y1 = det.box.y1;
        x2 = det.box.x2;
        y2 = det.box.y2;
      }

      const bx = offsetX + x1 * renderedW;
      const by = offsetY + y1 * renderedH;
      const bw = (x2 - x1) * renderedW;
      const bh = (y2 - y1) * renderedH;

      const lower = det.label.toLowerCase();
      const isViolation =
        det.compliant === false ||
        lower.includes("missing") ||
        lower.startsWith("no-") ||
        lower.startsWith("no_") ||
        det.color === "#FF3333";

      let col = isViolation ? "#FF3333" : det.color;
      if (!col) {
        for (const [k, c] of Object.entries(CLASS_COLORS)) {
          if (lower.includes(k)) {
            col = c;
            break;
          }
        }
      }
      col = col || "#38BDF8";

      // Main box outline with shadow
      ctx.shadowColor = "rgba(0,0,0,0.6)";
      ctx.shadowBlur = 4;
      ctx.strokeStyle = col;
      ctx.lineWidth = 2;
      ctx.strokeRect(bx, by, bw, bh);
      ctx.shadowBlur = 0;

      // Violation outer dashed attention outline
      if (isViolation) {
        ctx.save();
        ctx.setLineDash([5, 3]);
        ctx.strokeStyle = "#FF3333";
        ctx.lineWidth = 2;
        ctx.strokeRect(bx - 3, by - 3, bw + 6, bh + 6);
        ctx.restore();
      }

      // Rounded pill label
      const labelText = det.label;
      const metrics = ctx.measureText(labelText);
      const pillW = metrics.width + 12;
      const pillH = 18;
      const pillY = by >= pillH + 3 ? by - pillH - 3 : by + 3;

      ctx.fillStyle = `${col}ee`;
      const r = 4;
      ctx.beginPath();
      ctx.moveTo(bx + r, pillY);
      ctx.lineTo(bx + pillW - r, pillY);
      ctx.quadraticCurveTo(bx + pillW, pillY, bx + pillW, pillY + r);
      ctx.lineTo(bx + pillW, pillY + pillH - r);
      ctx.quadraticCurveTo(bx + pillW, pillY + pillH, bx + pillW - r, pillY + pillH);
      ctx.lineTo(bx + r, pillY + pillH);
      ctx.quadraticCurveTo(bx, pillY + pillH, bx, pillY + pillH - r);
      ctx.lineTo(bx, pillY + r);
      ctx.quadraticCurveTo(bx, pillY, bx + r, pillY);
      ctx.closePath();
      ctx.fill();

      // Label text
      ctx.fillStyle = "#ffffff";
      ctx.fillText(labelText, bx + 6, pillY + 13);
    });
  }, [detections, containerDim, imageRatio, isOnline]);

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

      {/* HiDPI Canvas Overlay for sharp bounding boxes and attention rings */}
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
          zIndex: 10,
        }}
      />

      {/* Floating toast alert banner for violations */}
      {activeToast && (
        <div
          role="alert"
          style={{
            position: "absolute",
            top: "16px",
            right: "16px",
            backgroundColor: "rgba(28, 16, 12, 0.95)",
            border: "1.5px solid #FF8A3D",
            borderRadius: "8px",
            padding: "10px 16px",
            boxShadow: "0 6px 16px rgba(0,0,0,0.6)",
            color: "#fff",
            zIndex: 30,
            display: "flex",
            alignItems: "center",
            gap: "12px",
            pointerEvents: "none",
            transition: "all 0.3s ease-out",
          }}
        >
          <span style={{ fontSize: "20px" }}>⚠️</span>
          <div>
            <div style={{ fontWeight: "bold", fontSize: "11px", color: "#FF8A3D", textTransform: "uppercase", letterSpacing: "0.5px" }}>
              {activeToast.title}
            </div>
            <div style={{ fontSize: "13px", fontWeight: "500", marginTop: "2px" }}>
              {activeToast.subtitle}
            </div>
          </div>
        </div>
      )}

      <CameraOverlay>{overlay}</CameraOverlay>
    </section>
  );
}