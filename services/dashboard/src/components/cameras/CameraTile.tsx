import { useNavigate } from "react-router-dom";
import LiveFeed from "./LiveFeed";
import {
  ZONE_CONFIGS,
  type Camera,
} from "@/types/camera";
import { getUCModule, getUCBadgeStyle } from "@/modules/registry";

interface CameraTileProps {
  camera: Camera;
}

function getStatusLabel(status: Camera["status"]) {
  switch (status) {
    case "online":
      return "Online";
    case "offline":
      return "Offline";
    case "reconnecting":
      return "Reconnecting";
    case "disabled":
      return "Disabled";
    default:
      return status;
  }
}

export default function CameraTile({ camera }: CameraTileProps) {
  const navigate = useNavigate();

  const primaryUc = camera.use_cases[0]?.toLowerCase() || "uc1";
  const primaryModule = getUCModule(primaryUc);
  const primaryColor = primaryModule?.color ?? "#A646BD";
  const zoneConfig = camera.zone_id ? ZONE_CONFIGS[camera.zone_id] : null;

  // Determine zone badge label and styling
  const zoneBadgeText =
    zoneConfig?.typeLabel ||
    (camera.zone_type === "critical_hazard"
      ? "Critical Danger"
      : camera.zone_type === "deliberate_flame"
        ? "Controlled Flame"
        : camera.zone_type === "mandatory_ppe"
          ? "Mandatory PPE"
          : camera.zone_type === "restricted_entry"
            ? "Restricted Vault"
            : camera.zone_type === "speed_enforcement"
              ? "Speed Lane"
              : camera.zone_type === "access_control"
                ? "ANPR Gate"
                : "Active Zone");

  const zoneBadgeColor =
    zoneConfig?.badgeColor ||
    (primaryUc === "uc2"
      ? camera.zone_type === "deliberate_flame"
        ? "#f59e0b"
        : "#ef4444"
      : primaryUc === "uc4"
        ? "#0D9488"
        : primaryUc === "uc3"
          ? "#D97706"
          : "#1E3A8A");

  const zoneBadgeBg =
    zoneConfig?.badgeBg || `${zoneBadgeColor}22`;

  return (
    <article
      className="camera-tile"
      style={{
        borderTop: `3px solid ${primaryColor}`,
      }}
    >
      <button
        type="button"
        className="camera-tile-button"
        onClick={() => navigate(`/cameras/${camera.id}`)}
        aria-label={`Open ${camera.name}`}
      >
        <header className="camera-tile-header">
          <div className="camera-tile-heading">
            <div style={{ display: "flex", alignItems: "center", gap: "6px", flexWrap: "wrap", marginBottom: "4px" }}>
              {/* Dynamic UC Badges from Registry */}
              {camera.use_cases.map((ucId) => {
                const mod = getUCModule(ucId);
                const style = getUCBadgeStyle(ucId);
                return (
                  <span
                    key={ucId}
                    style={{
                      fontSize: "10px",
                      fontWeight: 700,
                      textTransform: "uppercase",
                      padding: "2px 6px",
                      borderRadius: "4px",
                      backgroundColor: style.backgroundColor,
                      color: style.color,
                      border: `1px solid ${style.borderColor}`,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "3px",
                    }}
                  >
                    {mod?.icon && <span>{mod.icon}</span>}
                    {mod ? mod.shortName.split(" ")[0] : ucId.toUpperCase()}
                  </span>
                );
              })}

              <span
                className="zone-badge"
                style={{
                  fontSize: "10px",
                  fontWeight: 650,
                  padding: "2px 6px",
                  borderRadius: "4px",
                  background: zoneBadgeBg,
                  color: zoneBadgeColor,
                  border: `1px solid ${zoneBadgeColor}44`,
                }}
              >
                ⬡ {zoneBadgeText}
              </span>
            </div>

            <h3>{camera.name}</h3>

            {camera.location && (
              <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                {camera.location}
              </span>
            )}
          </div>

          <span className={`status-badge status-${camera.status}`}>
            <span className="status-dot" />
            {getStatusLabel(camera.status)}
          </span>
        </header>

        <div className="camera-tile-feed" style={{ height: "210px" }}>
          <LiveFeed
            cameraId={camera.id}
            cameraName={camera.name}
            isOnline={camera.status === "online"}
            useCases={camera.use_cases}
            zoneId={camera.zone_id}
            zoneName={camera.zone_name}
            zoneType={camera.zone_type}
            demoVideo={camera.demo_video}
          />
        </div>

        {camera.zone_policy && (
          <div
            style={{
              padding: "6px 14px",
              background: "rgba(0, 0, 0, 0.25)",
              borderBottom: "1px solid var(--border)",
              fontSize: "11px",
              color: "var(--text-secondary)",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            <strong style={{ color: "var(--text-muted)", marginRight: "4px" }}>Policy:</strong>
            {camera.zone_policy}
          </div>
        )}

        <footer className="camera-tile-footer">
          <div className="camera-meta">
            <span>
              <strong>{camera.fps}</strong> FPS
            </span>

            <span className="meta-divider" />

            <span style={{ color: "var(--text-muted)" }}>
              {primaryModule?.name || camera.use_cases.join(", ").toUpperCase()}
            </span>
          </div>

          <span className="camera-view">
            Inspect Zone
            <span aria-hidden="true">→</span>
          </span>
        </footer>
      </button>
    </article>
  );
}