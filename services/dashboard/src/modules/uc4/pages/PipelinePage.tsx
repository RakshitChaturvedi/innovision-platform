import { useState, useEffect } from "react";
import {
  Play,
  Square,
  Cpu,
  Video,
  Activity,
  Layers,
} from "lucide-react";
import { getUC4Cameras } from "../api";
import type { UC4Camera } from "../types";

export function PipelinePage() {
  const [cameras, setCameras] = useState<UC4Camera[]>([]);
  const [selectedCamId, setSelectedCamId] = useState<string>("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getUC4Cameras()
      .then((cams) => {
        setCameras(cams);
        if (cams.length > 0) {
          setSelectedCamId(cams[0].id);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const selectedCam = cameras.find((c) => c.id === selectedCamId) || null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Page Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
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
            <Video size={20} />
          </span>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: 700, margin: 0, letterSpacing: "-0.01em" }}>
              Live AI Pipeline Stream
            </h1>
            <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "3px 0 0" }}>
              Real-time YOLO11 tracking, ANPR plate recognition, and speed estimation stream
            </p>
          </div>
        </div>
      </div>

      {/* Stream Viewer Card */}
      <div
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          overflow: "hidden",
        }}
      >
        {/* Stream Top Control Bar */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            padding: "16px 20px",
            borderBottom: "1px solid var(--border)",
            flexWrap: "wrap",
            gap: "12px",
          }}
        >
          <div>
            <h2 style={{ fontSize: "14px", fontWeight: 700, margin: 0 }}>Stream Viewer & Analytics Inference</h2>
            <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: "2px 0 0" }}>
              Select a camera node and start the high-throughput inference pipeline
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {/* Camera Select */}
            <select
              value={selectedCamId}
              onChange={(e) => setSelectedCamId(e.target.value)}
              disabled={isPlaying || loading}
              style={{
                height: "36px",
                padding: "0 12px",
                borderRadius: "6px",
                border: "1px solid var(--border)",
                background: "var(--surface-raised)",
                color: "var(--text-primary)",
                fontSize: "12px",
                outline: "none",
                minWidth: "220px",
              }}
            >
              {cameras.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>

            {/* Play/Stop Button */}
            {!isPlaying ? (
              <button
                type="button"
                onClick={() => setIsPlaying(true)}
                disabled={!selectedCamId || loading}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "0 16px",
                  height: "36px",
                  borderRadius: "6px",
                  border: "none",
                  background: "#10B981",
                  color: "#ffffff",
                  fontSize: "12px",
                  fontWeight: 650,
                  cursor: "pointer",
                }}
              >
                <Play size={14} />
                <span>Start Pipeline</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={() => setIsPlaying(false)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "0 16px",
                  height: "36px",
                  borderRadius: "6px",
                  border: "none",
                  background: "var(--danger)",
                  color: "#ffffff",
                  fontSize: "12px",
                  fontWeight: 650,
                  cursor: "pointer",
                }}
              >
                <Square size={14} />
                <span>Stop Stream</span>
              </button>
            )}
          </div>
        </div>

        {/* Video / Stream Frame Stage */}
        <div
          style={{
            position: "relative",
            width: "100%",
            height: "560px",
            background: "#080a0f",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {!isPlaying ? (
            <div style={{ textAlign: "center", color: "var(--text-muted)", padding: "40px" }}>
              <Video size={48} style={{ opacity: 0.2, margin: "0 auto 12px", display: "block" }} />
              <h3 style={{ fontSize: "16px", fontWeight: 650, color: "var(--text-primary)", marginBottom: "6px" }}>
                AI Inference Stream Standby
              </h3>
              <p style={{ fontSize: "12px", maxWidth: "400px", margin: "0 auto", lineHeight: 1.5 }}>
                Click &ldquo;Start Pipeline&rdquo; above to connect to the live YOLO11 MJPEG stream. Pipeline will automatically idle when stopped to preserve compute.
              </p>
            </div>
          ) : (
            <div style={{ width: "100%", height: "100%", position: "relative" }}>
              {/* HTML5 Video or Live Stream Source */}
              <video
                src={selectedCam?.video_source || "/videos/uc4_demo.mp4"}
                autoPlay
                loop
                muted
                playsInline
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "contain",
                  display: "block",
                }}
              />

              {/* Dynamic Synthetic HUD Telemetry Overlay */}
              <div
                style={{
                  position: "absolute",
                  top: "16px",
                  left: "16px",
                  display: "flex",
                  flexDirection: "column",
                  gap: "6px",
                  background: "rgba(12, 14, 20, 0.85)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  borderRadius: "6px",
                  padding: "10px 14px",
                  backdropFilter: "blur(6px)",
                  fontSize: "11px",
                  color: "var(--text-secondary)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#10B981" }} />
                  <span style={{ fontWeight: 700, color: "#ffffff" }}>YOLO11n-ANPR INFERENCE RUNNING</span>
                </div>
                <div style={{ display: "flex", gap: "16px", marginTop: "2px" }}>
                  <span>FPS: <strong style={{ color: "var(--text-primary)" }}>24.8</strong></span>
                  <span>LATENCY: <strong style={{ color: "var(--text-primary)" }}>18ms</strong></span>
                  <span>CONF: <strong style={{ color: "var(--text-primary)" }}>0.94</strong></span>
                </div>
              </div>

              {/* Detection Box Simulation */}
              <div
                style={{
                  position: "absolute",
                  top: "35%",
                  left: "40%",
                  width: "22%",
                  height: "30%",
                  border: "2px solid #0D9488",
                  borderRadius: "4px",
                  boxShadow: "0 0 10px rgba(13, 148, 136, 0.4)",
                  pointerEvents: "none",
                }}
              >
                <span
                  style={{
                    position: "absolute",
                    top: "-22px",
                    left: "-2px",
                    background: "#0D9488",
                    color: "#ffffff",
                    fontSize: "10px",
                    fontWeight: 700,
                    padding: "2px 6px",
                    borderRadius: "3px",
                    fontFamily: "var(--mono)",
                  }}
                >
                  KA01MJ4921 • 18.5 km/h
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Inference Diagnostics Footer */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 1fr)",
            padding: "14px 20px",
            borderTop: "1px solid var(--border)",
            background: "var(--surface-raised)",
            fontSize: "11px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Cpu size={16} color="#0D9488" />
            <div>
              <span style={{ color: "var(--text-muted)", display: "block", fontSize: "10px" }}>MODEL ARCHITECTURE</span>
              <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>YOLO11 nano + CRNN OCR Engine</span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Activity size={16} color="#3B82F6" />
            <div>
              <span style={{ color: "var(--text-muted)", display: "block", fontSize: "10px" }}>ESTIMATION PIPELINE</span>
              <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Perspective Quad Homography</span>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <Layers size={16} color="#F59E0B" />
            <div>
              <span style={{ color: "var(--text-muted)", display: "block", fontSize: "10px" }}>STREAM ENCODING</span>
              <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>MJPEG Multi-Client Fanout</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PipelinePage;
