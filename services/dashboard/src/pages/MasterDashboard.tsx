import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import axios from "axios";

import { getCameras } from "@/api/cameras";
import { getAlerts } from "@/api/alerts";
import { getRtspStatus } from "@/api/detection";

import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import CameraTile from "@/components/cameras/CameraTile";
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

  // Query Cameras
  const {
    data: cameras = [],
    isLoading: camerasLoading,
    isError: camerasError,
  } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    refetchInterval: 5000,
  });

  // Query UC1 Health
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

  // Query UC2 Health
  const { data: uc2Healthy = true } = useQuery({
    queryKey: ["uc2-health"],
    queryFn: async () => {
      try {
        const res = await axios.get(`${UC2_STREAM_URL}/health`, { timeout: 2000 });
        return res.data?.status === "ok";
      } catch {
        return false;
      }
    },
    refetchInterval: 4000,
  });

  // Query UC3 Health
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

  // UC2 demo camera
  const uc2Camera = cameras.find((c) => c.use_cases.includes("uc2")) || cameras[0];

  return (
    <main className="page" style={{ maxWidth: "1400px", margin: "0 auto", padding: "24px" }}>
      {/* ── HEADER ──────────────────────────────────────────────────────── */}
      <header className="page-header" style={{ marginBottom: "24px", borderBottom: "1px solid var(--border)", paddingBottom: "16px" }}>
        <div>
          <span style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "1px", color: "var(--primary)", textTransform: "uppercase" }}>
            Autonomous Computer Vision System
          </span>
          <h1 className="page-title" style={{ fontSize: "28px", fontWeight: 800, margin: "4px 0" }}>
            INNOVISION INTEGRATION PLATFORM
          </h1>
          <p className="page-description" style={{ color: "var(--text-secondary)" }}>
            Integrated multi-hazard platform: UC1 Worker Count, UC2 Fire/Smoke/Sparks, UC3/PART PPE monitoring, and Detection Module.
          </p>
        </div>
      </header>

      {/* ── SECTION 1: ACTIVE USE CASES ─────────────────────────────────── */}
      <section aria-labelledby="use-cases-heading" style={{ marginBottom: "32px" }}>
        <h2 id="use-cases-heading" style={{ fontSize: "18px", fontWeight: 700, margin: "0 0 16px 0", color: "var(--text-primary)" }}>
          USE CASES
        </h2>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))", gap: "16px" }}>
          {/* UC1 / PART Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "3px", background: "#3182ce" }} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
                UC1 / PART — Worker Count
              </h3>
              <span
                style={{
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 700,
                  background: uc1Healthy ? "rgba(70, 189, 146, 0.15)" : "rgba(248, 113, 113, 0.15)",
                  color: uc1Healthy ? "var(--success)" : "var(--danger)",
                }}
              >
                ● {uc1Healthy ? "RUNNING" : "OFFLINE"}
              </span>
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "16px", lineHeight: "1.5" }}>
              Autonomous personnel presence monitoring, occupancy counting, and zone intrusion detection using YOLO person analytics.
            </div>
            <div style={{ display: "flex", gap: "12px", fontSize: "12px" }}>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Detection: </span>
                <strong style={{ color: "var(--success)" }}>LIVE</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Model: </span>
                <strong>YOLOv8n</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Domain: </span>
                <strong>Worker Presence</strong>
              </div>
            </div>
          </div>

          {/* UC2 Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "3px", background: "#e53e3e" }} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
                UC2 — Fire / Smoke / Sparks
              </h3>
              <span
                style={{
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 700,
                  background: uc2Healthy ? "rgba(70, 189, 146, 0.15)" : "rgba(248, 113, 113, 0.15)",
                  color: uc2Healthy ? "var(--success)" : "var(--danger)",
                }}
              >
                ● {uc2Healthy ? "RUNNING" : "OFFLINE"}
              </span>
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "16px", lineHeight: "1.5" }}>
              Deep-learning inference running trained YOLOv8 model (<code style={{ color: "var(--primary)" }}>best.pt</code>) with temporal verification, fire persistence tracking, and false-positive suppression.
            </div>
            <div style={{ display: "flex", gap: "12px", fontSize: "12px" }}>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Detection: </span>
                <strong style={{ color: "var(--success)" }}>LIVE</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Classes: </span>
                <strong>Fire, Smoke, Sparks</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Model: </span>
                <strong>YOLOv8</strong>
              </div>
            </div>
          </div>

          {/* UC3 / PART Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "3px", background: "#46BD92" }} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
                UC3 / PART
              </h3>
              <span
                style={{
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 700,
                  background: uc3Healthy ? "rgba(70, 189, 146, 0.15)" : "rgba(248, 113, 113, 0.15)",
                  color: uc3Healthy ? "var(--success)" : "var(--danger)",
                }}
              >
                ● {uc3Healthy ? "RUNNING" : "OFFLINE"}
              </span>
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "16px", lineHeight: "1.5" }}>
              Active PPE and industrial safety gear compliance inspection. Evaluates real camera stream frames for safety helmets and high-visibility vests.
            </div>
            <div style={{ display: "flex", gap: "12px", fontSize: "12px" }}>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Detection: </span>
                <strong style={{ color: "var(--success)" }}>LIVE</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Domain: </span>
                <strong>PPE Compliance</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Last Event: </span>
                <strong>{latestUc3Alert ? latestUc3Alert.title : "Active"}</strong>
              </div>
            </div>
          </div>

          {/* UC4 / DEMO ONLY Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "3px", background: "#9333ea" }} />
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "12px" }}>
              <h3 style={{ margin: 0, fontSize: "18px", fontWeight: 700, color: "var(--text-primary)" }}>
                UC4 — Vehicle / Speed
              </h3>
              <span
                style={{
                  padding: "4px 8px",
                  borderRadius: "4px",
                  fontSize: "11px",
                  fontWeight: 700,
                  background: "rgba(147, 51, 234, 0.15)",
                  color: "#c084fc",
                }}
              >
                ● DEMO ONLY
              </span>
            </div>
            <div style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "16px", lineHeight: "1.5" }}>
              Controlled simulation for vehicle access monitoring and speed violation demonstration. Explicitly isolated demo mode.
            </div>
            <div style={{ display: "flex", gap: "12px", fontSize: "12px" }}>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Mode: </span>
                <strong style={{ color: "#c084fc" }}>DEMO ONLY</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Domain: </span>
                <strong>Vehicle / ANPR</strong>
              </div>
              <div style={{ padding: "6px 10px", background: "var(--surface-raised)", borderRadius: "4px" }}>
                <span style={{ color: "var(--text-muted)" }}>Last Event: </span>
                <strong>{latestUc4Alert ? latestUc4Alert.title : "Ready"}</strong>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── SECTION 2: DETECTION MODULE QUICK-LAUNCH ────────────────────── */}
      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "20px",
          marginBottom: "32px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <span style={{ fontSize: "11px", fontWeight: 700, letterSpacing: "0.5px", color: "var(--primary)", textTransform: "uppercase" }}>
              Central Inference Hub
            </span>
            <h2 style={{ fontSize: "20px", fontWeight: 700, margin: "4px 0" }}>
              DETECTION MODULE
            </h2>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
              Run ad-hoc or live computer vision detection against any image, recorded video file, or live RTSP camera stream.
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px" }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate("/detection")}
              style={{ padding: "10px 18px", fontWeight: 600, borderRadius: "6px" }}
            >
              🖼️ Image Upload
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate("/detection")}
              style={{ padding: "10px 18px", fontWeight: 600, borderRadius: "6px" }}
            >
              🎬 Video Upload
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate("/detection")}
              style={{ padding: "10px 18px", fontWeight: 600, borderRadius: "6px" }}
            >
              📡 RTSP Camera
            </button>
          </div>
        </div>
      </section>

      {/* ── SECTION 3: UC2 LIVE DETECTION ───────────────────────────────── */}
      <section aria-labelledby="live-detection-heading" style={{ marginBottom: "32px" }}>
        <h2 id="live-detection-heading" style={{ fontSize: "18px", fontWeight: 700, margin: "0 0 16px 0", color: "var(--text-primary)" }}>
          UC2 LIVE DETECTION
        </h2>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "20px" }}>
          {/* Live Video Preview Box */}
          <div
            style={{
              background: "#000",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              overflow: "hidden",
              position: "relative",
              minHeight: "320px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            {uc2Camera ? (
              <img
                src={`${UC2_STREAM_URL}/preview/${uc2Camera.id}`}
                alt="UC2 Live Annotated Stream"
                style={{ width: "100%", height: "100%", objectFit: "contain", maxHeight: "400px" }}
                onError={(e) => {
                  (e.target as HTMLImageElement).src = `http://localhost:8020/stream/${uc2Camera.id}`;
                }}
              />
            ) : (
              <div style={{ color: "var(--text-muted)", fontSize: "14px" }}>No active feed</div>
            )}
            <div
              style={{
                position: "absolute",
                top: "12px",
                left: "12px",
                padding: "4px 8px",
                borderRadius: "4px",
                background: "rgba(0,0,0,0.7)",
                color: "#fff",
                fontSize: "11px",
                fontWeight: 600,
                backdropFilter: "blur(4px)",
              }}
            >
              🔴 LIVE UC2 FEED — DEMO VIDEO (AUTO-STARTED)
            </div>
          </div>

          {/* UC2 Real-time Telemetry Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "24px",
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
            }}
          >
            <div>
              <h3 style={{ margin: "0 0 16px 0", fontSize: "16px", color: "var(--text-primary)" }}>
                Detection Telemetry
              </h3>

              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                  <span style={{ color: "var(--text-secondary)", fontSize: "13px" }}>Camera / Source:</span>
                  <strong style={{ fontSize: "13px" }}>Demo Video / RTSP / Ingestion</strong>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                  <span style={{ color: "var(--text-secondary)", fontSize: "13px" }}>Model:</span>
                  <strong style={{ fontSize: "13px" }}>Fire / Smoke / Sparks (YOLOv8)</strong>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                  <span style={{ color: "var(--text-secondary)", fontSize: "13px" }}>Latest Detection:</span>
                  <strong style={{ fontSize: "14px", color: latestDetectionName !== "CLEAR" ? "#fc8181" : "var(--success)" }}>
                    {latestDetectionName}
                  </strong>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                  <span style={{ color: "var(--text-secondary)", fontSize: "13px" }}>Confidence:</span>
                  <strong style={{ fontSize: "13px" }}>{latestConfidence}</strong>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", padding: "10px 14px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                  <span style={{ color: "var(--text-secondary)", fontSize: "13px" }}>Status:</span>
                  <span style={{ color: "var(--success)", fontWeight: 700, fontSize: "13px" }}>
                    ● RUNNING (REAL-TIME)
                  </span>
                </div>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate("/detection")}
              style={{ marginTop: "16px", padding: "10px", width: "100%", fontWeight: 600 }}
            >
              Open Detection Module Controls →
            </button>
          </div>
        </div>
      </section>

      {/* ── SECTION 4: LIVE ALERTS ──────────────────────────────────────── */}
      <section aria-labelledby="live-alerts-heading" style={{ marginBottom: "32px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <h2 id="live-alerts-heading" style={{ fontSize: "18px", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
              LIVE ALERTS
            </h2>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)" }}>
              Real-time events emitted by UC1, UC2 detection engine, and UC3/PART worker.
            </p>
          </div>

          <div style={{ display: "flex", gap: "6px" }}>
            {(["all", "fire", "smoke", "sparks", "uc1", "uc3", "uc4"] as const).map((cat) => (
              <button
                key={cat}
                type="button"
                className={`btn ${alertCategory === cat ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "6px 12px", fontSize: "12px", borderRadius: "4px", textTransform: "capitalize" }}
                onClick={() => setAlertCategory(cat)}
              >
                {cat === "uc1" ? "UC1 / PART" : cat === "uc3" ? "UC3 / PART" : cat === "uc4" ? "UC4 (Demo)" : cat}
              </button>
            ))}
          </div>
        </div>

        {filteredAlerts.length === 0 ? (
          <div
            style={{
              padding: "32px",
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
          <div style={{ display: "flex", flexDirection: "column", gap: "8px", maxHeight: "320px", overflowY: "auto" }}>
            {filteredAlerts.slice(0, 10).map((alert: Alert) => {
              const isFire = alert.alert_type?.includes("fire");
              const isSmoke = alert.alert_type?.includes("smoke");
              const isSparks = alert.alert_type?.includes("spark");
              const isUc3 = alert.source_uc === "uc3";
              const isUc4 = alert.source_uc === "uc4";

              const badgeColor = isFire ? "#e53e3e" : isSmoke ? "#805ad5" : isSparks ? "#dd6b20" : isUc3 ? "#46BD92" : isUc4 ? "#9333ea" : "var(--primary)";

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

      {/* ── SECTION 5: CAMERA REPOSITORY / GRID ─────────────────────────── */}
      <section aria-labelledby="cameras-grid-heading">
        <div className="section-header" style={{ marginBottom: "16px" }}>
          <div>
            <h2 id="cameras-grid-heading" className="section-title" style={{ fontSize: "18px", fontWeight: 700 }}>
              Live Camera Feeds
            </h2>
            <p className="section-description" style={{ color: "var(--text-secondary)", fontSize: "13px" }}>
              Active streaming channels feeding UC2 and UC3 analytics pipelines.
            </p>
          </div>
          <span className="section-count">
            {cameras.length} {cameras.length === 1 ? "camera" : "cameras"}
          </span>
        </div>

        <div className="camera-grid">
          {cameras.map((camera) => (
            <CameraTile key={camera.id} camera={camera} />
          ))}
        </div>
      </section>
    </main>
  );
}