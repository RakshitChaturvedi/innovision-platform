import { useRef, useEffect, useState, useCallback } from "react";
import type { ChangeEvent } from "react";
import { useSearchParams } from "react-router-dom";
import {
  SlidersHorizontal,
  Pencil,
  Minus,
  RotateCcw,
  Save,
  Info,
  Hexagon,
  Upload,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertCircle,
  Video,
} from "lucide-react";
import {
  getUC4Cameras,
  getCameraCalibration,
  saveCameraCalibration,
  uploadCameraVideo,
} from "../api";
import type {
  UC4Camera,
  NormalizedLine,
  NormalizedPoint,
} from "../types";

type Tool = "entry" | "exit" | "polygon" | "calibration" | null;
type DrawState = 0 | 1;

function getCanvasCoords(
  e: React.MouseEvent<HTMLCanvasElement>,
  canvas: HTMLCanvasElement,
): { normX: number; normY: number } {
  const rect = canvas.getBoundingClientRect();
  const intrinsicW = canvas.width;
  const intrinsicH = canvas.height;

  const displayRatio = rect.width / rect.height;
  const intrinsicRatio = intrinsicW / intrinsicH;

  let drawW: number;
  let drawH: number;
  let offX = 0;
  let offY = 0;

  if (displayRatio > intrinsicRatio) {
    drawH = rect.height;
    drawW = rect.height * intrinsicRatio;
    offX = (rect.width - drawW) / 2;
  } else {
    drawW = rect.width;
    drawH = rect.width / intrinsicRatio;
    offY = (rect.height - drawH) / 2;
  }

  const mouseX = e.clientX - rect.left - offX;
  const mouseY = e.clientY - rect.top - offY;

  return {
    normX: Math.max(0, Math.min(1, mouseX / drawW)),
    normY: Math.max(0, Math.min(1, mouseY / drawH)),
  };
}

function drawLine(
  ctx: CanvasRenderingContext2D,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  color: string,
  label?: string,
) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 3;
  ctx.setLineDash([]);
  ctx.stroke();

  // endpoints
  for (const [px, py] of [
    [x1, y1],
    [x2, y2],
  ]) {
    ctx.beginPath();
    ctx.arc(px, py, 7, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = "white";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // label
  if (label) {
    const midX = (x1 + x2) / 2;
    const midY = (y1 + y2) / 2;
    ctx.font = "bold 13px Inter, sans-serif";
    ctx.fillStyle = "white";
    ctx.strokeStyle = "rgba(0,0,0,0.8)";
    ctx.lineWidth = 4;
    ctx.strokeText(label, midX + 8, midY - 8);
    ctx.fillText(label, midX + 8, midY - 8);
  }
}

function drawPreviewLine(
  ctx: CanvasRenderingContext2D,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  color: string,
) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 4]);
  ctx.stroke();
  ctx.setLineDash([]);
}

function renderSyntheticRoadBackground(ctx: CanvasRenderingContext2D, w: number, h: number) {
  // Road surface
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, "#1a1e27");
  grad.addColorStop(1, "#0d1017");
  ctx.fillStyle = grad;
  ctx.fillRect(0, 0, w, h);

  // Perspective lane perspective lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
  ctx.lineWidth = 2;

  // Left road shoulder
  ctx.beginPath();
  ctx.moveTo(w * 0.35, h * 0.25);
  ctx.lineTo(w * 0.05, h * 0.95);
  ctx.stroke();

  // Right road shoulder
  ctx.beginPath();
  ctx.moveTo(w * 0.65, h * 0.25);
  ctx.lineTo(w * 0.95, h * 0.95);
  ctx.stroke();

  // Center dashed lane line
  ctx.setLineDash([16, 12]);
  ctx.strokeStyle = "rgba(234, 179, 8, 0.4)";
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.moveTo(w * 0.50, h * 0.25);
  ctx.lineTo(w * 0.50, h * 0.95);
  ctx.stroke();
  ctx.setLineDash([]);

  // Subtitle watermark
  ctx.fillStyle = "rgba(255, 255, 255, 0.25)";
  ctx.font = "12px monospace";
  ctx.fillText("SIMULATED ROAD CALIBRATION PLANE [OFFLINE PREVIEW]", 16, 24);
}

export function ConfiguratorPage() {
  const [searchParams] = useSearchParams();
  const preselectedCameraId = searchParams.get("camera");

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imageRef = useRef<HTMLImageElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [cameras, setCameras] = useState<UC4Camera[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [loadingCameras, setLoadingCameras] = useState(true);

  // Calibration state
  const [entryLine, setEntryLine] = useState<NormalizedLine | null>(null);
  const [exitLine, setExitLine] = useState<NormalizedLine | null>(null);
  const [speedPolygon, setSpeedPolygon] = useState<NormalizedPoint[]>([]);
  const [calibrationPolygon, setCalibrationPolygon] = useState<NormalizedPoint[]>([]);
  const [distance, setDistance] = useState<number>(15.0);
  const [speedLimit, setSpeedLimit] = useState<number>(20);

  // View toggles
  const [showEntryExit, setShowEntryExit] = useState(true);
  const [showPolygon, setShowPolygon] = useState(true);

  // Drawing tool state
  const [tool, setTool] = useState<Tool>(null);
  const [drawState, setDrawState] = useState<DrawState>(0);
  const [tempPoint, setTempPoint] = useState<{ x: number; y: number } | null>(null);
  const [tempPolygon, setTempPolygon] = useState<NormalizedPoint[]>([]);
  const [tempCalibration, setTempCalibration] = useState<NormalizedPoint[]>([]);
  const [previewPoint, setPreviewPoint] = useState<{ x: number; y: number } | null>(null);

  // Status & feedback
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Load cameras
  useEffect(() => {
    let mounted = true;
    getUC4Cameras()
      .then((cams) => {
        if (!mounted) return;
        setCameras(cams);
        if (preselectedCameraId && cams.some((c) => c.id === preselectedCameraId)) {
          setSelectedId(preselectedCameraId);
        } else if (cams.length > 0) {
          setSelectedId(cams[0].id);
        }
      })
      .finally(() => {
        if (mounted) setLoadingCameras(false);
      });

    return () => {
      mounted = false;
    };
  }, [preselectedCameraId]);

  const selectedCamera = cameras.find((c) => c.id === selectedId) ?? null;

  // Redraw canvas
  const redraw = useCallback(
    (
      img: HTMLImageElement | null,
      entry: NormalizedLine | null,
      exit: NormalizedLine | null,
      polygon: NormalizedPoint[],
      calibration: NormalizedPoint[],
      preview: { x: number; y: number } | null,
      anchor: { x: number; y: number } | null,
      tPolygon: NormalizedPoint[],
      tCalibration: NormalizedPoint[],
      activeTool?: Tool,
      sEntryExit?: boolean,
      sPolygon?: boolean,
    ) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      const w = canvas.width;
      const h = canvas.height;

      ctx.clearRect(0, 0, w, h);

      if (img && img.complete && img.naturalWidth > 0) {
        ctx.drawImage(img, 0, 0, w, h);
      } else {
        renderSyntheticRoadBackground(ctx, w, h);
      }

      // Helper to draw polygons
      const drawPoly = (
        points: NormalizedPoint[],
        isComplete: boolean,
        colorStr: string,
        fillColorStr: string,
      ) => {
        if (points.length === 0) return;
        ctx.beginPath();
        ctx.moveTo(points[0].x * w, points[0].y * h);
        for (let i = 1; i < points.length; i++) {
          ctx.lineTo(points[i].x * w, points[i].y * h);
        }

        if (isComplete) {
          ctx.closePath();
          ctx.fillStyle = fillColorStr;
          ctx.fill();
        }

        ctx.strokeStyle = colorStr;
        ctx.lineWidth = 2.5;
        ctx.stroke();

        for (const p of points) {
          ctx.beginPath();
          ctx.arc(p.x * w, p.y * h, 5, 0, Math.PI * 2);
          ctx.fillStyle = colorStr;
          ctx.fill();
          ctx.strokeStyle = "white";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }
      };

      // Speed ROI Polygon (Yellow)
      if (sPolygon && polygon.length >= 3) {
        drawPoly(polygon, true, "#eab308", "rgba(234, 179, 8, 0.2)");
      }

      // Temporary in-progress Speed ROI Polygon
      if (activeTool === "polygon" && tPolygon.length > 0) {
        drawPoly(tPolygon, false, "#eab308", "rgba(234, 179, 8, 0.2)");
        if (preview) {
          ctx.beginPath();
          const last = tPolygon[tPolygon.length - 1];
          ctx.moveTo(last.x * w, last.y * h);
          ctx.lineTo(preview.x * w, preview.y * h);
          ctx.strokeStyle = "#eab308";
          ctx.setLineDash([8, 4]);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      // Calibration Quad (Cyan)
      if (sPolygon && calibration.length === 4) {
        drawPoly(calibration, true, "#06b6d4", "rgba(6, 182, 212, 0.2)");
      }

      // In-progress Calibration Quad
      if (activeTool === "calibration" && tCalibration.length > 0) {
        drawPoly(tCalibration, false, "#06b6d4", "rgba(6, 182, 212, 0.2)");
        if (preview) {
          ctx.beginPath();
          const last = tCalibration[tCalibration.length - 1];
          ctx.moveTo(last.x * w, last.y * h);
          ctx.lineTo(preview.x * w, preview.y * h);
          ctx.strokeStyle = "#06b6d4";
          ctx.setLineDash([8, 4]);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }

      // Entry & Exit Lines
      if (sEntryExit && entry) {
        drawLine(
          ctx,
          entry.x1 * w,
          entry.y1 * h,
          entry.x2 * w,
          entry.y2 * h,
          "#22c55e",
          "ENTRY",
        );
      }

      if (sEntryExit && exit) {
        drawLine(
          ctx,
          exit.x1 * w,
          exit.y1 * h,
          exit.x2 * w,
          exit.y2 * h,
          "#ef4444",
          "EXIT",
        );
      }

      // Rubber-band line preview
      if (anchor && preview && (activeTool === "entry" || activeTool === "exit")) {
        const color = activeTool === "entry" ? "#22c55e" : "#ef4444";
        drawPreviewLine(
          ctx,
          anchor.x * w,
          anchor.y * h,
          preview.x * w,
          preview.y * h,
          color,
        );
      }
    },
    [],
  );

  // Load camera data when selectedId changes
  useEffect(() => {
    if (!selectedId) return;

    let active = true;
    setTool(null);
    setDrawState(0);
    setTempPoint(null);
    setPreviewPoint(null);
    setTempPolygon([]);
    setTempCalibration([]);
    setFeedbackMessage(null);
    setErrorMessage(null);

    getCameraCalibration(selectedId).then((cal) => {
      if (!active) return;
      if (cal) {
        setEntryLine(cal.entry_line ?? null);
        setExitLine(cal.exit_line ?? null);
        setSpeedPolygon(cal.speed_polygon_normalized ?? []);
        setCalibrationPolygon(cal.calibration_polygon_normalized ?? []);
        setDistance(cal.distance_between_lines_meters ?? 15.0);
        setSpeedLimit(cal.speed_limit_kmh ?? 20);
      } else {
        const cam = cameras.find((c) => c.id === selectedId);
        setEntryLine(cam?.entry_line ?? null);
        setExitLine(cam?.exit_line ?? null);
        setSpeedPolygon(cam?.speed_polygon_normalized ?? []);
        setCalibrationPolygon(cam?.calibration_polygon_normalized ?? []);
        setDistance(cam?.distance_between_lines_meters ?? 15.0);
        setSpeedLimit(cam?.speed_limit_kmh ?? 20);
      }
    });

    const canvas = canvasRef.current;
    if (canvas) {
      canvas.width = 960;
      canvas.height = 540;
    }

    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      if (!active) return;
      imageRef.current = img;
      if (canvas) {
        canvas.width = img.width || 960;
        canvas.height = img.height || 540;
      }
      redraw(
        img,
        entryLine,
        exitLine,
        speedPolygon,
        calibrationPolygon,
        null,
        null,
        [],
        [],
        null,
        showEntryExit,
        showPolygon,
      );
    };

    img.onerror = () => {
      if (!active) return;
      imageRef.current = null;
      redraw(
        null,
        entryLine,
        exitLine,
        speedPolygon,
        calibrationPolygon,
        null,
        null,
        [],
        [],
        null,
        showEntryExit,
        showPolygon,
      );
    };

    img.src = `/api/cameras/${selectedId}/frame?t=${Date.now()}`;

    return () => {
      active = false;
      img.onload = null;
      img.onerror = null;
      img.src = "";
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, cameras]);

  // Trigger redraw on state change
  useEffect(() => {
    redraw(
      imageRef.current,
      entryLine,
      exitLine,
      speedPolygon,
      calibrationPolygon,
      previewPoint,
      tempPoint,
      tempPolygon,
      tempCalibration,
      tool,
      showEntryExit,
      showPolygon,
    );
  }, [
    entryLine,
    exitLine,
    speedPolygon,
    calibrationPolygon,
    previewPoint,
    tempPoint,
    tempPolygon,
    tempCalibration,
    tool,
    showEntryExit,
    showPolygon,
    redraw,
  ]);

  // Canvas Mouse Events
  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!tool || !canvasRef.current) return;
    const { normX, normY } = getCanvasCoords(e, canvasRef.current);

    if (tool === "polygon") {
      setTempPolygon((prev) => [...prev, { x: normX, y: normY }]);
      return;
    }

    if (tool === "calibration") {
      const newCal = [...tempCalibration, { x: normX, y: normY }];
      if (newCal.length === 4) {
        setCalibrationPolygon(newCal);
        setTempCalibration([]);
        setTool(null);
        setPreviewPoint(null);
      } else {
        setTempCalibration(newCal);
      }
      return;
    }

    if (drawState === 0) {
      setTempPoint({ x: normX, y: normY });
      setDrawState(1);
    } else {
      if (tool === "entry") {
        setEntryLine({ x1: tempPoint!.x, y1: tempPoint!.y, x2: normX, y2: normY });
      } else if (tool === "exit") {
        setExitLine({ x1: tempPoint!.x, y1: tempPoint!.y, x2: normX, y2: normY });
      }
      setDrawState(0);
      setTempPoint(null);
      setPreviewPoint(null);
      setTool(null);
    }
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!tool || !canvasRef.current) return;
    if (tool === "polygon" && tempPolygon.length === 0) return;
    if (tool === "calibration" && tempCalibration.length === 0) return;
    if ((tool === "entry" || tool === "exit") && drawState !== 1) return;

    const { normX, normY } = getCanvasCoords(e, canvasRef.current);
    setPreviewPoint({ x: normX, y: normY });
  };

  // Video Upload
  const handleFileUpload = async (e: ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0 || !selectedId) return;
    const file = e.target.files[0];
    setUploading(true);
    setFeedbackMessage(null);
    try {
      await uploadCameraVideo(selectedId, file);
      setFeedbackMessage(`Uploaded video "${file.name}" for ${selectedCamera?.name}`);
    } catch {
      setErrorMessage("Video upload failed. Check file format.");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Save Configuration
  const handleSave = async () => {
    if (!selectedId) return;
    setSaving(true);
    setFeedbackMessage(null);
    setErrorMessage(null);
    try {
      await saveCameraCalibration(selectedId, {
        entry_line: entryLine,
        exit_line: exitLine,
        speed_polygon_normalized: speedPolygon.length >= 3 ? speedPolygon : null,
        calibration_polygon_normalized:
          calibrationPolygon.length === 4 ? calibrationPolygon : null,
        distance_between_lines_meters: distance,
        speed_limit_kmh: speedLimit,
      });
      setFeedbackMessage(
        `Configuration successfully saved for "${selectedCamera?.name || selectedId}". Speed polygon and tripwires active.`,
      );
    } catch {
      setErrorMessage("Failed to save calibration.");
    } finally {
      setSaving(false);
    }
  };

  // Reset Overlays
  const handleReset = () => {
    setEntryLine(null);
    setExitLine(null);
    setSpeedPolygon([]);
    setCalibrationPolygon([]);
    setTool(null);
    setDrawState(0);
    setTempPoint(null);
    setTempPolygon([]);
    setTempCalibration([]);
    setPreviewPoint(null);
    setFeedbackMessage("All tripwire and ROI overlays cleared. Click Save to persist.");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Page Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "12px" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: "36px",
                height: "36px",
                borderRadius: "8px",
                background: "rgba(13, 148, 136, 0.15)",
                color: "#0D9488",
              }}
            >
              <SlidersHorizontal size={20} />
            </span>
            <div>
              <h1 style={{ fontSize: "22px", fontWeight: 700, margin: 0, letterSpacing: "-0.01em" }}>
                Camera & Speed Configurator
              </h1>
              <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "3px 0 0" }}>
                Interactive canvas calibration for speed polygon, tripwires, and ANPR zone limits
              </p>
            </div>
          </div>
        </div>

        {feedbackMessage && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 14px",
              borderRadius: "6px",
              background: "rgba(70, 189, 146, 0.15)",
              border: "1px solid rgba(70, 189, 146, 0.3)",
              color: "var(--success)",
              fontSize: "12px",
            }}
          >
            <CheckCircle2 size={16} />
            <span>{feedbackMessage}</span>
          </div>
        )}

        {errorMessage && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              padding: "8px 14px",
              borderRadius: "6px",
              background: "var(--danger-bg)",
              border: "1px solid rgba(248, 113, 113, 0.3)",
              color: "var(--danger)",
              fontSize: "12px",
            }}
          >
            <AlertCircle size={16} />
            <span>{errorMessage}</span>
          </div>
        )}
      </div>

      {/* Main Split Layout */}
      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", gap: "20px", alignItems: "start" }}>
        {/* Left Sidebar Toolbar */}
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* Camera Selector Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "16px",
            }}
          >
            <label
              style={{
                display: "block",
                fontSize: "11px",
                fontWeight: 650,
                color: "var(--text-muted)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: "8px",
              }}
            >
              Select UC4 Camera
            </label>
            {loadingCameras ? (
              <div style={{ padding: "10px", fontSize: "12px", color: "var(--text-muted)" }}>
                Loading cameras...
              </div>
            ) : (
              <select
                value={selectedId}
                onChange={(e) => setSelectedId(e.target.value)}
                style={{
                  width: "100%",
                  height: "38px",
                  padding: "0 10px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                  outline: "none",
                }}
              >
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            )}

            {selectedCamera && (
              <div
                style={{
                  marginTop: "12px",
                  padding: "10px",
                  borderRadius: "6px",
                  background: "rgba(255, 255, 255, 0.02)",
                  border: "1px solid var(--border)",
                  fontSize: "11px",
                  color: "var(--text-secondary)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                  <span>Location:</span>
                  <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {selectedCamera.location || "Perimeter Lane"}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                  <span>Source:</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: "10px" }}>
                    {selectedCamera.video_source?.split("/").pop() || "demo.mp4"}
                  </span>
                </div>
                <input
                  type="file"
                  accept="video/mp4,video/*"
                  ref={fileInputRef}
                  style={{ display: "none" }}
                  onChange={handleFileUpload}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    padding: "6px 12px",
                    borderRadius: "4px",
                    border: "1px solid var(--border)",
                    background: "var(--surface-hover)",
                    color: "var(--text-primary)",
                    fontSize: "11px",
                    fontWeight: 550,
                  }}
                >
                  <Upload size={13} />
                  <span>{uploading ? "Uploading..." : "Upload New Video Source"}</span>
                </button>
              </div>
            )}
          </div>

          {/* Speed Calibration Settings Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "16px",
            }}
          >
            <label
              style={{
                display: "block",
                fontSize: "11px",
                fontWeight: 650,
                color: "var(--text-muted)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: "12px",
              }}
            >
              Speed & Zone Calibration
            </label>

            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              <div>
                <label style={{ display: "block", fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
                  Distance Between Lines (Meters)
                </label>
                <input
                  type="number"
                  step="0.5"
                  min="1"
                  value={distance}
                  onChange={(e) => setDistance(parseFloat(e.target.value) || 0)}
                  style={{
                    width: "100%",
                    height: "34px",
                    padding: "0 10px",
                    borderRadius: "6px",
                    border: "1px solid var(--border)",
                    background: "var(--surface-raised)",
                    color: "var(--text-primary)",
                    fontSize: "13px",
                  }}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
                  Speed Limit Threshold (km/h)
                </label>
                <input
                  type="number"
                  step="5"
                  min="5"
                  value={speedLimit}
                  onChange={(e) => setSpeedLimit(parseInt(e.target.value, 10) || 20)}
                  style={{
                    width: "100%",
                    height: "34px",
                    padding: "0 10px",
                    borderRadius: "6px",
                    border: "1px solid var(--border)",
                    background: "var(--surface-raised)",
                    color: "var(--text-primary)",
                    fontSize: "13px",
                  }}
                />
              </div>

              {/* View Toggles */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px", marginTop: "4px" }}>
                <button
                  type="button"
                  onClick={() => setShowEntryExit(!showEntryExit)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    padding: "6px 8px",
                    borderRadius: "6px",
                    border: `1px solid ${showEntryExit ? "#0D9488" : "var(--border)"}`,
                    background: showEntryExit ? "rgba(13, 148, 136, 0.15)" : "var(--surface-raised)",
                    color: showEntryExit ? "#0D9488" : "var(--text-muted)",
                    fontSize: "11px",
                    fontWeight: 600,
                  }}
                >
                  {showEntryExit ? <Eye size={13} /> : <EyeOff size={13} />}
                  <span>Tripwires</span>
                </button>
                <button
                  type="button"
                  onClick={() => setShowPolygon(!showPolygon)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    padding: "6px 8px",
                    borderRadius: "6px",
                    border: `1px solid ${showPolygon ? "#eab308" : "var(--border)"}`,
                    background: showPolygon ? "rgba(234, 179, 8, 0.15)" : "var(--surface-raised)",
                    color: showPolygon ? "#eab308" : "var(--text-muted)",
                    fontSize: "11px",
                    fontWeight: 600,
                  }}
                >
                  {showPolygon ? <Eye size={13} /> : <EyeOff size={13} />}
                  <span>Speed Poly</span>
                </button>
              </div>
            </div>
          </div>

          {/* Interactive Drawing Tools */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "16px",
            }}
          >
            <label
              style={{
                display: "block",
                fontSize: "11px",
                fontWeight: 650,
                color: "var(--text-muted)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: "10px",
              }}
            >
              Drawing Tools
            </label>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              {/* Draw Entry Line */}
              <button
                type="button"
                onClick={() => {
                  setTool("entry");
                  setDrawState(0);
                  setTempPoint(null);
                  setTempPolygon([]);
                  setTempCalibration([]);
                  setShowEntryExit(true);
                }}
                disabled={!selectedId}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  border: `1px solid ${tool === "entry" ? "#22c55e" : "var(--border)"}`,
                  background: tool === "entry" ? "rgba(34, 197, 94, 0.15)" : "var(--surface-raised)",
                  color: tool === "entry" ? "#22c55e" : "var(--text-primary)",
                  fontSize: "12px",
                  fontWeight: 600,
                  textAlign: "left",
                }}
              >
                <Pencil size={15} />
                <span>Draw Entry Line (Green)</span>
              </button>

              {/* Draw Exit Line */}
              <button
                type="button"
                onClick={() => {
                  setTool("exit");
                  setDrawState(0);
                  setTempPoint(null);
                  setTempPolygon([]);
                  setTempCalibration([]);
                  setShowEntryExit(true);
                }}
                disabled={!selectedId}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  border: `1px solid ${tool === "exit" ? "#ef4444" : "var(--border)"}`,
                  background: tool === "exit" ? "rgba(239, 68, 68, 0.15)" : "var(--surface-raised)",
                  color: tool === "exit" ? "#ef4444" : "var(--text-primary)",
                  fontSize: "12px",
                  fontWeight: 600,
                  textAlign: "left",
                }}
              >
                <Minus size={15} />
                <span>Draw Exit Line (Red)</span>
              </button>

              {/* Speed ROI Polygon */}
              <button
                type="button"
                onClick={() => {
                  setTool("polygon");
                  setDrawState(0);
                  setTempPoint(null);
                  setTempPolygon([]);
                  setTempCalibration([]);
                  setShowPolygon(true);
                }}
                disabled={!selectedId}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  border: `1px solid ${tool === "polygon" ? "#eab308" : "var(--border)"}`,
                  background: tool === "polygon" ? "rgba(234, 179, 8, 0.15)" : "var(--surface-raised)",
                  color: tool === "polygon" ? "#eab308" : "var(--text-primary)",
                  fontSize: "12px",
                  fontWeight: 600,
                  textAlign: "left",
                }}
              >
                <Hexagon size={15} />
                <span>Speed ROI Polygon (Yellow)</span>
              </button>

              {tool === "polygon" && tempPolygon.length >= 3 && (
                <button
                  type="button"
                  onClick={() => {
                    setSpeedPolygon(tempPolygon);
                    setTempPolygon([]);
                    setTool(null);
                    setPreviewPoint(null);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    padding: "8px 12px",
                    borderRadius: "6px",
                    border: "1px solid #22c55e",
                    background: "rgba(34, 197, 94, 0.2)",
                    color: "#22c55e",
                    fontSize: "12px",
                    fontWeight: 650,
                  }}
                >
                  <CheckCircle2 size={15} />
                  <span>Finish Polygon ({tempPolygon.length} Points)</span>
                </button>
              )}

              {/* Calibration Quad */}
              <button
                type="button"
                onClick={() => {
                  setTool("calibration");
                  setDrawState(0);
                  setTempPoint(null);
                  setTempPolygon([]);
                  setTempCalibration([]);
                  setShowPolygon(true);
                }}
                disabled={!selectedId}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  border: `1px solid ${tool === "calibration" ? "#06b6d4" : "var(--border)"}`,
                  background: tool === "calibration" ? "rgba(6, 182, 212, 0.15)" : "var(--surface-raised)",
                  color: tool === "calibration" ? "#06b6d4" : "var(--text-primary)",
                  fontSize: "12px",
                  fontWeight: 600,
                  textAlign: "left",
                }}
              >
                <Hexagon size={15} />
                <span>Calibration Box (4pt Cyan)</span>
              </button>

              {/* Reset Overlays */}
              <button
                type="button"
                onClick={handleReset}
                disabled={!selectedId}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  padding: "8px 12px",
                  marginTop: "6px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "transparent",
                  color: "var(--text-muted)",
                  fontSize: "12px",
                  fontWeight: 500,
                }}
              >
                <RotateCcw size={14} />
                <span>Clear All Overlays</span>
              </button>
            </div>
          </div>

          {/* Status Overview Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "16px",
              fontSize: "12px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontWeight: 650, color: "var(--text-primary)", marginBottom: "10px" }}>
              <Info size={14} />
              <span>OVERLAY STATUS</span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "8px", color: "var(--text-secondary)" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Entry Line:</span>
                <span style={{ fontWeight: 600, color: entryLine ? "#22c55e" : "var(--text-muted)" }}>
                  {entryLine ? "✓ Set" : "Not set"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Exit Line:</span>
                <span style={{ fontWeight: 600, color: exitLine ? "#ef4444" : "var(--text-muted)" }}>
                  {exitLine ? "✓ Set" : "Not set"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Speed Polygon:</span>
                <span style={{ fontWeight: 600, color: speedPolygon.length >= 3 ? "#eab308" : "var(--text-muted)" }}>
                  {speedPolygon.length >= 3 ? `✓ Set (${speedPolygon.length} pts)` : "Not set"}
                </span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span>Calibration Quad:</span>
                <span style={{ fontWeight: 600, color: calibrationPolygon.length === 4 ? "#06b6d4" : "var(--text-muted)" }}>
                  {calibrationPolygon.length === 4 ? "✓ Set (4 pts)" : "Not set"}
                </span>
              </div>
            </div>

            {tool && (
              <div
                style={{
                  marginTop: "12px",
                  padding: "8px 10px",
                  borderRadius: "6px",
                  background: "rgba(13, 148, 136, 0.15)",
                  color: "#0D9488",
                  fontSize: "11px",
                  fontWeight: 600,
                  lineHeight: 1.4,
                }}
              >
                {tool === "polygon"
                  ? `Click canvas to place point ${tempPolygon.length + 1}. Minimum 3 points required.`
                  : tool === "calibration"
                    ? `Click point ${tempCalibration.length + 1} of 4 for perspective quad.`
                    : drawState === 0
                      ? `Click canvas to start ${tool} line.`
                      : `Click again to complete ${tool} line.`}
              </div>
            )}
          </div>

          {/* Save Button */}
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !selectedId}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "8px",
              padding: "12px 16px",
              borderRadius: "8px",
              border: "none",
              background: "#0D9488",
              color: "#ffffff",
              fontSize: "13px",
              fontWeight: 700,
              boxShadow: "0 2px 8px rgba(13, 148, 136, 0.25)",
              cursor: saving || !selectedId ? "not-allowed" : "pointer",
              opacity: saving || !selectedId ? 0.6 : 1,
            }}
          >
            <Save size={16} />
            <span>{saving ? "Saving Configuration..." : "Save Configuration"}</span>
          </button>
        </div>

        {/* Right Canvas Interactive Viewport */}
        <div
          style={{
            background: "#07080b",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            overflow: "hidden",
            position: "relative",
            minHeight: "560px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <canvas
            ref={canvasRef}
            style={{
              maxWidth: "100%",
              maxHeight: "100%",
              objectFit: "contain",
              cursor: tool ? "crosshair" : "default",
              display: "block",
            }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
          />

          {/* Interactive HUD overlay badge */}
          <div
            style={{
              position: "absolute",
              top: "16px",
              left: "16px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              background: "rgba(15, 17, 23, 0.85)",
              border: "1px solid var(--border)",
              padding: "6px 12px",
              borderRadius: "6px",
              backdropFilter: "blur(6px)",
              fontSize: "11px",
              color: "var(--text-secondary)",
            }}
          >
            <Video size={14} color="#0D9488" />
            <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
              {selectedCamera?.name || "Active Camera"}
            </span>
            <span>•</span>
            <span>Limit: {speedLimit} km/h</span>
            <span>•</span>
            <span>Span: {distance}m</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ConfiguratorPage;
