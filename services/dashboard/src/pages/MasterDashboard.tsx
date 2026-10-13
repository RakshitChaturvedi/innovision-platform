import { useState, useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { getCamerasResult } from "@/api/cameras";
import { getAlerts, getPendingAlertsCount } from "@/api/alerts";

import { ErrorState } from "@/components/common/ErrorState";
import { LoadingState } from "@/components/common/LoadingState";
import { EmptyState } from "@/components/common/EmptyState";
import { PageHeader } from "@/components/common/PageHeader";
import { StatCard } from "@/components/common/StatCard";
import CameraTile from "@/components/cameras/CameraTile";

import {
  getAllUCModules,
  getUCBadgeStyle,
} from "@/modules/registry";
import type { Camera } from "@/types/camera";

type ViewMode = "by_use_case" | "by_zone_type" | "all_grid";

export default function MasterDashboard() {
  const [viewMode, setViewMode] = useState<ViewMode>("by_use_case");
  const [selectedUc, setSelectedUc] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const allModules = useMemo(() => getAllUCModules(), []);

  // Fetch cameras with fallback detection
  const camerasQuery = useQuery({
    queryKey: ["cameras-result"],
    queryFn: getCamerasResult,
    refetchInterval: 5000,
  });

  // Fetch alerts metrics from backend
  const pendingCountQuery = useQuery({
    queryKey: ["alerts-pending-count"],
    queryFn: getPendingAlertsCount,
    refetchInterval: 10000,
  });

  const alertsQuery = useQuery({
    queryKey: ["alerts-summary"],
    queryFn: () => getAlerts({ limit: 100 }),
    refetchInterval: 10000,
  });

  const cameras = useMemo(
    () => camerasQuery.data?.cameras ?? [],
    [camerasQuery.data?.cameras],
  );
  const isDemoFallback = Boolean(camerasQuery.data?.isDemoFallback);

  // Compute live alert metrics
  const pendingAlertsCount = pendingCountQuery.data ?? 0;
  const liveAlerts = useMemo(
    () => alertsQuery.data ?? [],
    [alertsQuery.data],
  );
  const criticalCount = liveAlerts.filter(
    (a) => a.severity === "critical" || a.severity === "high",
  ).length;

  const alertsByUc = useMemo(() => {
    const counts: Record<string, number> = {
      uc1: 0,
      uc2: 0,
      uc3: 0,
      uc4: 0,
    };
    for (const a of liveAlerts) {
      const uc = a.source_uc?.toLowerCase();
      if (counts[uc] !== undefined) {
        counts[uc]++;
      }
    }
    return counts;
  }, [liveAlerts]);

  // Filtered cameras based on user selections
  const filteredCameras = useMemo(() => {
    return cameras.filter((cam) => {
      // Use Case filter
      if (selectedUc !== "all") {
        const matchesUc = cam.use_cases.some(
          (u) => u.toLowerCase() === selectedUc.toLowerCase(),
        );
        if (!matchesUc) return false;
      }

      // Search query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesName = cam.name.toLowerCase().includes(q);
        const matchesLoc = (cam.location || "").toLowerCase().includes(q);
        const matchesZone = (cam.zone_name || "").toLowerCase().includes(q);
        const matchesPolicy = (cam.zone_policy || "").toLowerCase().includes(q);
        if (!matchesName && !matchesLoc && !matchesZone && !matchesPolicy) {
          return false;
        }
      }

      return true;
    });
  }, [cameras, selectedUc, searchQuery]);

  if (camerasQuery.isLoading) {
    return <LoadingState message="Loading platform camera topology..." />;
  }

  if (camerasQuery.isError) {
    return <ErrorState message="Failed to load cameras." onRetry={() => camerasQuery.refetch()} />;
  }

  if (cameras.length === 0) {
    return <EmptyState message="No cameras registered in system." />;
  }

  const onlineCount = cameras.filter((c) => c.status === "online").length;

  // Group cameras by Zone Type
  const zoneGroups: Record<
    string,
    { title: string; description: string; color: string; cameras: Camera[] }
  > = {
    critical_hazard: {
      title: "Critical Danger & Thermal Core (UC2)",
      description: "Zero-tolerance fire & smoke hazard zones with immediate suppression triggers",
      color: "#ef4444",
      cameras: filteredCameras.filter((c) => c.zone_type === "critical_hazard"),
    },
    deliberate_flame: {
      title: "Controlled Flame & Welding Bays (UC2)",
      description: "Deliberate work flame permitted in ROI; alerts trigger on rollout or toxic smoke",
      color: "#f59e0b",
      cameras: filteredCameras.filter((c) => c.zone_type === "deliberate_flame"),
    },
    mandatory_ppe: {
      title: "PPE Safety Inspection Sectors (UC3)",
      description: "Mandatory hardhat, safety boots, and high-visibility vest compliance areas",
      color: "#D97706",
      cameras: filteredCameras.filter((c) => c.zone_type === "mandatory_ppe"),
    },
    access_control: {
      title: "Vehicle Access & ANPR Ingress (UC4)",
      description: "Automated license plate scanning, whitelist verification & dwell-time enforcement",
      color: "#0D9488",
      cameras: filteredCameras.filter((c) => c.zone_type === "access_control"),
    },
    speed_enforcement: {
      title: "Perimeter Speed Enforcement Lanes (UC4)",
      description: "Radar & optical tracking lanes with instantaneous speed violation detection (20 km/h)",
      color: "#0D9488",
      cameras: filteredCameras.filter((c) => c.zone_type === "speed_enforcement"),
    },
    occupancy_flow: {
      title: "Worker Occupancy & Ingress Flow (UC1)",
      description: "Main lobby turnstile counting and assembly floor headcount density",
      color: "#1E3A8A",
      cameras: filteredCameras.filter((c) => c.zone_type === "occupancy_flow"),
    },
    restricted_entry: {
      title: "Restricted Vaults & Intrusion Zones (UC1)",
      description: "High-security IT archives and server rooms with strict zero-occupancy mandate",
      color: "#a855f7",
      cameras: filteredCameras.filter((c) => c.zone_type === "restricted_entry"),
    },
  };

  return (
    <main className="page master-dashboard-page">
      <PageHeader
        title="Master Multi-Zone CV Dashboard"
        description="Unified live operational monitoring across safety, hazard, compliance, and traffic analytics."
        badges={
          isDemoFallback ? (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "3px 10px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 700,
                backgroundColor: "rgba(245, 158, 11, 0.18)",
                color: "#fbbf24",
                border: "1px solid rgba(245, 158, 11, 0.4)",
                letterSpacing: "0.04em",
              }}
            >
              <span>⚠️</span> DEMO DATA (OFFLINE CATALOG)
            </span>
          ) : (
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "3px 10px",
                borderRadius: "6px",
                fontSize: "11px",
                fontWeight: 700,
                backgroundColor: "rgba(34, 197, 94, 0.18)",
                color: "#4ade80",
                border: "1px solid rgba(34, 197, 94, 0.4)",
              }}
            >
              <span>●</span> LIVE REGISTRY CONNECTED
            </span>
          )
        }
      />

      {/* Prominent Demo Data Banner if in fallback mode */}
      {isDemoFallback && (
        <div
          style={{
            marginBottom: "20px",
            padding: "12px 16px",
            borderRadius: "8px",
            backgroundColor: "rgba(245, 158, 11, 0.12)",
            border: "1px solid rgba(245, 158, 11, 0.35)",
            color: "#fbbf24",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            fontSize: "13px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <span style={{ fontSize: "18px" }}>ℹ️</span>
            <span>
              <strong>Demo Data Active:</strong> Backend Camera Registry service is unreachable on port 8011. Using pre-seeded 12-camera operational topology fallback.
            </span>
          </div>
          <span style={{ fontSize: "11px", opacity: 0.8 }}>Fallback Active</span>
        </div>
      )}

      {/* Summary KPI Tiles from Alerts API & Registry */}
      <section className="stats-grid" style={{ marginBottom: "24px" }}>
        <StatCard
          title="Cameras Online"
          value={`${onlineCount} / ${cameras.length}`}
          subtitle={`${cameras.length - onlineCount} cameras currently offline`}
          icon="📹"
          color="#38bdf8"
        />

        <StatCard
          title="Pending Alerts"
          value={pendingAlertsCount}
          subtitle="Unacknowledged operational alerts"
          icon="🔔"
          color={pendingAlertsCount > 0 ? "#f59e0b" : "#4ade80"}
        />

        <StatCard
          title="Critical / High Severity"
          value={criticalCount}
          subtitle="Urgent hazard or security alerts"
          icon="⚠️"
          color={criticalCount > 0 ? "#ef4444" : "#4ade80"}
        />

        <StatCard
          title="Integrated Use Cases"
          value={allModules.length}
          subtitle={
            <span style={{ display: "flex", gap: "6px", marginTop: "4px", flexWrap: "wrap" }}>
              {allModules.map((m) => {
                const style = getUCBadgeStyle(m.id);
                return (
                  <span
                    key={m.id}
                    style={{
                      padding: "1px 5px",
                      borderRadius: "3px",
                      fontSize: "10px",
                      fontWeight: 700,
                      backgroundColor: style.backgroundColor,
                      color: style.color,
                      border: `1px solid ${style.borderColor}`,
                    }}
                  >
                    {m.id.toUpperCase()}: {alertsByUc[m.id] ?? 0}
                  </span>
                );
              })}
            </span>
          }
          icon="🧩"
          color="#A646BD"
        />
      </section>

      {/* UC4 Operations & Configurator Quick-Access Showcase */}
      <div
        style={{
          marginBottom: "24px",
          padding: "16px 20px",
          borderRadius: "10px",
          background: "linear-gradient(90deg, rgba(13, 148, 136, 0.16) 0%, rgba(21, 23, 30, 0.95) 100%)",
          border: "1px solid rgba(13, 148, 136, 0.35)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "14px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "38px",
              height: "38px",
              borderRadius: "8px",
              background: "#0D9488",
              color: "#ffffff",
              fontSize: "18px",
            }}
          >
            🚗
          </span>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <span style={{ fontSize: "14px", fontWeight: 700, color: "#ffffff" }}>
                Traffic & Vehicle Analytics (UC4 Active)
              </span>
              <span
                style={{
                  padding: "1px 6px",
                  borderRadius: "4px",
                  fontSize: "10px",
                  fontWeight: 800,
                  background: "rgba(13, 148, 136, 0.3)",
                  color: "#2dd4bf",
                  border: "1px solid rgba(13, 148, 136, 0.5)",
                }}
              >
                CONFIGURED
              </span>
            </div>
            <p style={{ fontSize: "12px", color: "var(--text-secondary, #a2a8b5)", margin: "2px 0 0" }}>
              Speed polygon calibration, license plate tracking journey, and real-time ANPR events
            </p>
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          <Link
            to="/uc4/configurator"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 14px",
              borderRadius: "6px",
              background: "#0D9488",
              color: "#ffffff",
              fontSize: "12px",
              fontWeight: 700,
              textDecoration: "none",
            }}
          >
            <span>📐 Camera Configurator</span>
          </Link>
          <Link
            to="/uc4/tracking"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 12px",
              borderRadius: "6px",
              background: "var(--surface-raised, #191c24)",
              border: "1px solid var(--border, #292d36)",
              color: "var(--text-primary, #f1f3f5)",
              fontSize: "12px",
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            <span>🔍 Plate Search</span>
          </Link>
          <Link
            to="/uc4/analytics"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 12px",
              borderRadius: "6px",
              background: "var(--surface-raised, #191c24)",
              border: "1px solid var(--border, #292d36)",
              color: "var(--text-primary, #f1f3f5)",
              fontSize: "12px",
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            <span>📊 Analytics</span>
          </Link>
          <Link
            to="/uc4"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
              padding: "7px 12px",
              borderRadius: "6px",
              background: "var(--surface-raised, #191c24)",
              border: "1px solid var(--border, #292d36)",
              color: "var(--text-primary, #f1f3f5)",
              fontSize: "12px",
              fontWeight: 600,
              textDecoration: "none",
            }}
          >
            <span>🚗 Traffic Hub →</span>
          </Link>
        </div>
      </div>

      {/* Controls & Filter Bar */}
      <div
        className="dashboard-controls"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "12px",
          flexWrap: "wrap",
          padding: "14px 18px",
          background: "var(--surface, #15171e)",
          border: "1px solid var(--border, #292d36)",
          borderRadius: "10px",
          marginBottom: "24px",
        }}
      >
        {/* Left Filter: Use Cases */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          <span style={{ fontSize: "12px", fontWeight: 600, color: "var(--text-muted, #707786)" }}>
            FILTER UC:
          </span>
          <button
            type="button"
            className={`filter-btn ${selectedUc === "all" ? "active" : ""}`}
            onClick={() => setSelectedUc("all")}
            style={{
              padding: "4px 10px",
              borderRadius: "6px",
              fontSize: "12px",
              fontWeight: 600,
              border: "1px solid var(--border, #292d36)",
              backgroundColor: selectedUc === "all" ? "var(--surface-hover, #1d2029)" : "transparent",
              color: selectedUc === "all" ? "var(--text-primary, #f1f3f5)" : "var(--text-secondary, #a2a8b5)",
            }}
          >
            All Use Cases ({cameras.length})
          </button>

          {allModules.map((m) => {
            const count = cameras.filter((c) => c.use_cases.includes(m.id)).length;
            const isSelected = selectedUc === m.id;
            return (
              <button
                key={m.id}
                type="button"
                className={`filter-btn ${isSelected ? "active" : ""}`}
                onClick={() => setSelectedUc(m.id)}
                style={{
                  padding: "4px 10px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: 600,
                  border: isSelected ? `1px solid ${m.color}` : "1px solid var(--border, #292d36)",
                  backgroundColor: isSelected ? m.colorBg : "transparent",
                  color: isSelected ? m.color : "var(--text-secondary, #a2a8b5)",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                <span>{m.icon}</span>
                <span>{m.id.toUpperCase()}</span>
                <span style={{ opacity: 0.7 }}>({count})</span>
              </button>
            );
          })}
        </div>

        {/* Right Search and View Modes */}
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <input
            type="text"
            placeholder="Search cameras, zones, policies..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              padding: "6px 12px",
              borderRadius: "6px",
              fontSize: "12px",
              border: "1px solid var(--border, #292d36)",
              backgroundColor: "var(--bg, #0f1117)",
              color: "var(--text-primary, #f1f3f5)",
              width: "220px",
            }}
          />

          <div style={{ display: "flex", border: "1px solid var(--border, #292d36)", borderRadius: "6px", overflow: "hidden" }}>
            <button
              type="button"
              onClick={() => setViewMode("by_use_case")}
              style={{
                padding: "6px 10px",
                fontSize: "12px",
                border: "none",
                backgroundColor: viewMode === "by_use_case" ? "var(--surface-raised, #191c24)" : "transparent",
                color: viewMode === "by_use_case" ? "var(--text-primary, #f1f3f5)" : "var(--text-muted, #707786)",
                cursor: "pointer",
              }}
            >
              By UC
            </button>
            <button
              type="button"
              onClick={() => setViewMode("by_zone_type")}
              style={{
                padding: "6px 10px",
                fontSize: "12px",
                border: "none",
                backgroundColor: viewMode === "by_zone_type" ? "var(--surface-raised, #191c24)" : "transparent",
                color: viewMode === "by_zone_type" ? "var(--text-primary, #f1f3f5)" : "var(--text-muted, #707786)",
                cursor: "pointer",
              }}
            >
              By Zone
            </button>
            <button
              type="button"
              onClick={() => setViewMode("all_grid")}
              style={{
                padding: "6px 10px",
                fontSize: "12px",
                border: "none",
                backgroundColor: viewMode === "all_grid" ? "var(--surface-raised, #191c24)" : "transparent",
                color: viewMode === "all_grid" ? "var(--text-primary, #f1f3f5)" : "var(--text-muted, #707786)",
                cursor: "pointer",
              }}
            >
              All Grid
            </button>
          </div>
        </div>
      </div>

      {/* Main View: Grouped by Use Case, by Zone Type, or Flat Grid */}
      {viewMode === "by_use_case" && selectedUc === "all" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "32px" }}>
          {allModules.map((module) => {
            const moduleCams = filteredCameras.filter((c) =>
              c.use_cases.includes(module.id),
            );

            if (moduleCams.length === 0) return null;

            return (
              <section key={module.id} className="uc-camera-group">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: "14px",
                    paddingBottom: "8px",
                    borderBottom: `2px solid ${module.color}44`,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span style={{ fontSize: "20px" }}>{module.icon}</span>
                    <div>
                      <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "var(--text-primary, #f1f3f5)" }}>
                        {module.name} ({module.id.toUpperCase()})
                      </h2>
                      <p style={{ fontSize: "12px", color: "var(--text-muted, #707786)", margin: 0 }}>
                        {module.description}
                      </p>
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 600,
                      color: module.color,
                      backgroundColor: module.colorBg,
                      padding: "2px 8px",
                      borderRadius: "6px",
                    }}
                  >
                    {moduleCams.length} Cameras Active
                  </span>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                    gap: "18px",
                  }}
                >
                  {moduleCams.map((camera) => (
                    <CameraTile key={camera.id} camera={camera} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : viewMode === "by_zone_type" ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "32px" }}>
          {Object.entries(zoneGroups).map(([groupKey, group]) => {
            if (group.cameras.length === 0) return null;

            return (
              <section key={groupKey} className="zone-camera-group">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: "14px",
                    paddingBottom: "8px",
                    borderBottom: `2px solid ${group.color}44`,
                  }}
                >
                  <div>
                    <h2 style={{ fontSize: "16px", fontWeight: 700, margin: 0, color: "var(--text-primary, #f1f3f5)" }}>
                      {group.title}
                    </h2>
                    <p style={{ fontSize: "12px", color: "var(--text-muted, #707786)", margin: 0 }}>
                      {group.description}
                    </p>
                  </div>
                  <span
                    style={{
                      fontSize: "12px",
                      fontWeight: 600,
                      color: group.color,
                      backgroundColor: `${group.color}18`,
                      padding: "2px 8px",
                      borderRadius: "6px",
                      border: `1px solid ${group.color}44`,
                    }}
                  >
                    {group.cameras.length} Cameras
                  </span>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                    gap: "18px",
                  }}
                >
                  {group.cameras.map((camera) => (
                    <CameraTile key={camera.id} camera={camera} />
                  ))}
                </div>
              </section>
            );
          })}
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: "18px",
          }}
        >
          {filteredCameras.map((camera) => (
            <CameraTile key={camera.id} camera={camera} />
          ))}
        </div>
      )}
    </main>
  );
}