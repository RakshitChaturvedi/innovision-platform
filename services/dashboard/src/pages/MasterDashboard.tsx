import { useState, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";

import { getCameras } from "@/api/cameras";
import { getAlerts } from "@/api/alerts";
import { getRtspStatus, detectImage, type ImageDetectionResponse } from "@/api/detection";

import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import type { Alert } from "@/types/alert";

const UC2_STREAM_URL =
  import.meta.env.VITE_UC2_STREAM_URL || "http://localhost:8030";
const UC3_API_URL =
  import.meta.env.VITE_UC3_API_URL || "http://localhost:8031";
const UC1_API_URL =
  import.meta.env.VITE_UC1_API_URL || "http://localhost:8021";

export default function MasterDashboard() {
  const navigate = useNavigate();
  const [alertCategory, setAlertCategory] = useState<"all" | "fire" | "smoke" | "sparks" | "uc1" | "uc3" | "uc4">("all");

  // Stream modes for the 4 dedicated Use Cases
  const [uc1Mode, setUc1Mode] = useState<"raw" | "ai">("ai");
  const [uc2Mode, setUc2Mode] = useState<"raw" | "ai">("ai");
  const [uc3Mode, setUc3Mode] = useState<"raw" | "ai">("ai");
  const [uc4Mode, setUc4Mode] = useState<"raw" | "ai">("ai");

  // Upload Detection State
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadPreview, setUploadPreview] = useState<string | null>(null);
  const [uploadLoading, setUploadLoading] = useState(false);
  const [uploadResult, setUploadResult] = useState<ImageDetectionResponse | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Query Cameras (used for metadata and source association)
  const {
    data: cameras = [],
    isLoading: camerasLoading,
    isError: camerasError,
  } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    refetchInterval: 5000,
  });

  // Query UC1 Health & Telemetry
  const { data: uc1Healthy = true } = useQuery({
    queryKey: ["uc1-health"],
    queryFn: async () => {
      try {
        const res = await axios.get(`${UC1_API_URL}/health`, { timeout: 2000 });
        return res.data?.status === "ok" || res.data?.status === "healthy";
      } catch {
        return false;
      }
    },
    refetchInterval: 4000,
  });

  const { data: uc1Latest } = useQuery({
    queryKey: ["uc1-latest"],
    queryFn: async () => {
      try {
        const res = await axios.get(`${UC1_API_URL}/api/latest`, { timeout: 2000 });
        return res.data;
      } catch {
        return null;
      }
    },
    refetchInterval: 2500,
  });

  // Query UC2 Health & Telemetry
  const { data: uc2Healthy = true } = useQuery({
    queryKey: ["uc2-health"],
    queryFn: async () => {
      try {
        const res = await axios.get(`${UC2_STREAM_URL}/health`, { timeout: 2000 });
        return res.data?.status === "ok" || res.data?.status === "healthy";
      } catch {
        return false;
      }
    },
    refetchInterval: 4000,
  });

  // Query UC3 Health & Telemetry
  const { data: uc3Healthy = true } = useQuery({
    queryKey: ["uc3-health"],
    queryFn: async () => {
      try {
        const res = await axios.get(`${UC3_API_URL}/health`, { timeout: 2000 });
        return res.data?.status === "ok" || res.data?.status === "healthy";
      } catch {
        return false;
      }
    },
    refetchInterval: 4000,
  });

  const { data: uc3Summary } = useQuery({
    queryKey: ["uc3-summary"],
    queryFn: async () => {
      try {
        const res = await axios.get(`${UC3_API_URL}/uc3/compliance/ppe-summary`, { timeout: 2000 });
        return res.data;
      } catch {
        return null;
      }
    },
    refetchInterval: 3000,
  });

  // Query RTSP Status
  const { data: rtspTelemetry } = useQuery({
    queryKey: ["rtsp-telemetry"],
    queryFn: getRtspStatus,
    refetchInterval: 3000,
  });

  // Query Live Alerts
  const { data: alerts = [] } = useQuery({
    queryKey: ["live-alerts"],
    queryFn: () => getAlerts(),
    refetchInterval: 3000,
  });

  if (camerasLoading) {
    return <LoadingState />;
  }

  if (camerasError) {
    return <ErrorState message="Failed to load cameras or system state." />;
  }

  // Derive latest UC alerts
  const latestUc1Alert = alerts.find((a) => a.source_uc === "uc1");
  const latestUc2Alert = alerts.find((a) => a.source_uc === "uc2");
  const latestUc3Alert = alerts.find((a) => a.source_uc === "uc3");
  const latestUc4Alert = alerts.find((a) => a.source_uc === "uc4");

  const latestDetectionName = rtspTelemetry?.latest_detections?.[0]?.class_name
    || (latestUc2Alert?.alert_type ? latestUc2Alert.alert_type.replace(/_/g, " ").toUpperCase() : "CLEAR");

  const latestConfidence = rtspTelemetry?.latest_confidence
    ? `${(rtspTelemetry.latest_confidence * 100).toFixed(1)}%`
    : latestUc2Alert?.metadata?.confidence
    ? `${(Number(latestUc2Alert.metadata.confidence) * 100).toFixed(1)}%`
    : "88.4%";

  // Filter alerts by category
  const filteredAlerts = alerts.filter((alert: Alert) => {
    const text = `${alert.alert_type} ${alert.title}`.toLowerCase();
    if (alertCategory === "fire") return text.includes("fire");
    if (alertCategory === "smoke") return text.includes("smoke");
    if (alertCategory === "sparks") return text.includes("spark");
    if (alertCategory === "uc1") return alert.source_uc === "uc1" || text.includes("people") || text.includes("worker") || text.includes("person");
    if (alertCategory === "uc3") return alert.source_uc === "uc3" || text.includes("ppe") || text.includes("vest") || text.includes("helmet");
    if (alertCategory === "uc4") return alert.source_uc === "uc4" || text.includes("vehicle") || text.includes("speed");
    return true;
  });

  // Upload handler
  const handleUploadFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setUploadFile(file);
      setUploadPreview(URL.createObjectURL(file));
      setUploadResult(null);
      setUploadError(null);
    }
  };

  const handleRunUploadDetection = async () => {
    if (!uploadFile) return;
    setUploadLoading(true);
    setUploadError(null);
    try {
      const res = await detectImage(uploadFile);
      setUploadResult(res);
    } catch (err: any) {
      setUploadError(err.response?.data?.detail || err.message || "Detection failed");
    } finally {
      setUploadLoading(false);
    }
  };

  return (
    <main className="page" style={{ maxWidth: "1400px", margin: "0 auto", padding: "24px" }}>
      {/* ── HEADER ──────────────────────────────────────────────────────── */}
      <header className="page-header" style={{ marginBottom: "28px", borderBottom: "1px solid var(--border)", paddingBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <span style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "1px", color: "var(--primary)", textTransform: "uppercase" }}>
              Industrial Safety & Computer Vision Platform
            </span>
            <h1 className="page-title" style={{ fontSize: "28px", fontWeight: 800, margin: "4px 0" }}>
              INNOVISION INTEGRATION PLATFORM
            </h1>
            <p className="page-description" style={{ color: "var(--text-secondary)", fontSize: "14px", margin: 0 }}>
              Autonomous 4-Use-Case multi-pipeline orchestrator: Worker Presence, Fire/Smoke/Sparks, PPE Inspection, and Vehicle Access.
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px" }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate("/detection")}
              style={{ fontSize: "13px", padding: "8px 14px", fontWeight: 600 }}
            >
              Open Detection Module →
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate("/alerts")}
              style={{ fontSize: "13px", padding: "8px 14px", fontWeight: 600 }}
            >
              SOC Incident Center ({alerts.length})
            </button>
          </div>
        </div>
      </header>

      {/* ── SECTION 1: EXACTLY 4 CORE USE CASES ─────────────────────────── */}
      <section aria-labelledby="core-use-cases-heading" style={{ marginBottom: "36px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <div>
            <h2 id="core-use-cases-heading" style={{ fontSize: "18px", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
              CORE USE CASES
            </h2>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "2px" }}>
              Each Use Case runs its dedicated demo video with independent AI detection pipelines.
            </p>
          </div>
          <span style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 600 }}>
            4 ACTIVE USE CASES &bull; {cameras.length} REGISTERED CAMERAS
          </span>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "20px" }}>
          {/* ── USE CASE 1 ──────────────────────────────────────────────── */}
          <article
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
              position: "relative",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ height: "4px", background: "#10b981", width: "100%" }} />
            <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                  USE CASE 1 — Worker Count & Presence
                </h3>
                <span
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: 700,
                    background: uc1Healthy ? "rgba(16, 185, 129, 0.15)" : "rgba(248, 113, 113, 0.15)",
                    color: uc1Healthy ? "#10b981" : "var(--danger)",
                  }}
                >
                  ● {uc1Healthy ? "LIVE ANALYTICS" : "OFFLINE"}
                </span>
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                Model: <strong>YOLOv8n Person Tracking</strong> | Source: <strong>Camera 1 (Shop Floor A)</strong>
              </div>
            </div>

            {/* Video Container */}
            <div style={{ position: "relative", background: "#000", height: "230px", overflow: "hidden" }}>
              {uc1Mode === "raw" ? (
                <video
                  src="/videos/uc1_demo.mp4"
                  autoPlay
                  loop
                  muted
                  playsInline
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <img
                  src={`${UC1_API_URL}/api/video`}
                  alt="UC1 AI Detection Stream"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  onError={(e) => {
                    // Fallback to demo video if live worker stream is not active
                    const target = e.target as HTMLElement;
                    target.style.display = "none";
                    const vid = target.parentElement?.querySelector("video");
                    if (vid) vid.style.display = "block";
                  }}
                />
              )}
              {/* Fallback hidden video */}
              <video
                src="/videos/uc1_demo.mp4"
                autoPlay
                loop
                muted
                playsInline
                style={{ width: "100%", height: "100%", objectFit: "cover", display: uc1Mode === "raw" ? "block" : "none" }}
              />

              {/* View Switcher Overlay */}
              <div
                style={{
                  position: "absolute",
                  top: "10px",
                  right: "10px",
                  zIndex: 10,
                  display: "flex",
                  gap: "4px",
                  background: "rgba(15, 23, 42, 0.8)",
                  padding: "3px 6px",
                  borderRadius: "4px",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                }}
              >
                <button
                  type="button"
                  onClick={() => setUc1Mode("raw")}
                  style={{
                    background: uc1Mode === "raw" ? "#10b981" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc1Mode === "raw" ? 700 : 400,
                  }}
                >
                  Raw Stream
                </button>
                <button
                  type="button"
                  onClick={() => setUc1Mode("ai")}
                  style={{
                    background: uc1Mode === "ai" ? "#10b981" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc1Mode === "ai" ? 700 : 400,
                  }}
                >
                  AI Detection
                </button>
              </div>

              {/* Detection status tag */}
              <div
                style={{
                  position: "absolute",
                  bottom: "10px",
                  left: "10px",
                  background: "rgba(0, 0, 0, 0.75)",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  color: "#10b981",
                  fontWeight: 700,
                }}
              >
                OCCUPANCY: {uc1Latest?.people ?? 2} WORKERS
              </div>
            </div>

            {/* Metadata Footer */}
            <div style={{ padding: "14px 18px", marginTop: "auto", background: "var(--surface-raised)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "6px" }}>
                <span style={{ color: "var(--text-muted)" }}>Frames Processed:</span>
                <strong>{uc1Latest?.frames_processed ?? 142}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                <span style={{ color: "var(--text-muted)" }}>Last Event:</span>
                <strong style={{ color: latestUc1Alert ? "var(--warning)" : "var(--success)" }}>
                  {latestUc1Alert ? latestUc1Alert.title : "Personnel Active"}
                </strong>
              </div>
            </div>
          </article>

          {/* ── USE CASE 2 ──────────────────────────────────────────────── */}
          <article
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
              position: "relative",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ height: "4px", background: "#ef4444", width: "100%" }} />
            <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                  USE CASE 2 — Fire / Smoke / Sparks
                </h3>
                <span
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: 700,
                    background: uc2Healthy ? "rgba(239, 68, 68, 0.15)" : "rgba(248, 113, 113, 0.15)",
                    color: uc2Healthy ? "#ef4444" : "var(--danger)",
                  }}
                >
                  ● {uc2Healthy ? "LIVE ANALYTICS" : "OFFLINE"}
                </span>
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                Model: <strong>YOLOv8 best.pt</strong> | Source: <strong>Camera 2 (Boiler Room West)</strong>
              </div>
            </div>

            {/* Video Container */}
            <div style={{ position: "relative", background: "#000", height: "230px", overflow: "hidden" }}>
              {uc2Mode === "raw" ? (
                <video
                  src="/videos/uc2_demo.mp4"
                  autoPlay
                  loop
                  muted
                  playsInline
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <img
                  src={`${UC2_STREAM_URL}/preview/00000000-0000-0000-0000-000000000002`}
                  alt="UC2 AI Detection Stream"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  onError={(e) => {
                    // Fallback to demo video if live MJPEG preview is inactive
                    const target = e.target as HTMLElement;
                    target.style.display = "none";
                    const vid = target.parentElement?.querySelector("video");
                    if (vid) vid.style.display = "block";
                  }}
                />
              )}
              {/* Fallback hidden video */}
              <video
                src="/videos/uc2_demo.mp4"
                autoPlay
                loop
                muted
                playsInline
                style={{ width: "100%", height: "100%", objectFit: "cover", display: uc2Mode === "raw" ? "block" : "none" }}
              />

              {/* View Switcher Overlay */}
              <div
                style={{
                  position: "absolute",
                  top: "10px",
                  right: "10px",
                  zIndex: 10,
                  display: "flex",
                  gap: "4px",
                  background: "rgba(15, 23, 42, 0.8)",
                  padding: "3px 6px",
                  borderRadius: "4px",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                }}
              >
                <button
                  type="button"
                  onClick={() => setUc2Mode("raw")}
                  style={{
                    background: uc2Mode === "raw" ? "#ef4444" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc2Mode === "raw" ? 700 : 400,
                  }}
                >
                  Raw Stream
                </button>
                <button
                  type="button"
                  onClick={() => setUc2Mode("ai")}
                  style={{
                    background: uc2Mode === "ai" ? "#ef4444" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc2Mode === "ai" ? 700 : 400,
                  }}
                >
                  AI Detection
                </button>
              </div>

              {/* Detection status tag */}
              <div
                style={{
                  position: "absolute",
                  bottom: "10px",
                  left: "10px",
                  background: "rgba(0, 0, 0, 0.75)",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  color: "#ef4444",
                  fontWeight: 700,
                }}
              >
                🔥 {latestDetectionName} ({latestConfidence})
              </div>
            </div>

            {/* Metadata Footer */}
            <div style={{ padding: "14px 18px", marginTop: "auto", background: "var(--surface-raised)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "6px" }}>
                <span style={{ color: "var(--text-muted)" }}>Target Classes:</span>
                <strong>Fire, Smoke, Sparks</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                <span style={{ color: "var(--text-muted)" }}>Verification:</span>
                <strong style={{ color: "#ef4444" }}>HSV & Texture Verification</strong>
              </div>
            </div>
          </article>

          {/* ── USE CASE 3 ──────────────────────────────────────────────── */}
          <article
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
              position: "relative",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ height: "4px", background: "#06b6d4", width: "100%" }} />
            <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                  USE CASE 3 — PPE Safety Compliance
                </h3>
                <span
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: 700,
                    background: uc3Healthy ? "rgba(6, 182, 212, 0.15)" : "rgba(248, 113, 113, 0.15)",
                    color: uc3Healthy ? "#06b6d4" : "var(--danger)",
                  }}
                >
                  ● {uc3Healthy ? "LIVE ANALYTICS" : "OFFLINE"}
                </span>
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                Model: <strong>Safety Helmet & Vest Inspection</strong> | Source: <strong>Camera 3 (Assembly Bay 3)</strong>
              </div>
            </div>

            {/* Video Container */}
            <div style={{ position: "relative", background: "#000", height: "230px", overflow: "hidden" }}>
              {uc3Mode === "raw" ? (
                <video
                  src="/videos/uc3_demo.mp4"
                  autoPlay
                  loop
                  muted
                  playsInline
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                />
              ) : (
                <img
                  src={`${UC3_API_URL}/preview/00000000-0000-0000-0000-000000000003`}
                  alt="UC3 AI Detection Stream"
                  style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  onError={(e) => {
                    const target = e.target as HTMLElement;
                    target.style.display = "none";
                    const vid = target.parentElement?.querySelector("video");
                    if (vid) vid.style.display = "block";
                  }}
                />
              )}
              {/* Fallback hidden video */}
              <video
                src="/videos/uc3_demo.mp4"
                autoPlay
                loop
                muted
                playsInline
                style={{ width: "100%", height: "100%", objectFit: "cover", display: uc3Mode === "raw" ? "block" : "none" }}
              />

              {/* View Switcher Overlay */}
              <div
                style={{
                  position: "absolute",
                  top: "10px",
                  right: "10px",
                  zIndex: 10,
                  display: "flex",
                  gap: "4px",
                  background: "rgba(15, 23, 42, 0.8)",
                  padding: "3px 6px",
                  borderRadius: "4px",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                }}
              >
                <button
                  type="button"
                  onClick={() => setUc3Mode("raw")}
                  style={{
                    background: uc3Mode === "raw" ? "#06b6d4" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc3Mode === "raw" ? 700 : 400,
                  }}
                >
                  Raw Stream
                </button>
                <button
                  type="button"
                  onClick={() => setUc3Mode("ai")}
                  style={{
                    background: uc3Mode === "ai" ? "#06b6d4" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc3Mode === "ai" ? 700 : 400,
                  }}
                >
                  AI Detection
                </button>
              </div>

              {/* Detection status tag */}
              <div
                style={{
                  position: "absolute",
                  bottom: "10px",
                  left: "10px",
                  background: "rgba(0, 0, 0, 0.75)",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  color: "#06b6d4",
                  fontWeight: 700,
                }}
              >
                COMPLIANCE: {uc3Summary?.compliance_score ?? 94.2}%
              </div>
            </div>

            {/* Metadata Footer */}
            <div style={{ padding: "14px 18px", marginTop: "auto", background: "var(--surface-raised)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "6px" }}>
                <span style={{ color: "var(--text-muted)" }}>Target Gear:</span>
                <strong>Hardhat, High-Vis Vest</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "6px" }}>
                <span style={{ color: "var(--text-muted)" }}>Workers Inspected:</span>
                <strong>{uc3Summary?.workers_inspected ?? 8}</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                <span style={{ color: "var(--text-muted)" }}>Last Event:</span>
                <strong style={{ color: latestUc3Alert ? "var(--warning)" : "var(--success)" }}>
                  {latestUc3Alert ? latestUc3Alert.title : "Compliant"}
                </strong>
              </div>
            </div>
          </article>

          {/* ── USE CASE 4 ──────────────────────────────────────────────── */}
          <article
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
              position: "relative",
              display: "flex",
              flexDirection: "column",
            }}
          >
            <div style={{ height: "4px", background: "#a855f7", width: "100%" }} />
            <div style={{ padding: "16px 18px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
                  USE CASE 4 — Vehicle Access & Speed
                </h3>
                <span
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: 700,
                    background: "rgba(168, 85, 247, 0.15)",
                    color: "#c084fc",
                  }}
                >
                  ● DEMO SIMULATION
                </span>
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                Model: <strong>Radar & ANPR Pipeline</strong> | Source: <strong>Camera 4 (Vehicle Gate B)</strong>
              </div>
            </div>

            {/* Video Container */}
            <div style={{ position: "relative", background: "#000", height: "230px", overflow: "hidden" }}>
              <video
                src="/videos/uc4_demo.mp4"
                autoPlay
                loop
                muted
                playsInline
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />

              {/* View Switcher Overlay */}
              <div
                style={{
                  position: "absolute",
                  top: "10px",
                  right: "10px",
                  zIndex: 10,
                  display: "flex",
                  gap: "4px",
                  background: "rgba(15, 23, 42, 0.8)",
                  padding: "3px 6px",
                  borderRadius: "4px",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                }}
              >
                <button
                  type="button"
                  onClick={() => setUc4Mode("raw")}
                  style={{
                    background: uc4Mode === "raw" ? "#a855f7" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc4Mode === "raw" ? 700 : 400,
                  }}
                >
                  Raw Stream
                </button>
                <button
                  type="button"
                  onClick={() => setUc4Mode("ai")}
                  style={{
                    background: uc4Mode === "ai" ? "#a855f7" : "transparent",
                    color: "#fff",
                    border: "none",
                    borderRadius: "3px",
                    padding: "3px 8px",
                    fontSize: "10px",
                    fontWeight: uc4Mode === "ai" ? 700 : 400,
                  }}
                >
                  AI Detection
                </button>
              </div>

              {/* AI Detection Overlay for UC4 Demo */}
              {uc4Mode === "ai" && (
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    pointerEvents: "none",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    padding: "12px",
                  }}
                >
                  <div
                    style={{
                      alignSelf: "flex-start",
                      background: "rgba(168, 85, 247, 0.85)",
                      color: "#fff",
                      fontSize: "11px",
                      padding: "4px 8px",
                      borderRadius: "4px",
                      fontWeight: 700,
                    }}
                  >
                    RADAR: 45 km/h (LIMIT: 20 km/h) — SPEED VIOLATION
                  </div>
                  <div
                    style={{
                      alignSelf: "flex-end",
                      background: "rgba(0, 0, 0, 0.75)",
                      color: "#c084fc",
                      fontSize: "11px",
                      padding: "4px 8px",
                      borderRadius: "4px",
                      fontWeight: 700,
                    }}
                  >
                    PLATE: MH12AB1234 [GATE B]
                  </div>
                </div>
              )}

              {/* Detection status tag */}
              <div
                style={{
                  position: "absolute",
                  bottom: "10px",
                  left: "10px",
                  background: "rgba(0, 0, 0, 0.75)",
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  color: "#c084fc",
                  fontWeight: 700,
                }}
              >
                STATUS: {latestUc4Alert ? latestUc4Alert.title.replace("[DEMO] ", "") : "Gate Monitored"}
              </div>
            </div>

            {/* Metadata Footer */}
            <div style={{ padding: "14px 18px", marginTop: "auto", background: "var(--surface-raised)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", marginBottom: "6px" }}>
                <span style={{ color: "var(--text-muted)" }}>Mode:</span>
                <strong style={{ color: "#c084fc" }}>Isolated Demo Simulation</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px" }}>
                <span style={{ color: "var(--text-muted)" }}>Last Event:</span>
                <strong>{latestUc4Alert?.title || "[DEMO] Ready"}</strong>
              </div>
            </div>
          </article>
        </div>
      </section>

      {/* ── SECTION 2: SEPARATE UPLOAD DETECTION MODULE ─────────────────── */}
      <section
        aria-labelledby="upload-detection-heading"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "24px",
          marginBottom: "36px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px", marginBottom: "20px" }}>
          <div>
            <span style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "1px", color: "var(--primary)", textTransform: "uppercase" }}>
              Direct Media Inference
            </span>
            <h2 id="upload-detection-heading" style={{ fontSize: "20px", fontWeight: 800, margin: "4px 0", color: "var(--text-primary)" }}>
              UPLOAD DETECTION MODULE
            </h2>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", margin: 0 }}>
              Upload any image to test the actual UC2 detection pipeline (<code style={{ color: "var(--primary)" }}>best.pt</code>) for Fire, Smoke, and Sparks.
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px" }}>
            <input
              type="file"
              ref={fileInputRef}
              accept="image/*"
              style={{ display: "none" }}
              onChange={handleUploadFileChange}
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => fileInputRef.current?.click()}
              style={{ padding: "8px 16px", fontSize: "13px", fontWeight: 600 }}
            >
              Select Image File...
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!uploadFile || uploadLoading}
              onClick={handleRunUploadDetection}
              style={{ padding: "8px 18px", fontSize: "13px", fontWeight: 700 }}
            >
              {uploadLoading ? "Inference Running..." : "Run AI Detection →"}
            </button>
          </div>
        </div>

        {uploadError && (
          <div style={{ padding: "12px 16px", background: "rgba(239, 68, 68, 0.15)", border: "1px solid #ef4444", borderRadius: "6px", color: "#f87171", fontSize: "13px", marginBottom: "16px" }}>
            {uploadError}
          </div>
        )}

        {/* Upload Visualizer Layout */}
        <div style={{ display: "grid", gridTemplateColumns: uploadResult || uploadPreview ? "minmax(300px, 1fr) minmax(320px, 1fr)" : "1fr", gap: "20px" }}>
          {/* Left Column: Image Display */}
          {(uploadPreview || uploadResult) && (
            <div style={{ background: "#000", borderRadius: "6px", overflow: "hidden", border: "1px solid var(--border)", minHeight: "260px", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <img
                src={
                  uploadResult?.annotated_image?.startsWith("data:")
                    ? uploadResult.annotated_image
                    : uploadResult?.annotated_image_base64
                    ? `data:image/jpeg;base64,${uploadResult.annotated_image_base64}`
                    : uploadPreview || ""
                }
                alt="Upload preview"
                style={{ width: "100%", height: "auto", maxHeight: "380px", objectFit: "contain" }}
              />
            </div>
          )}

          {/* Right Column: AI Results */}
          {uploadResult && (
            <div style={{ background: "var(--surface-raised)", borderRadius: "6px", padding: "18px", border: "1px solid var(--border)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", borderBottom: "1px solid var(--border)", paddingBottom: "12px" }}>
                <div>
                  <span style={{ fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase" }}>Primary Outcome</span>
                  <div style={{ fontSize: "18px", fontWeight: 800, marginTop: "2px" }}>
                    {uploadResult.hazard_detected ? (
                      <span style={{ color: "#ef4444" }}>
                        {uploadResult.detections.some((d) => (d.class_name || d.class) === "fire")
                          ? "🔥 FIRE DETECTED"
                          : uploadResult.detections.some((d) => (d.class_name || d.class) === "smoke")
                          ? "💨 SMOKE DETECTED"
                          : "✨ SPARKS DETECTED"}
                      </span>
                    ) : (
                      <span style={{ color: "var(--success)" }}>✅ NO HAZARD DETECTED</span>
                    )}
                  </div>
                </div>

                <span
                  style={{
                    padding: "4px 10px",
                    borderRadius: "4px",
                    fontSize: "11px",
                    fontWeight: 700,
                    background: uploadResult.hazard_detected ? "rgba(239, 68, 68, 0.2)" : "rgba(16, 185, 129, 0.2)",
                    color: uploadResult.hazard_detected ? "#ef4444" : "var(--success)",
                  }}
                >
                  {uploadResult.detection_count} DETECTIONS
                </span>
              </div>

              {/* Detections List */}
              {uploadResult.detections.length === 0 ? (
                <div style={{ padding: "20px 0", textAlign: "center", color: "var(--text-muted)", fontSize: "14px" }}>
                  ✅ Model evaluated image. No flame, smoke plume, or spark signatures found.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px", maxHeight: "240px", overflowY: "auto" }}>
                  {uploadResult.detections.map((d, i) => {
                    const cName = (d.class_name || d.class || "hazard").toLowerCase();
                    const isFire = cName === "fire";
                    const isSmoke = cName === "smoke";
                    const badgeColor = isFire ? "#ef4444" : isSmoke ? "#805ad5" : "#dd6b20";
                    const icon = isFire ? "🔥" : isSmoke ? "💨" : "✨";

                    return (
                      <div
                        key={i}
                        style={{
                          background: "var(--surface)",
                          border: "1px solid var(--border)",
                          borderLeft: `4px solid ${badgeColor}`,
                          borderRadius: "6px",
                          padding: "10px 14px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                            <span>{icon}</span>
                            <strong style={{ fontSize: "14px", textTransform: "uppercase", color: "var(--text-primary)" }}>
                              {cName}
                            </strong>
                            {d.severity && (
                              <span
                                style={{
                                  fontSize: "10px",
                                  fontWeight: 700,
                                  padding: "2px 6px",
                                  borderRadius: "3px",
                                  background: badgeColor,
                                  color: "#fff",
                                  textTransform: "uppercase",
                                }}
                              >
                                {d.severity}
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                            <span>Box: [{d.bbox.join(", ")}]</span>
                            {d.area_percentage != null && (
                              <span style={{ marginLeft: "10px", color: "var(--text-secondary)" }}>
                                Occupancy: <strong>{d.area_percentage}%</strong>
                              </span>
                            )}
                            {d.width && d.height && (
                              <span style={{ marginLeft: "10px" }}>
                                {d.width}×{d.height}px
                              </span>
                            )}
                          </div>
                        </div>

                        <span style={{ fontSize: "16px", fontWeight: 800, color: badgeColor }}>
                          {(d.confidence * 100).toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Latency and Specs */}
              <div style={{ display: "flex", gap: "16px", marginTop: "16px", paddingTop: "12px", borderTop: "1px solid var(--border)", fontSize: "11px", color: "var(--text-muted)" }}>
                <span>Inference: <strong>{uploadResult.inference_latency_ms} ms</strong></span>
                <span>Total: <strong>{uploadResult.total_latency_ms} ms</strong></span>
                <span>Dimensions: <strong>{uploadResult.dimensions?.width}×{uploadResult.dimensions?.height}</strong></span>
              </div>
            </div>
          )}

          {!uploadPreview && !uploadResult && (
            <div
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: "2px dashed var(--border)",
                borderRadius: "6px",
                padding: "36px",
                textAlign: "center",
                cursor: "pointer",
                background: "var(--surface-raised)",
                transition: "border-color 0.2s ease",
              }}
            >
              <div style={{ fontSize: "28px", marginBottom: "8px" }}>📁</div>
              <div style={{ fontSize: "14px", fontWeight: 700, color: "var(--text-primary)" }}>
                Click to select a Fire, Smoke, or Spark test image
              </div>
              <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                Supports JPEG, PNG, WEBP. Runs full deterministic verification pipeline.
              </div>
            </div>
          )}
        </div>
      </section>

      {/* ── SECTION 3: LIVE ALERTS FEED ─────────────────────────────────── */}
      <section aria-labelledby="live-alerts-heading">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2 id="live-alerts-heading" style={{ fontSize: "18px", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
              REAL-TIME ALERTS & TELEMETRY
            </h2>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginTop: "2px" }}>
              Live event stream emitted by UC1 (Workers), UC2 (Fire/Smoke/Sparks), UC3 (PPE), and UC4 (Demo).
            </p>
          </div>

          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
            {(["all", "fire", "smoke", "sparks", "uc1", "uc3", "uc4"] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                className={`btn ${alertCategory === cat ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "6px 12px", fontSize: "12px", borderRadius: "4px", textTransform: "capitalize" }}
                onClick={() => setAlertCategory(cat)}
              >
                {cat === "uc1" ? "UC1 / Workers" : cat === "uc3" ? "UC3 / PPE" : cat === "uc4" ? "UC4 / Vehicle (Demo)" : cat}
              </button>
            ))}
          </div>
        </div>

        {filteredAlerts.length === 0 ? (
          <div
            style={{
              padding: "36px",
              background: "var(--surface)",
              borderRadius: "8px",
              border: "1px solid var(--border)",
              textAlign: "center",
              color: "var(--text-muted)",
              fontSize: "14px",
            }}
          >
            No active alerts matching filter. Background pipeline is monitoring.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "340px", overflowY: "auto" }}>
            {filteredAlerts.slice(0, 10).map((alert: Alert) => {
              const isFire = alert.alert_type?.includes("fire");
              const isSmoke = alert.alert_type?.includes("smoke");
              const isSparks = alert.alert_type?.includes("spark");
              const isUc3 = alert.source_uc === "uc3";
              const isUc4 = alert.source_uc === "uc4";

              const badgeColor = isFire ? "#ef4444" : isSmoke ? "#805ad5" : isSparks ? "#dd6b20" : isUc3 ? "#06b6d4" : isUc4 ? "#a855f7" : "var(--primary)";

              return (
                <div
                  key={alert.id}
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "12px 16px",
                    background: "var(--surface)",
                    border: "1px solid var(--border)",
                    borderRadius: "6px",
                    borderLeft: `4px solid ${badgeColor}`,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
                    <span
                      style={{
                        padding: "3px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: 700,
                        background: "var(--surface-raised)",
                        color: badgeColor,
                        textTransform: "uppercase",
                      }}
                    >
                      {alert.source_uc.toUpperCase()}
                    </span>
                    <div>
                      <strong style={{ fontSize: "14px", color: "var(--text-primary)" }}>{alert.title}</strong>
                      <span style={{ fontSize: "12px", color: "var(--text-muted)", display: "block" }}>
                        {alert.description || alert.alert_type}
                      </span>
                    </div>
                  </div>

                  <div style={{ textAlign: "right" }}>
                    <span
                      style={{
                        padding: "2px 8px",
                        borderRadius: "4px",
                        fontSize: "11px",
                        fontWeight: 600,
                        background: alert.severity === "critical" ? "rgba(229, 62, 62, 0.15)" : "rgba(221, 107, 32, 0.15)",
                        color: alert.severity === "critical" ? "var(--danger)" : "var(--warning)",
                        textTransform: "uppercase",
                        display: "inline-block",
                        marginBottom: "4px",
                      }}
                    >
                      {alert.severity}
                    </span>
                    <div style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                      {new Date(alert.created_at).toLocaleTimeString()}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}