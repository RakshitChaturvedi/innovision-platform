import { useState, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  getCameras,
  getCameraStatus,
  getCameraVideoSessions,
  uploadCameraVideo,
  processCameraVideoSession,
  stopCameraVideoSession,
  type VideoSession,
} from "@/api/cameras";
import { getCameraHierarchy, getCameraEffectiveAnalytics } from "@/api/platform";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import LiveFeed from "@/components/cameras/LiveFeed";

export default function CameraDetail() {
  const { cameraId } = useParams<{ cameraId: string }>();
  const queryClient = useQueryClient();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const camerasQuery = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });

  const hierarchyQuery = useQuery({
    queryKey: ["cameraHierarchy", cameraId],
    queryFn: () => getCameraHierarchy(cameraId as string),
    enabled: Boolean(cameraId),
  });

  const effectiveQuery = useQuery({
    queryKey: ["cameraEffectiveAnalytics", cameraId],
    queryFn: () => getCameraEffectiveAnalytics(cameraId as string),
    enabled: Boolean(cameraId),
  });

  const statusQuery = useQuery({
    queryKey: ["camera", cameraId, "status"],
    queryFn: () => getCameraStatus(cameraId as string),
    enabled: Boolean(cameraId),
    refetchInterval: 5000,
  });

  const sessionsQuery = useQuery({
    queryKey: ["cameraVideoSessions", cameraId],
    queryFn: () => getCameraVideoSessions(cameraId as string),
    enabled: Boolean(cameraId),
    refetchInterval: (query) => {
      const hasActive = query.state.data?.some(
        (s) => s.status === "processing" || s.status === "queued"
      );
      return hasActive ? 2000 : 8000;
    },
  });

  if (!cameraId) {
    return <ErrorState message="Camera ID is missing." />;
  }

  if (camerasQuery.isLoading || hierarchyQuery.isLoading) {
    return <LoadingState />;
  }

  if (camerasQuery.isError) {
    return <ErrorState message="Failed to load camera feed." />;
  }

  const camera = camerasQuery.data?.find((item) => item.id === cameraId);

  if (!camera) {
    return <ErrorState message="Camera not found." />;
  }

  const status = statusQuery.data ?? camera.status;
  const hierarchy = hierarchyQuery.data;
  const effectiveList = effectiveQuery.data || [];
  const sessions = sessionsQuery.data || [];
  const activeSession = sessions.find((s) => s.session_id === activeSessionId);

  const statusLabel =
    status === "online"
      ? "Online"
      : status === "offline"
        ? "Offline"
        : status === "reconnecting"
          ? "Reconnecting"
          : "Disabled";

  const isSimulation = hierarchy?.is_simulation || hierarchy?.source_type === "test_simulation";
  const siteName = hierarchy?.site?.name || "Unassigned Site";
  const zoneName = hierarchy?.zone?.name || "Unassigned Zone";

  // File selection validation
  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setUploadError(null);
    setActionError(null);
    const file = e.target.files?.[0];
    if (!file) {
      setSelectedFile(null);
      return;
    }

    const validExtensions = [".mp4", ".mov", ".avi", ".mkv"];
    const fileExt = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (!validExtensions.includes(fileExt)) {
      setUploadError(`Invalid video format '${fileExt}'. Allowed formats: ${validExtensions.join(", ")}`);
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    if (file.size > 200 * 1024 * 1024) {
      setUploadError("File size exceeds 200 MB maximum limit.");
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    setSelectedFile(file);
  };

  const extractError = (err: unknown, fallback: string): string => {
    if (err && typeof err === "object") {
      const resp = (err as { response?: { data?: { detail?: string } }; message?: string });
      if (resp.response?.data?.detail) return resp.response.data.detail;
      if (resp.message) return resp.message;
    }
    return fallback;
  };

  // Upload handler
  const handleUpload = async () => {
    if (!selectedFile) return;
    setIsSubmitting(true);
    setUploadError(null);
    setActionError(null);
    setUploadProgress(0);

    try {
      const created = await uploadCameraVideo(cameraId, selectedFile, (pct) => {
        setUploadProgress(pct);
      });
      setSelectedFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      setUploadProgress(null);
      setActiveSessionId(created.session_id);
      await queryClient.invalidateQueries({ queryKey: ["cameraVideoSessions", cameraId] });
    } catch (err: unknown) {
      setUploadError(extractError(err, "Failed to upload video."));
      setUploadProgress(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Start processing session
  const handleStartSession = async (sessionId: string) => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await processCameraVideoSession(cameraId, sessionId);
      setActiveSessionId(sessionId);
      await queryClient.invalidateQueries({ queryKey: ["cameraVideoSessions", cameraId] });
    } catch (err: unknown) {
      setActionError(extractError(err, "Failed to start session processing."));
    } finally {
      setIsSubmitting(false);
    }
  };

  // Stop processing session
  const handleStopSession = async (sessionId: string) => {
    setIsSubmitting(true);
    setActionError(null);
    try {
      await stopCameraVideoSession(cameraId, sessionId);
      await queryClient.invalidateQueries({ queryKey: ["cameraVideoSessions", cameraId] });
    } catch (err: unknown) {
      setActionError(extractError(err, "Failed to stop session."));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <main className="page camera-detail-page">
      <header className="camera-detail-header">
        <Link to="/" className="back-link">
          ← Back to Dashboard
        </Link>

        <div className="camera-detail-title-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "12px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              <h1 className="page-title" style={{ margin: 0 }}>{camera.name}</h1>
              {isSimulation && (
                <span
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    padding: "3px 8px",
                    borderRadius: "4px",
                    background: "var(--warning-bg)",
                    color: "var(--warning)",
                    border: "1px solid rgba(189,154,70,0.3)",
                    letterSpacing: "0.5px",
                  }}
                >
                  TEST SIMULATION SOURCE
                </span>
              )}
            </div>

            <p className="page-description" style={{ marginTop: "4px" }}>
              📍 {siteName} • 🏢 {zoneName} • {camera.location ?? "Industrial Plant Zone"}
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            {activeSessionId && (
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 700,
                  padding: "4px 10px",
                  borderRadius: "4px",
                  background: "var(--primary-bg, rgba(99, 102, 241, 0.15))",
                  color: "var(--primary, #6366f1)",
                  border: "1px solid var(--primary, #6366f1)",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                }}
              >
                <span>SOURCE: UPLOADED VIDEO</span>
                <button
                  type="button"
                  onClick={() => setActiveSessionId(null)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "inherit",
                    cursor: "pointer",
                    fontSize: "12px",
                    padding: "0 2px",
                  }}
                  title="Switch to Live RTSP Feed"
                >
                  ✕
                </button>
              </span>
            )}
            <span className={`status-badge status-${status}`}>
              <span className="status-dot" />
              {statusLabel}
            </span>
          </div>
        </div>
      </header>

      {/* Feed Source Selector & Video Feed */}
      <section className="camera-detail-feed" aria-label={`${camera.name} live feed`} style={{ margin: "20px 0" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              type="button"
              className={`btn btn-sm ${!activeSessionId ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setActiveSessionId(null)}
              style={{
                fontSize: "12px",
                padding: "4px 12px",
                borderRadius: "4px",
                fontWeight: 600,
                cursor: "pointer",
                border: "1px solid var(--border)",
                background: !activeSessionId ? "var(--primary)" : "var(--surface)",
                color: !activeSessionId ? "#ffffff" : "var(--text-secondary)",
              }}
            >
              📹 Live RTSP Stream
            </button>
            {activeSession && (
              <button
                type="button"
                className="btn btn-sm btn-primary"
                style={{
                  fontSize: "12px",
                  padding: "4px 12px",
                  borderRadius: "4px",
                  fontWeight: 600,
                  cursor: "pointer",
                  border: "1px solid var(--accent, #6366f1)",
                  background: "var(--accent, #6366f1)",
                  color: "#ffffff",
                }}
              >
                🎬 Session: {activeSession.original_filename}
              </button>
            )}
          </div>
          <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
            Resolution: 1920×1080 • Overlay: Active Effective Analytics
          </span>
        </div>

        {!activeSession && status !== "online" && sessions.length === 0 ? (
          <div style={{ background: "var(--surface)", border: "1px dashed var(--border)", borderRadius: "8px", padding: "48px 24px", textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: "12px" }}>
            <div style={{ width: "48px", height: "48px", borderRadius: "50%", background: "var(--surface-raised)", border: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "22px" }}>
              🎬
            </div>
            <div style={{ fontSize: "16px", fontWeight: 700, color: "var(--text-primary)" }}>
              No Video Uploaded
            </div>
            <p style={{ fontSize: "13px", color: "var(--text-muted)", margin: 0, maxWidth: "460px", lineHeight: 1.5 }}>
              This camera is currently offline and no video session has been uploaded. Select a genuine recorded video file below to run safety analytics and PPE zone compliance verification.
            </p>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              style={{
                background: "var(--primary, #3b82f6)",
                color: "#ffffff",
                border: "none",
                borderRadius: "6px",
                padding: "8px 20px",
                fontSize: "13px",
                fontWeight: 600,
                cursor: "pointer",
                marginTop: "4px",
              }}
            >
              Choose Video File (.mp4, .mov, .avi)
            </button>
          </div>
        ) : (
          <LiveFeed
            cameraId={camera.id}
            cameraName={camera.name}
            isOnline={status === "online"}
            useCases={camera.use_cases}
            sessionId={activeSessionId || undefined}
            sessionFilename={activeSession?.original_filename}
          />
        )}
      </section>

      {/* Video Upload & Dynamic Analytics Sessions Panel (Phase B & C) */}
      <section
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          borderRadius: "8px",
          padding: "20px",
          marginBottom: "24px",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px" }}>
          <div>
            <h2 style={{ fontSize: "16px", fontWeight: 600, margin: "0 0 4px 0" }}>
              Upload Test Video & Run Camera Analytics
            </h2>
            <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: 0 }}>
              Upload custom video files (.mp4, .mov, .avi, .mkv) against this camera to run effective analytics and zone compliance rules with isolated frame routing.
            </p>
          </div>
        </div>

        {uploadError && (
          <div
            style={{
              padding: "10px 14px",
              background: "var(--danger-bg, rgba(239, 68, 68, 0.15))",
              color: "var(--danger, #ef4444)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "6px",
              fontSize: "12px",
              marginBottom: "14px",
            }}
          >
            <strong>Upload Error:</strong> {uploadError}
          </div>
        )}

        {actionError && (
          <div
            style={{
              padding: "10px 14px",
              background: "var(--danger-bg, rgba(239, 68, 68, 0.15))",
              color: "var(--danger, #ef4444)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "6px",
              fontSize: "12px",
              marginBottom: "14px",
            }}
          >
            <strong>Action Error:</strong> {actionError}
          </div>
        )}

        {/* Upload Controls Row */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "12px",
            alignItems: "center",
            padding: "16px",
            background: "var(--surface-raised, rgba(255, 255, 255, 0.03))",
            border: "1px dashed var(--border)",
            borderRadius: "6px",
            marginBottom: "20px",
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp4,.mov,.avi,.mkv"
            onChange={handleFileChange}
            disabled={isSubmitting}
            style={{ fontSize: "13px", color: "var(--text-secondary)" }}
          />

          <button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile || isSubmitting}
            style={{
              padding: "7px 16px",
              fontSize: "13px",
              fontWeight: 600,
              borderRadius: "4px",
              border: "none",
              background: selectedFile && !isSubmitting ? "var(--primary, #3b82f6)" : "var(--border)",
              color: "#ffffff",
              cursor: selectedFile && !isSubmitting ? "pointer" : "not-allowed",
            }}
          >
            {isSubmitting && uploadProgress !== null ? `Uploading (${uploadProgress}%)...` : "Upload Video"}
          </button>
        </div>

        {uploadProgress !== null && (
          <div style={{ marginBottom: "16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--text-muted)", marginBottom: "4px" }}>
              <span>Upload Progress</span>
              <span>{uploadProgress}%</span>
            </div>
            <div style={{ height: "6px", background: "var(--border)", borderRadius: "3px", overflow: "hidden" }}>
              <div style={{ width: `${uploadProgress}%`, height: "100%", background: "var(--primary)", transition: "width 0.2s" }} />
            </div>
          </div>
        )}

        {/* Video Sessions List */}
        <div>
          <h3 style={{ fontSize: "13px", fontWeight: 650, color: "var(--text-secondary)", margin: "0 0 10px 0", textTransform: "uppercase", letterSpacing: "0.5px" }}>
            Video Sessions ({sessions.length})
          </h3>

          {sessions.length === 0 ? (
            <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "13px", background: "var(--surface-raised)", borderRadius: "6px" }}>
              No uploaded video sessions found for this camera. Upload a video above to test analytics playback.
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {sessions.map((s: VideoSession) => {
                const isSelected = activeSessionId === s.session_id;
                const isProcessing = s.status === "processing";
                const isDone = s.status === "completed";
                const isStopped = s.status === "stopped";
                const isFailed = s.status === "failed";

                const statusColor = isProcessing
                  ? "var(--primary, #3b82f6)"
                  : isDone
                    ? "var(--success, #10b981)"
                    : isStopped
                      ? "var(--text-muted, #94a3b8)"
                      : isFailed
                        ? "var(--danger, #ef4444)"
                        : "var(--warning, #f59e0b)";

                const fileSizeMb = (s.file_size_bytes / (1024 * 1024)).toFixed(1);

                return (
                  <div
                    key={s.session_id}
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "14px 16px",
                      background: isSelected ? "var(--surface-raised, rgba(255, 255, 255, 0.05))" : "var(--surface)",
                      border: isSelected ? "1px solid var(--primary, #6366f1)" : "1px solid var(--border)",
                      borderRadius: "6px",
                      gap: "12px",
                    }}
                  >
                    <div style={{ minWidth: "220px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <span style={{ fontSize: "14px", fontWeight: 600, color: "var(--text-primary)" }}>
                          {s.original_filename}
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: "4px",
                            background: `rgba(0,0,0,0.15)`,
                            color: statusColor,
                            border: `1px solid ${statusColor}`,
                            textTransform: "uppercase",
                          }}
                        >
                          {s.status}
                        </span>
                      </div>
                      <div style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px" }}>
                        Size: {fileSizeMb} MB • Target: {s.fps} FPS • Frames: {s.processed_frames} / {s.total_frames || "—"} • ID: {s.session_id.slice(0, 8)}
                      </div>
                      {s.error_message && (
                        <div style={{ fontSize: "11px", color: "var(--danger)", marginTop: "2px" }}>
                          Error: {s.error_message}
                        </div>
                      )}
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      {/* View In Feed Toggle */}
                      <button
                        type="button"
                        onClick={() => setActiveSessionId(isSelected ? null : s.session_id)}
                        style={{
                          padding: "6px 12px",
                          fontSize: "12px",
                          fontWeight: 600,
                          borderRadius: "4px",
                          border: "1px solid var(--border)",
                          background: isSelected ? "var(--accent, #6366f1)" : "var(--surface)",
                          color: isSelected ? "#ffffff" : "var(--text-primary)",
                          cursor: "pointer",
                        }}
                      >
                        {isSelected ? "✓ Previewing" : "👁 Preview Feed"}
                      </button>

                      {/* Start / Re-run Analytics Button */}
                      {(() => {
                        const hasActiveAnalytics = effectiveList.some((e) => e.is_active);
                        return (
                          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "4px" }}>
                            <button
                              type="button"
                              onClick={() => handleStartSession(s.session_id)}
                              disabled={isProcessing || isSubmitting || !hasActiveAnalytics}
                              title={!hasActiveAnalytics ? "Cannot start analytics: no active analytics enabled for this camera/zone" : undefined}
                              style={{
                                padding: "6px 12px",
                                fontSize: "12px",
                                fontWeight: 600,
                                borderRadius: "4px",
                                border: "none",
                                background: isProcessing
                                  ? "var(--border)"
                                  : !hasActiveAnalytics
                                    ? "var(--surface-raised)"
                                    : "var(--success, #10b981)",
                                color: !hasActiveAnalytics ? "var(--text-muted)" : "#ffffff",
                                cursor: isProcessing || isSubmitting || !hasActiveAnalytics ? "not-allowed" : "pointer",
                              }}
                            >
                              {isProcessing ? "Processing..." : isDone ? "↻ Re-Run Analytics" : "▶ Start Analytics"}
                            </button>
                            {!hasActiveAnalytics && (
                              <span style={{ fontSize: "10px", color: "var(--warning, #f59e0b)" }}>
                                ⚠️ Analytics disabled in zone policy
                              </span>
                            )}
                          </div>
                        );
                      })()}

                      {/* Stop Button */}
                      {isProcessing && (
                        <button
                          type="button"
                          onClick={() => handleStopSession(s.session_id)}
                          disabled={isSubmitting}
                          style={{
                            padding: "6px 12px",
                            fontSize: "12px",
                            fontWeight: 600,
                            borderRadius: "4px",
                            border: "none",
                            background: "var(--danger, #ef4444)",
                            color: "#ffffff",
                            cursor: isSubmitting ? "not-allowed" : "pointer",
                          }}
                        >
                          ⏹ Stop
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </section>

      {/* Camera & Effective Analytics Details Panel */}
      <section className="camera-detail-info" aria-label="Camera information" style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "24px" }}>
        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Plant Site</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600 }}>{siteName}</span>
        </div>

        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Zone</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600 }}>{zoneName}</span>
        </div>

        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Lifecycle State</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600, color: "var(--success)" }}>{(hierarchy?.lifecycle_state || "active").toUpperCase()}</span>
        </div>

        <div className="detail-group">
          <span className="detail-label" style={{ display: "block", fontSize: "11px", fontWeight: 650, color: "var(--text-muted)", textTransform: "uppercase" }}>Frame Rate</span>
          <span className="detail-value" style={{ fontSize: "14px", fontWeight: 600 }}>{camera.fps} FPS</span>
        </div>
      </section>

      {/* Effective Analytics Panel (Phase 4 Integration) */}
      <section style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "24px" }}>
        <h2 style={{ fontSize: "16px", fontWeight: 600, margin: "0 0 4px 0" }}>Active Effective Analytics</h2>
        <p style={{ fontSize: "12px", color: "var(--text-muted)", margin: "0 0 16px 0" }}>
          Resolved active analytics capabilities based on organization subscription, zone policy, and camera override.
        </p>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "12px" }}>
          {effectiveList.length > 0 ? (
            effectiveList.map((eff) => {
              const sourceLabel =
                eff.source === "camera_override"
                  ? "Camera Override"
                  : eff.source === "zone"
                    ? "Zone Policy"
                    : "None";

              return (
                <div
                  key={eff.analytic_id}
                  style={{
                    background: "var(--surface-raised)",
                    border: eff.is_active ? "1px solid var(--border-hover)" : "1px solid var(--border)",
                    borderRadius: "6px",
                    padding: "14px",
                    opacity: eff.is_active ? 1 : 0.6,
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <span style={{ fontSize: "13px", fontWeight: 600, color: eff.is_active ? "var(--text-primary)" : "var(--text-muted)" }}>
                      {eff.display_name}
                    </span>
                    <span
                      style={{
                        fontSize: "10px",
                        fontWeight: 700,
                        padding: "2px 6px",
                        borderRadius: "4px",
                        background: eff.is_active ? "var(--success-bg)" : "var(--danger-bg)",
                        color: eff.is_active ? "var(--success)" : "var(--danger)",
                      }}
                    >
                      {eff.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>

                  <div style={{ fontSize: "11px", color: "var(--text-secondary)" }}>
                    Source: <strong style={{ color: "var(--primary)" }}>{sourceLabel}</strong>
                  </div>
                </div>
              );
            })
          ) : (
            <div style={{ fontSize: "13px", color: "var(--text-muted)" }}>No analytics enabled on this camera.</div>
          )}
        </div>
      </section>
    </main>
  );
}