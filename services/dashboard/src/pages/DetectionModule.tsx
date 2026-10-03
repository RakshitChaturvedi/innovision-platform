import { useState, useEffect, useRef } from "react";
import {
  detectImage,
  detectVideo,
  connectRtsp,
  stopRtsp,
  getRtspStatus,
  getDetectionStatus,
  type ImageDetectionResponse,
  type VideoDetectionResponse,
  type RtspStatusResponse,
  type DetectionModuleStatus,
} from "@/api/detection";

type InputMode = "image" | "video" | "rtsp";

const UC2_BASE_URL =
  import.meta.env.VITE_UC2_STREAM_URL || "http://localhost:8030";

export default function DetectionModule() {
  const [mode, setMode] = useState<InputMode>("image");
  const [modelStatus, setModelStatus] = useState<DetectionModuleStatus | null>(null);

  // Image mode state
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(false);
  const [imageResult, setImageResult] = useState<ImageDetectionResponse | null>(null);
  const [imageError, setImageError] = useState<string | null>(null);

  // Video mode state
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [videoLoading, setVideoLoading] = useState(false);
  const [videoResult, setVideoResult] = useState<VideoDetectionResponse | null>(null);
  const [videoError, setVideoError] = useState<string | null>(null);

  // RTSP mode state
  const [rtspUrl, setRtspUrl] = useState("rtsp://localhost:8554/live/fire_stream");
  const [rtspLoading, setRtspLoading] = useState(false);
  const [rtspStatus, setRtspStatus] = useState<RtspStatusResponse | null>(null);
  const [rtspError, setRtspError] = useState<string | null>(null);
  const rtspPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Fetch model metadata on mount
  useEffect(() => {
    getDetectionStatus()
      .then((data) => setModelStatus(data))
      .catch((err) => console.warn("Failed to fetch detection module status:", err));
  }, []);

  // Poll RTSP status when in RTSP mode or running
  useEffect(() => {
    if (mode === "rtsp" || rtspStatus?.status === "running") {
      const poll = () => {
        getRtspStatus()
          .then((status) => setRtspStatus(status))
          .catch(() => {});
      };
      poll();
      rtspPollRef.current = setInterval(poll, 2000);
      return () => {
        if (rtspPollRef.current) clearInterval(rtspPollRef.current);
      };
    }
  }, [mode, rtspStatus?.status]);

  // Image handlers
  const handleImageFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setImageFile(file);
      setImagePreview(URL.createObjectURL(file));
      setImageResult(null);
      setImageError(null);
    }
  };

  const handleRunImageDetection = async () => {
    if (!imageFile) return;
    setImageLoading(true);
    setImageError(null);
    try {
      const res = await detectImage(imageFile);
      setImageResult(res);
    } catch (err: any) {
      setImageError(err.response?.data?.detail || err.message || "Detection failed");
    } finally {
      setImageLoading(false);
    }
  };

  // Video handlers
  const handleVideoFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setVideoFile(file);
      setVideoResult(null);
      setVideoError(null);
    }
  };

  const handleRunVideoDetection = async () => {
    if (!videoFile) return;
    setVideoLoading(true);
    setVideoError(null);
    try {
      const res = await detectVideo(videoFile, 5);
      setVideoResult(res);
    } catch (err: any) {
      setVideoError(err.response?.data?.detail || err.message || "Video detection failed");
    } finally {
      setVideoLoading(false);
    }
  };

  // RTSP handlers
  const handleConnectRtsp = async () => {
    if (!rtspUrl.trim()) return;
    setRtspLoading(true);
    setRtspError(null);
    try {
      await connectRtsp(rtspUrl.trim());
      const status = await getRtspStatus();
      setRtspStatus(status);
    } catch (err: any) {
      setRtspError(err.response?.data?.detail || err.message || "RTSP connection failed");
    } finally {
      setRtspLoading(false);
    }
  };

  const handleStopRtsp = async () => {
    try {
      await stopRtsp();
      const status = await getRtspStatus();
      setRtspStatus(status);
    } catch (err: any) {
      setRtspError(err.message || "Failed to stop RTSP");
    }
  };

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Detection Module</h1>
          <p className="page-description">
            Multi-input computer vision inference interface powered by UC2 YOLOv8 Engine.
          </p>
        </div>
        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <span className="status-badge status-online">
            <span className="status-dot" />
            Model: {modelStatus ? "UC2 YOLOv8 (best.pt)" : "UC2 Fire/Smoke/Sparks"}
          </span>
        </div>
      </header>

      {/* Mode Selection Bar */}
      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "24px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "12px" }}>
          <div>
            <span style={{ fontSize: "13px", color: "var(--text-secondary)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.5px" }}>
              Select Input Source
            </span>
            <div style={{ display: "flex", gap: "8px", marginTop: "8px" }}>
              <button
                type="button"
                className={`btn ${mode === "image" ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "8px 16px", borderRadius: "6px", fontWeight: 600 }}
                onClick={() => setMode("image")}
              >
                🖼️ Image Upload
              </button>
              <button
                type="button"
                className={`btn ${mode === "video" ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "8px 16px", borderRadius: "6px", fontWeight: 600 }}
                onClick={() => setMode("video")}
              >
                🎬 Video Upload
              </button>
              <button
                type="button"
                className={`btn ${mode === "rtsp" ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "8px 16px", borderRadius: "6px", fontWeight: 600 }}
                onClick={() => setMode("rtsp")}
              >
                📡 RTSP Stream
              </button>
            </div>
          </div>

          <div style={{ fontSize: "12px", color: "var(--text-muted)", textAlign: "right" }}>
            <div><strong>Supported Classes:</strong> 0: Fire | 1: Smoke | 2: Sparks</div>
            <div><strong>Active Engine:</strong> YOLOv8 + Class Confidence Fusion + Temporal Verification</div>
          </div>
        </div>
      </section>

      {/* MODE 1: IMAGE UPLOAD */}
      {mode === "image" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "24px" }}>
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "var(--text-primary)" }}>
              Image Input
            </h3>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "16px" }}>
              Upload an image (JPG, PNG) to detect Fire, Smoke, and Sparks using UC2 inference.
            </p>

            <div style={{ marginBottom: "16px" }}>
              <label
                style={{
                  display: "block",
                  padding: "16px",
                  border: "2px dashed var(--border)",
                  borderRadius: "8px",
                  textAlign: "center",
                  cursor: "pointer",
                  background: "var(--surface-raised)",
                }}
              >
                <input
                  type="file"
                  accept="image/*"
                  onChange={handleImageFileChange}
                  style={{ display: "none" }}
                />
                <span style={{ fontSize: "14px", color: "var(--text-primary)" }}>
                  {imageFile ? `Selected: ${imageFile.name}` : "📁 Click to Choose Image File"}
                </span>
              </label>
            </div>

            {imagePreview && (
              <div style={{ marginBottom: "16px", borderRadius: "6px", overflow: "hidden", maxHeight: "280px" }}>
                <img
                  src={imagePreview}
                  alt="Selected preview"
                  style={{ width: "100%", height: "auto", maxHeight: "280px", objectFit: "contain", background: "#000" }}
                />
              </div>
            )}

            <button
              type="button"
              className="btn btn-primary"
              disabled={!imageFile || imageLoading}
              onClick={handleRunImageDetection}
              style={{ width: "100%", padding: "10px", fontWeight: 600 }}
            >
              {imageLoading ? "⚡ Running Detection..." : "Run Detection"}
            </button>

            {imageError && (
              <div style={{ marginTop: "12px", padding: "10px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: "6px", fontSize: "13px" }}>
                ❌ {imageError}
              </div>
            )}
          </div>

          {/* Image Result Display */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "var(--text-primary)" }}>
              Detection Result
            </h3>

            {!imageResult && !imageLoading && (
              <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)", fontSize: "14px" }}>
                Select an image and click <strong>Run Detection</strong> to view results.
              </div>
            )}

            {imageLoading && (
              <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-secondary)", fontSize: "14px" }}>
                ⏳ Processing frame through YOLOv8 model & temporal verification...
              </div>
            )}

            {imageResult && (
              <div>
                <div style={{ display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }}>
                  <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>MODEL</span>
                    <strong style={{ fontSize: "13px" }}>YOLOv8 best.pt (UC2)</strong>
                  </div>
                  <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>STATUS</span>
                    {imageResult.hazard_detected || imageResult.has_alert ? (
                      <strong style={{ fontSize: "13px", color: "#e53e3e" }}>
                        {imageResult.detections.some((d) => (d.class_name || d.class) === "fire")
                          ? "🔥 FIRE DETECTED"
                          : imageResult.detections.some((d) => (d.class_name || d.class) === "smoke")
                          ? "💨 SMOKE DETECTED"
                          : "✨ SPARKS DETECTED"}
                      </strong>
                    ) : (
                      <strong style={{ fontSize: "13px", color: "var(--success)" }}>
                        ✅ NO HAZARD DETECTED
                      </strong>
                    )}
                  </div>
                  <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>COUNT</span>
                    <strong style={{ fontSize: "13px" }}>{imageResult.detection_count ?? imageResult.detections?.length ?? 0} detections</strong>
                  </div>
                </div>

                {(imageResult.annotated_image || imageResult.annotated_image_base64) && (
                  <div style={{ marginBottom: "16px", borderRadius: "6px", overflow: "hidden", border: "1px solid var(--border)" }}>
                    <img
                      src={
                        imageResult.annotated_image?.startsWith("data:")
                          ? imageResult.annotated_image
                          : `data:image/jpeg;base64,${imageResult.annotated_image_base64 || imageResult.annotated_image}`
                      }
                      alt="Annotated detection"
                      style={{ width: "100%", height: "auto", maxHeight: "360px", objectFit: "contain", background: "#000" }}
                    />
                  </div>
                )}

                <div>
                  <h4 style={{ margin: "0 0 8px 0", fontSize: "13px", color: "var(--text-secondary)", textTransform: "uppercase" }}>
                    Detections ({imageResult.detections.length})
                  </h4>
                  {imageResult.detections.length === 0 ? (
                    <p style={{ fontSize: "13px", color: "var(--text-muted)" }}>✅ No hazards detected in this image.</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                      {imageResult.detections.map((d, idx) => {
                        const cName = (d.class_name || d.class || "hazard").toLowerCase();
                        const isFire = cName === "fire";
                        const isSmoke = cName === "smoke";
                        const badgeColor = isFire ? "#e53e3e" : isSmoke ? "#805ad5" : "#dd6b20";
                        const icon = isFire ? "🔥" : isSmoke ? "💨" : "✨";

                        return (
                          <div
                            key={idx}
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              padding: "10px 14px",
                              background: "var(--surface-raised)",
                              borderRadius: "6px",
                              borderLeft: `4px solid ${badgeColor}`,
                            }}
                          >
                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                                <span style={{ fontSize: "16px" }}>{icon}</span>
                                <strong style={{ textTransform: "uppercase", fontSize: "14px", color: "var(--text-primary)" }}>
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
                                  <span style={{ marginLeft: "12px", color: "var(--text-secondary)" }}>
                                    Occupancy: <strong>{d.area_percentage}%</strong> of frame
                                  </span>
                                )}
                                {d.width && d.height && (
                                  <span style={{ marginLeft: "12px" }}>
                                    Dimensions: {d.width}×{d.height}px
                                  </span>
                                )}
                              </div>
                            </div>
                            <span style={{ fontWeight: 800, fontSize: "16px", color: badgeColor }}>
                              {(d.confidence * 100).toFixed(1)}%
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODE 2: VIDEO UPLOAD */}
      {mode === "video" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "24px" }}>
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "var(--text-primary)" }}>
              Video Input
            </h3>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "16px" }}>
              Upload a recorded video clip (MP4, AVI) for frame-by-frame UC2 detection and temporal hazard aggregation.
            </p>

            <div style={{ marginBottom: "16px" }}>
              <label
                style={{
                  display: "block",
                  padding: "16px",
                  border: "2px dashed var(--border)",
                  borderRadius: "8px",
                  textAlign: "center",
                  cursor: "pointer",
                  background: "var(--surface-raised)",
                }}
              >
                <input
                  type="file"
                  accept="video/*"
                  onChange={handleVideoFileChange}
                  style={{ display: "none" }}
                />
                <span style={{ fontSize: "14px", color: "var(--text-primary)" }}>
                  {videoFile ? `Selected: ${videoFile.name}` : "📁 Click to Choose Video File"}
                </span>
              </label>
            </div>

            <button
              type="button"
              className="btn btn-primary"
              disabled={!videoFile || videoLoading}
              onClick={handleRunVideoDetection}
              style={{ width: "100%", padding: "10px", fontWeight: 600 }}
            >
              {videoLoading ? "⚡ Analyzing Video Frames..." : "Start Detection"}
            </button>

            {videoError && (
              <div style={{ marginTop: "12px", padding: "10px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: "6px", fontSize: "13px" }}>
                ❌ {videoError}
              </div>
            )}
          </div>

          {/* Video Result Display */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "var(--text-primary)" }}>
              Video Detection Timeline
            </h3>

            {!videoResult && !videoLoading && (
              <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)", fontSize: "14px" }}>
                Upload a video file to begin frame-level inference.
              </div>
            )}

            {videoLoading && (
              <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-secondary)", fontSize: "14px" }}>
                ⏳ Decoding video stream and evaluating temporal bounding boxes...
              </div>
            )}

            {videoResult && (
              <div>
                <div style={{ display: "flex", gap: "12px", marginBottom: "16px", flexWrap: "wrap" }}>
                  <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>PROCESSED FRAMES</span>
                    <strong style={{ fontSize: "13px" }}>{videoResult.processed_frames}</strong>
                  </div>
                  <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>TOTAL DETECTIONS</span>
                    <strong style={{ fontSize: "13px" }}>{videoResult.total_detections}</strong>
                  </div>
                  <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>HAZARD STATUS</span>
                    <strong style={{ fontSize: "13px", color: videoResult.total_detections > 0 ? "var(--danger)" : "var(--success)" }}>
                      {videoResult.total_detections > 0 ? "🚨 HAZARDS DETECTED" : "✅ CLEAR"}
                    </strong>
                  </div>
                </div>

                {videoResult.annotated_snapshot_base64 && (
                  <div style={{ marginBottom: "16px", borderRadius: "6px", overflow: "hidden", border: "1px solid var(--border)" }}>
                    <span style={{ fontSize: "11px", color: "var(--text-muted)", padding: "4px 8px", display: "block", background: "var(--surface-raised)" }}>
                      Annotated Keyframe Snapshot
                    </span>
                    <img
                      src={`data:image/jpeg;base64,${videoResult.annotated_snapshot_base64}`}
                      alt="Annotated video keyframe"
                      style={{ width: "100%", height: "auto", maxHeight: "260px", objectFit: "contain", background: "#000" }}
                    />
                  </div>
                )}

                <div style={{ maxHeight: "240px", overflowY: "auto" }}>
                  <h4 style={{ margin: "0 0 8px 0", fontSize: "13px", color: "var(--text-secondary)", textTransform: "uppercase" }}>
                    Frame Events ({videoResult.timeline.length})
                  </h4>
                  {videoResult.timeline.map((frame, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: "8px 12px",
                        background: "var(--surface-raised)",
                        borderRadius: "6px",
                        marginBottom: "6px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ fontSize: "12px", color: "var(--text-secondary)" }}>
                        Frame #{frame.frame_index} ({frame.timestamp_seconds}s)
                      </span>
                      <div style={{ display: "flex", gap: "6px" }}>
                        {frame.detections.map((d, dIdx) => (
                          <span
                            key={dIdx}
                            style={{
                              fontSize: "11px",
                              padding: "2px 6px",
                              borderRadius: "4px",
                              background: d.class_name === "fire" ? "rgba(229, 62, 62, 0.2)" : "rgba(128, 90, 213, 0.2)",
                              color: d.class_name === "fire" ? "#fc8181" : "#b794f4",
                              fontWeight: 600,
                            }}
                          >
                            {d.class_name} {(d.confidence * 100).toFixed(0)}%
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* MODE 3: RTSP CAMERA CONNECTION */}
      {mode === "rtsp" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))", gap: "24px" }}>
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "var(--text-primary)" }}>
              RTSP Camera Connection
            </h3>
            <p style={{ fontSize: "13px", color: "var(--text-secondary)", marginBottom: "16px" }}>
              Connect directly to an RTSP IP camera or live media stream. Frame acquisition and YOLOv8 inference run autonomously on the backend.
            </p>

            <div style={{ marginBottom: "16px" }}>
              <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "6px" }}>
                RTSP URL:
              </label>
              <input
                type="text"
                value={rtspUrl}
                onChange={(e) => setRtspUrl(e.target.value)}
                placeholder="rtsp://192.168.1.100:554/stream"
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  background: "var(--surface-raised)",
                  border: "1px solid var(--border)",
                  borderRadius: "6px",
                  color: "var(--text-primary)",
                  fontSize: "13px",
                  fontFamily: "var(--mono)",
                }}
              />
            </div>

            <div style={{ display: "flex", gap: "10px" }}>
              <button
                type="button"
                className="btn btn-primary"
                disabled={rtspLoading || rtspStatus?.status === "running"}
                onClick={handleConnectRtsp}
                style={{ flex: 1, padding: "10px", fontWeight: 600 }}
              >
                {rtspLoading ? "Connecting..." : "Connect & Start"}
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                disabled={rtspStatus?.status !== "running"}
                onClick={handleStopRtsp}
                style={{ padding: "10px 20px", fontWeight: 600, color: "var(--danger)" }}
              >
                Stop
              </button>
            </div>

            {rtspError && (
              <div style={{ marginTop: "12px", padding: "10px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: "6px", fontSize: "13px" }}>
                ❌ {rtspError}
              </div>
            )}
          </div>

          {/* RTSP Live Result & Telemetry */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <h3 style={{ margin: "0 0 12px 0", fontSize: "16px", color: "var(--text-primary)" }}>
              Live Stream & Telemetry
            </h3>

            {/* Live MJPEG feed */}
            {rtspStatus?.status === "running" ? (
              <div style={{ marginBottom: "16px", borderRadius: "6px", overflow: "hidden", border: "1px solid var(--border)", background: "#000" }}>
                <img
                  src={`${UC2_BASE_URL}/detection/rtsp/stream`}
                  alt="Live RTSP Detection Feed"
                  style={{ width: "100%", height: "auto", maxHeight: "280px", objectFit: "contain", display: "block" }}
                />
              </div>
            ) : (
              <div style={{ padding: "40px 20px", textAlign: "center", color: "var(--text-muted)", fontSize: "14px", border: "1px dashed var(--border)", borderRadius: "6px", marginBottom: "16px" }}>
                RTSP Stream is currently <strong>{rtspStatus?.status?.toUpperCase() || "IDLE"}</strong>. Enter URL and click Connect.
              </div>
            )}

            {/* Telemetry card */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "10px", marginBottom: "16px" }}>
              <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>STREAM STATUS</span>
                <strong style={{ fontSize: "13px", color: rtspStatus?.status === "running" ? "var(--success)" : "var(--text-secondary)" }}>
                  {rtspStatus?.status?.toUpperCase() || "OFFLINE"}
                </strong>
              </div>
              <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>FPS</span>
                <strong style={{ fontSize: "13px" }}>{rtspStatus?.fps ?? 0} FPS</strong>
              </div>
              <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>ALERT STATUS</span>
                <strong style={{ fontSize: "13px", color: rtspStatus?.alert_status === "ALERT" ? "var(--danger)" : "var(--success)" }}>
                  {rtspStatus?.alert_status || "CLEAR"}
                </strong>
              </div>
              <div style={{ padding: "8px 12px", background: "var(--surface-raised)", borderRadius: "6px" }}>
                <span style={{ fontSize: "11px", color: "var(--text-muted)", display: "block" }}>MAX CONFIDENCE</span>
                <strong style={{ fontSize: "13px" }}>
                  {rtspStatus?.latest_confidence ? `${(rtspStatus.latest_confidence * 100).toFixed(1)}%` : "0.0%"}
                </strong>
              </div>
            </div>

            {/* Latest detections */}
            <div>
              <span style={{ fontSize: "11px", color: "var(--text-muted)", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>
                Active Detections
              </span>
              {rtspStatus?.latest_detections && rtspStatus.latest_detections.length > 0 ? (
                <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
                  {rtspStatus.latest_detections.map((d, i) => (
                    <span
                      key={i}
                      style={{
                        padding: "4px 8px",
                        background: d.class_name === "fire" ? "rgba(229, 62, 62, 0.2)" : "rgba(128, 90, 213, 0.2)",
                        color: d.class_name === "fire" ? "#fc8181" : "#b794f4",
                        borderRadius: "4px",
                        fontSize: "12px",
                        fontWeight: 600,
                      }}
                    >
                      {d.class_name} ({(d.confidence * 100).toFixed(0)}%)
                    </span>
                  ))}
                </div>
              ) : (
                <span style={{ fontSize: "12px", color: "var(--text-muted)" }}>No hazards detected</span>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
