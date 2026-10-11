import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getCameras } from "@/api/cameras";
import { getZones } from "@/api/platform";

import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import CameraTile from "@/components/cameras/CameraTile";

export function LiveMonitoring() {
  const [search, setSearch] = useState("");
  const [selectedZone, setSelectedZone] = useState("");
  const [layoutColumns, setLayoutColumns] = useState<number>(3); // 2, 3, or 4 columns

  const { data: zones } = useQuery({
    queryKey: ["zones"],
    queryFn: () => getZones(),
  });

  const {

    data: cameras,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
    refetchInterval: 5000,
  });

  if (isLoading) {
    return <LoadingState message="Connecting to Live RTSP Video Feeds..." />;
  }

  if (isError) {
    return <ErrorState message="Failed to connect to video stream pipeline." />;
  }

  const cameraList = cameras || [];
  const onlineCount = cameraList.filter((c) => c.status === "online").length;

  const filtered = cameraList.filter((c) => {
    const matchesSearch =
      c.name.toLowerCase().includes(search.toLowerCase()) ||
      (c.location && c.location.toLowerCase().includes(search.toLowerCase())) ||
      c.id.toLowerCase().includes(search.toLowerCase());

    const matchesZone = selectedZone ? (c.location && c.location.includes(selectedZone)) : true;

    return matchesSearch && matchesZone;
  });

  return (
    <main className="page" style={{ padding: "24px 32px" }}>
      {/* Video Wall Header */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
          marginBottom: "24px",
          paddingBottom: "18px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1 style={{ fontSize: "22px", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
              Live CCTV Video Wall
            </h1>
            <span
              style={{
                fontSize: "11px",
                fontWeight: 700,
                color: "var(--success)",
                background: "var(--success-bg)",
                padding: "2px 8px",
                borderRadius: "9999px",
                border: "1px solid rgba(16, 185, 129, 0.25)",
              }}
            >
              ● {onlineCount} Active Feeds
            </span>
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "13px", marginTop: "4px", margin: "4px 0 0 0" }}>
            Continuous multi-camera surveillance grid with edge AI bounding box telemetry.
          </p>
        </div>

        {/* Video Wall Toolbar: Grid Layout + Filters */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px", flexWrap: "wrap" }}>
          {/* Search */}
          <input
            type="text"
            placeholder="Search streams..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              background: "var(--input-bg)",
              border: "1px solid var(--input-border)",
              borderRadius: "6px",
              padding: "6px 12px",
              color: "var(--input-color)",
              fontSize: "12.5px",
              width: "200px",
              outline: "none",
            }}
          />

          {/* Zone Selector */}
          {zones && zones.length > 0 && (
            <select
              value={selectedZone}
              onChange={(e) => setSelectedZone(e.target.value)}
              style={{
                background: "var(--input-bg)",
                border: "1px solid var(--input-border)",
                borderRadius: "6px",
                padding: "6px 10px",
                color: "var(--input-color)",
                fontSize: "12.5px",
                outline: "none",
              }}
            >
              <option value="">All Production Zones</option>
              {zones.map((z) => (
                <option key={z.id} value={z.name}>
                  {z.name}
                </option>
              ))}
            </select>
          )}

          {/* Grid Layout Switcher */}
          <div
            style={{
              display: "flex",
              background: "var(--surface-raised)",
              border: "1px solid var(--border)",
              borderRadius: "6px",
              padding: "2px",
            }}
          >
            <button
              type="button"
              onClick={() => setLayoutColumns(2)}
              title="2 Columns (Large View)"
              style={{
                background: layoutColumns === 2 ? "var(--surface-hover)" : "transparent",
                border: "none",
                color: layoutColumns === 2 ? "var(--text-primary)" : "var(--text-muted)",
                padding: "4px 8px",
                borderRadius: "4px",
                fontSize: "12px",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              2x2
            </button>
            <button
              type="button"
              onClick={() => setLayoutColumns(3)}
              title="3 Columns (Standard View)"
              style={{
                background: layoutColumns === 3 ? "var(--surface-hover)" : "transparent",
                border: "none",
                color: layoutColumns === 3 ? "var(--text-primary)" : "var(--text-muted)",
                padding: "4px 8px",
                borderRadius: "4px",
                fontSize: "12px",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              3x3
            </button>
            <button
              type="button"
              onClick={() => setLayoutColumns(4)}
              title="4 Columns (Dense View)"
              style={{
                background: layoutColumns === 4 ? "var(--surface-hover)" : "transparent",
                border: "none",
                color: layoutColumns === 4 ? "var(--text-primary)" : "var(--text-muted)",
                padding: "4px 8px",
                borderRadius: "4px",
                fontSize: "12px",
                fontWeight: 700,
                cursor: "pointer",
              }}
            >
              4x4
            </button>
          </div>
        </div>
      </header>

      {/* Video Wall Grid */}
      {filtered.length === 0 ? (
        <EmptyState message="No live camera feeds match the selected filters." />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${layoutColumns}, minmax(0, 1fr))`,
            gap: "16px",
          }}
        >
          {filtered.map((camera) => (
            <CameraTile key={camera.id} camera={camera} />
          ))}
        </div>
      )}
    </main>
  );
}
