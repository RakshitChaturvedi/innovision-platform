import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Search,
  MapPin,
  Clock,
  Gauge,
  AlertTriangle,
  CheckCircle2,
  X,
  Navigation,
} from "lucide-react";
import { getTrackingJourney, getUC4Cameras } from "../api";
import type { UC4Camera, TrackingResult, TrackingNode } from "../types";

const SUGGESTED_PLATES = ["KA01MJ4921", "DL08CA2020", "MH12DE1433", "TS09FA8811", "HR26DK8392"];

export function TrackingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialPlate = searchParams.get("plate") || "KA01MJ4921";

  const [searchQuery, setSearchQuery] = useState(initialPlate);
  const [activePlate, setActivePlate] = useState(initialPlate);
  const [trackingData, setTrackingData] = useState<TrackingResult | null>(null);
  const [allCameras, setAllCameras] = useState<UC4Camera[]>([]);
  const [selectedNode, setSelectedNode] = useState<TrackingNode | null>(null);
  const [selectedCamera, setSelectedCamera] = useState<UC4Camera | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getUC4Cameras().then(setAllCameras);
  }, []);

  useEffect(() => {
    if (!activePlate) {
      setTrackingData(null);
      return;
    }
    setLoading(true);
    getTrackingJourney(activePlate)
      .then((res) => {
        setTrackingData(res);
        if (res.lastSeen) {
          setSelectedNode(res.lastSeen);
        }
      })
      .finally(() => setLoading(false));
  }, [activePlate]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const query = searchQuery.trim().toUpperCase();
    if (query) {
      setActivePlate(query);
      setSearchParams({ plate: query });
    }
  };

  const handleSelectSuggestion = (plate: string) => {
    setSearchQuery(plate);
    setActivePlate(plate);
    setSearchParams({ plate });
  };

  // Coordinates helper for the SVG map
  const getCameraPos = (index: number) => {
    // Generate clean layout coordinates across a 800x500 campus grid
    const positions = [
      { x: 180, y: 340 }, // Main Gate
      { x: 420, y: 160 }, // North Lane
      { x: 620, y: 320 }, // Logistics Bay
      { x: 340, y: 410 }, // South Lane
      { x: 680, y: 180 }, // East Lane
    ];
    return positions[index % positions.length] || { x: 200 + (index * 120) % 500, y: 200 + (index * 80) % 250 };
  };

  const cameraPosMap = new Map<string, { x: number; y: number }>();
  allCameras.forEach((cam, idx) => {
    cameraPosMap.set(cam.id, getCameraPos(idx));
  });

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
            <Navigation size={20} />
          </span>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: 700, margin: 0, letterSpacing: "-0.01em" }}>
              Vehicle Tracking & Route Journey
            </h1>
            <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "3px 0 0" }}>
              Chronological ANPR plate tracking and multi-camera route reconstruction
            </p>
          </div>
        </div>
      </div>

      {/* Main Container */}
      <div
        style={{
          position: "relative",
          width: "100%",
          height: "calc(100vh - 180px)",
          minHeight: "620px",
          borderRadius: "10px",
          border: "1px solid var(--border)",
          overflow: "hidden",
          background: "#0c0e14",
          boxShadow: "0 4px 20px rgba(0,0,0,0.3)",
        }}
      >
        {/* Background Campus Road SVG Layout */}
        <div style={{ position: "absolute", inset: 0 }}>
          <svg style={{ width: "100%", height: "100%" }} viewBox="0 0 800 500" preserveAspectRatio="xMidYMid slice">
            <defs>
              <pattern id="campusGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(255, 255, 255, 0.03)" strokeWidth="1" />
              </pattern>
              <marker id="routeArrow" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 2 L 10 5 L 0 8 z" fill="#0D9488" />
              </marker>
            </defs>

            <rect width="100%" height="100%" fill="#0a0c10" />
            <rect width="100%" height="100%" fill="url(#campusGrid)" />

            {/* Campus Road Network Paths */}
            <path d="M 80 340 L 720 340" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="18" fill="none" strokeLinecap="round" />
            <path d="M 80 340 L 720 340" stroke="#0e121a" strokeWidth="14" fill="none" strokeLinecap="round" />
            <path d="M 80 340 L 720 340" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="1.5" strokeDasharray="8 8" fill="none" />

            <path d="M 420 80 L 420 440" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="18" fill="none" strokeLinecap="round" />
            <path d="M 420 80 L 420 440" stroke="#0e121a" strokeWidth="14" fill="none" strokeLinecap="round" />
            <path d="M 420 80 L 420 440" stroke="rgba(255, 255, 255, 0.2)" strokeWidth="1.5" strokeDasharray="8 8" fill="none" />

            <path d="M 180 340 Q 300 240, 420 160 T 620 320" stroke="rgba(255, 255, 255, 0.08)" strokeWidth="16" fill="none" />
            <path d="M 180 340 Q 300 240, 420 160 T 620 320" stroke="#0e121a" strokeWidth="12" fill="none" />

            {/* Trajectory Route Path Polyline */}
            {trackingData && trackingData.nodes.length > 1 && (
              <polyline
                points={trackingData.nodes
                  .map((node) => {
                    const pos = cameraPosMap.get(node.camera.id) || { x: 400, y: 250 };
                    return `${pos.x},${pos.y}`;
                  })
                  .join(" ")}
                fill="none"
                stroke="#0D9488"
                strokeWidth="3.5"
                strokeDasharray="8 6"
                markerEnd="url(#routeArrow)"
                style={{ filter: "drop-shadow(0 0 6px rgba(13, 148, 136, 0.6))" }}
              />
            )}

            {/* Campus Building Polygons */}
            <rect x="230" y="190" width="120" height="90" rx="4" fill="rgba(255, 255, 255, 0.03)" stroke="rgba(255, 255, 255, 0.08)" />
            <text x="250" y="240" fill="rgba(255, 255, 255, 0.2)" fontSize="10" fontFamily="sans-serif" fontWeight="bold">ADMIN BLOCK</text>

            <rect x="470" y="190" width="110" height="90" rx="4" fill="rgba(255, 255, 255, 0.03)" stroke="rgba(255, 255, 255, 0.08)" />
            <text x="485" y="240" fill="rgba(255, 255, 255, 0.2)" fontSize="10" fontFamily="sans-serif" fontWeight="bold">TECH WING</text>
          </svg>

          {/* Interactive Camera Nodes on Map */}
          {allCameras.map((camera, idx) => {
            const pos = cameraPosMap.get(camera.id) || { x: 400, y: 250 };
            const nodeIndex = trackingData?.nodes.findIndex((n) => n.camera.id === camera.id) ?? -1;
            const isInRoute = nodeIndex >= 0;

            return (
              <div
                key={camera.id}
                style={{
                  position: "absolute",
                  left: `${(pos.x / 800) * 100}%`,
                  top: `${(pos.y / 500) * 100}%`,
                  transform: "translate(-50%, -50%)",
                  cursor: "pointer",
                  zIndex: 10,
                }}
                onClick={() => setSelectedCamera(camera)}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: isInRoute ? "28px" : "20px",
                    height: isInRoute ? "28px" : "20px",
                    borderRadius: "50%",
                    background: isInRoute ? "#0D9488" : "var(--surface)",
                    border: `2px solid ${isInRoute ? "#ffffff" : "var(--border)"}`,
                    color: "#ffffff",
                    fontSize: "11px",
                    fontWeight: 800,
                    boxShadow: isInRoute ? "0 0 14px rgba(13, 148, 136, 0.8)" : "none",
                    transition: "transform 0.2s",
                  }}
                >
                  {isInRoute ? nodeIndex + 1 : idx + 1}
                </div>
                <div
                  style={{
                    position: "absolute",
                    top: "100%",
                    left: "50%",
                    transform: "translateX(-50%)",
                    whiteSpace: "nowrap",
                    fontSize: "10px",
                    fontWeight: 600,
                    color: isInRoute ? "#0D9488" : "var(--text-muted)",
                    background: "rgba(15, 17, 23, 0.85)",
                    padding: "2px 6px",
                    borderRadius: "4px",
                    marginTop: "4px",
                    border: "1px solid rgba(255, 255, 255, 0.05)",
                  }}
                >
                  {camera.name.split("—")[0].trim()}
                </div>
              </div>
            );
          })}
        </div>

        {/* Floating Left Search & Timeline Panel */}
        <div
          style={{
            position: "absolute",
            top: "16px",
            left: "16px",
            width: "320px",
            maxHeight: "calc(100% - 32px)",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
            zIndex: 20,
            overflowY: "auto",
          }}
        >
          {/* Plate Search Form */}
          <div
            style={{
              background: "rgba(21, 23, 30, 0.95)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "14px",
              backdropFilter: "blur(8px)",
              boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            }}
          >
            <span
              style={{
                display: "block",
                fontSize: "10px",
                fontWeight: 650,
                color: "var(--text-muted)",
                letterSpacing: "0.08em",
                textTransform: "uppercase",
                marginBottom: "8px",
              }}
            >
              Plate Tracking Search
            </span>

            <form onSubmit={handleSearch} style={{ display: "flex", gap: "6px" }}>
              <input
                type="text"
                placeholder="Search plate (e.g. KA01MJ4921)"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value.toUpperCase())}
                style={{
                  flex: 1,
                  height: "36px",
                  padding: "0 10px",
                  borderRadius: "6px",
                  border: "1px solid var(--border)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  fontFamily: "var(--mono)",
                  fontSize: "12px",
                  outline: "none",
                }}
              />
              <button
                type="submit"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "36px",
                  height: "36px",
                  borderRadius: "6px",
                  border: "none",
                  background: "#0D9488",
                  color: "#ffffff",
                  cursor: "pointer",
                }}
              >
                <Search size={16} />
              </button>
            </form>

            {/* Quick Suggestion Chips */}
            <div style={{ marginTop: "10px", display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {SUGGESTED_PLATES.map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => handleSelectSuggestion(p)}
                  style={{
                    padding: "3px 7px",
                    borderRadius: "4px",
                    border: `1px solid ${activePlate === p ? "#0D9488" : "var(--border)"}`,
                    background: activePlate === p ? "rgba(13, 148, 136, 0.2)" : "rgba(255, 255, 255, 0.04)",
                    color: activePlate === p ? "#0D9488" : "var(--text-secondary)",
                    fontFamily: "var(--mono)",
                    fontSize: "10px",
                    cursor: "pointer",
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Chronological Detection Timeline */}
          {trackingData && (
            <div
              style={{
                background: "rgba(21, 23, 30, 0.95)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "14px",
                backdropFilter: "blur(8px)",
                boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 650,
                    color: "var(--text-muted)",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                  }}
                >
                  Trajectory Journey
                </span>
                <span
                  style={{
                    padding: "2px 6px",
                    borderRadius: "4px",
                    background: "rgba(13, 148, 136, 0.15)",
                    color: "#0D9488",
                    fontFamily: "var(--mono)",
                    fontSize: "11px",
                    fontWeight: 700,
                  }}
                >
                  {activePlate}
                </span>
              </div>

              {loading ? (
                <div style={{ padding: "12px", fontSize: "12px", color: "var(--text-muted)" }}>Searching nodes...</div>
              ) : trackingData.nodes.length === 0 ? (
                <div style={{ padding: "12px", fontSize: "12px", color: "var(--text-muted)" }}>
                  No detections recorded for this license plate.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {trackingData.nodes.map((node, i) => (
                    <div
                      key={node.event.event_id}
                      onClick={() => setSelectedNode(node)}
                      style={{
                        padding: "10px",
                        borderRadius: "6px",
                        border: `1px solid ${selectedNode?.event.event_id === node.event.event_id ? "#0D9488" : "var(--border)"}`,
                        background: selectedNode?.event.event_id === node.event.event_id ? "rgba(13, 148, 136, 0.12)" : "rgba(255, 255, 255, 0.02)",
                        cursor: "pointer",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                        <span style={{ fontSize: "12px", fontWeight: 650, color: "var(--text-primary)" }}>
                          #{i + 1} {node.camera.name.split("—")[0].trim()}
                        </span>
                        {node.event.is_violation ? (
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "3px",
                              fontSize: "10px",
                              color: "var(--danger)",
                              fontWeight: 650,
                            }}
                          >
                            <AlertTriangle size={11} /> Speeding
                          </span>
                        ) : (
                          <span style={{ fontSize: "10px", color: "var(--success)" }}>
                            <CheckCircle2 size={11} /> Normal
                          </span>
                        )}
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", color: "var(--text-secondary)" }}>
                        <span>
                          <Clock size={11} style={{ display: "inline", marginRight: "4px" }} />
                          {new Date(node.event.entry_time).toLocaleTimeString()}
                        </span>
                        <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>
                          <Gauge size={11} style={{ display: "inline", marginRight: "4px" }} />
                          {node.event.speed_kmh} km/h
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Floating Right HUD Card: Last Seen Summary */}
        {trackingData?.lastSeen && (
          <div
            style={{
              position: "absolute",
              bottom: "16px",
              right: "16px",
              width: "280px",
              background: "rgba(21, 23, 30, 0.95)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "14px",
              backdropFilter: "blur(8px)",
              boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
              zIndex: 20,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 650,
                  color: "var(--text-muted)",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                }}
              >
                Last Seen Position
              </span>
              <span
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "50%",
                  background: "var(--success)",
                  boxShadow: "0 0 8px var(--success)",
                }}
              />
            </div>

            <div style={{ fontSize: "16px", fontWeight: 700, fontFamily: "var(--mono)", color: "var(--text-primary)", marginBottom: "4px" }}>
              {trackingData.lastSeen.event.license_plate}
            </div>

            <div style={{ fontSize: "11px", color: "var(--text-secondary)", marginBottom: "8px" }}>
              <MapPin size={12} style={{ display: "inline", marginRight: "4px", color: "#0D9488" }} />
              {trackingData.lastSeen.camera.name}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "8px",
                borderTop: "1px solid var(--border)",
                paddingTop: "8px",
                fontSize: "11px",
              }}
            >
              <div>
                <span style={{ color: "var(--text-muted)", display: "block", fontSize: "10px" }}>SPEED</span>
                <span style={{ fontWeight: 600, color: trackingData.lastSeen.event.is_violation ? "var(--danger)" : "var(--text-primary)" }}>
                  {trackingData.lastSeen.event.speed_kmh} km/h
                </span>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)", display: "block", fontSize: "10px" }}>TIME</span>
                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                  {new Date(trackingData.lastSeen.event.entry_time).toLocaleTimeString()}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Floating Camera Detail Modal / HUD Card */}
        {selectedCamera && (
          <div
            style={{
              position: "absolute",
              top: "16px",
              right: "16px",
              width: "280px",
              background: "rgba(21, 23, 30, 0.95)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "14px",
              backdropFilter: "blur(8px)",
              boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
              zIndex: 20,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
              <span
                style={{
                  fontSize: "10px",
                  fontWeight: 650,
                  color: "var(--text-muted)",
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                }}
              >
                Camera Node Info
              </span>
              <button
                type="button"
                onClick={() => setSelectedCamera(null)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                }}
              >
                <X size={14} />
              </button>
            </div>

            <h3 style={{ fontSize: "13px", fontWeight: 700, margin: "0 0 4px", color: "var(--text-primary)" }}>
              {selectedCamera.name}
            </h3>
            <p style={{ fontSize: "11px", color: "var(--text-secondary)", margin: "0 0 10px" }}>
              {selectedCamera.location || "Campus Zone"}
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "6px", fontSize: "11px", borderTop: "1px solid var(--border)", paddingTop: "8px" }}>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Status:</span>
                <span style={{ color: "var(--success)", fontWeight: 600 }}>{selectedCamera.status}</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Speed Limit:</span>
                <span style={{ fontWeight: 600 }}>{selectedCamera.speed_limit_kmh} km/h</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between" }}>
                <span style={{ color: "var(--text-muted)" }}>Span Distance:</span>
                <span style={{ fontWeight: 600 }}>{selectedCamera.distance_between_lines_meters}m</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default TrackingPage;
