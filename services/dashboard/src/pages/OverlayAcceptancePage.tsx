import CameraOverlay from "@/components/cameras/CameraOverlay";

export function OverlayAcceptancePage() {
  const panelStyle = {
    position: "relative" as const,
    width: "480px",
    height: "270px",
    background: "#0f172a",
    border: "1px solid #334155",
    borderRadius: "8px",
    overflow: "hidden",
  };

  const imageStyle = {
    width: "100%",
    height: "100%",
    objectFit: "contain" as const,
    display: "block",
  };

  return (
    <div style={{ padding: "24px", background: "#020617", minHeight: "100vh", color: "#f8fafc", fontFamily: "sans-serif" }}>
      <header style={{ marginBottom: "20px" }}>
        <h1 style={{ fontSize: "22px", fontWeight: "bold", margin: "0 0 6px 0" }}>
          Production Browser Acceptance Gate — CameraOverlay Rendering
        </h1>
        <p style={{ margin: 0, color: "#94a3b8", fontSize: "14px" }}>
          Live end-to-end rendering test with actual API responses, aspect-ratio preservation, pillarboxing, and label verification.
        </p>
      </header>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(490px, 1fr))", gap: "24px" }}>
        {/* UC1 Landscape */}
        <div id="test-panel-uc1">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
            <span style={{ fontWeight: 600, color: "#38bdf8" }}>UC1 Intrusion (Landscape 1200x896)</span>
            <span id="uc1-status-badge" style={{ fontSize: "12px", background: "#0369a1", padding: "2px 8px", borderRadius: "4px" }}>API Active: 8021</span>
          </div>
          <div style={panelStyle}>
            <img className="live-feed-image" src="/test_media/uc1.jpg" alt="UC1 Feed" style={imageStyle} />
            <CameraOverlay cameraId="test-cam-uc1" useCases={["uc1"]} isOnline={true} />
          </div>
          <p style={{ fontSize: "12px", color: "#64748b", margin: "4px 0 0 0" }}>
            Verifies zone polygon (Restricted Security Perimeter) and intrusion label #FF3333.
          </p>
        </div>

        {/* UC2 Portrait */}
        <div id="test-panel-uc2">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
            <span style={{ fontWeight: 600, color: "#facc15" }}>UC2 Fire/Sparks (Portrait 704x1280)</span>
            <span id="uc2-status-badge" style={{ fontSize: "12px", background: "#854d0e", padding: "2px 8px", borderRadius: "4px" }}>API Active: 8022</span>
          </div>
          <div style={panelStyle}>
            <img className="live-feed-image" src="/test_media/uc2_portrait.jpg" alt="UC2 Feed" style={imageStyle} />
            <CameraOverlay cameraId="test-cam-uc2" useCases={["uc2"]} isOnline={true} />
          </div>
          <p style={{ fontSize: "12px", color: "#64748b", margin: "4px 0 0 0" }}>
            Verifies <strong>pillarboxing</strong>: lateral black bars with spark boxes precisely projected inside the video column.
          </p>
        </div>

        {/* UC3 Landscape */}
        <div id="test-panel-uc3">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
            <span style={{ fontWeight: 600, color: "#fb923c" }}>UC3 PPE Compliance (Landscape 1200x896)</span>
            <span id="uc3-status-badge" style={{ fontSize: "12px", background: "#9a3412", padding: "2px 8px", borderRadius: "4px" }}>API Active: 8023</span>
          </div>
          <div style={panelStyle}>
            <img className="live-feed-image" src="/test_media/uc3.jpg" alt="UC3 Feed" style={imageStyle} />
            <CameraOverlay cameraId="test-cam-uc3" useCases={["uc3"]} isOnline={true} />
          </div>
          <p style={{ fontSize: "12px", color: "#64748b", margin: "4px 0 0 0" }}>
            Verifies compliant items: Vest (#FF8A3D), Helmet (#FFC53D), Person (#94A3B8).
          </p>
        </div>

        {/* UC4 Landscape */}
        <div id="test-panel-uc4">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
            <span style={{ fontWeight: 600, color: "#4ade80" }}>UC4 Vehicles & Traffic (Landscape 1280x720)</span>
            <span id="uc4-status-badge" style={{ fontSize: "12px", background: "#166534", padding: "2px 8px", borderRadius: "4px" }}>API Active: 8024</span>
          </div>
          <div style={panelStyle}>
            <img className="live-feed-image" src="/test_media/uc4_landscape.jpg" alt="UC4 Feed" style={imageStyle} />
            <CameraOverlay cameraId="test-cam-uc4" useCases={["uc4"]} isOnline={true} />
          </div>
          <p style={{ fontSize: "12px", color: "#64748b", margin: "4px 0 0 0" }}>
            Verifies 16:9 full fit with Car bounding boxes and speed unavailable annotation.
          </p>
        </div>

        {/* Negative Test: Empty Detections */}
        <div id="test-panel-empty">
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
            <span style={{ fontWeight: 600, color: "#94a3b8" }}>Negative Test — Empty Detections</span>
            <span id="empty-status-badge" style={{ fontSize: "12px", background: "#334155", padding: "2px 8px", borderRadius: "4px" }}>API Active</span>
          </div>
          <div style={panelStyle}>
            <img className="live-feed-image" src="/test_media/blank.jpg" alt="Empty Feed" style={imageStyle} />
            <CameraOverlay cameraId="test-cam-empty" useCases={["uc1"]} isOnline={true} />
          </div>
          <p style={{ fontSize: "12px", color: "#64748b", margin: "4px 0 0 0" }}>
            Verifies canvas is completely clean when API returns empty detection list [].
          </p>
        </div>
      </div>
    </div>
  );
}

export default OverlayAcceptancePage;
