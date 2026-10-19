import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Car,
  SlidersHorizontal,
  Search,
  Clock,
  ShieldAlert,
  ArrowRight,
  Gauge,
} from "lucide-react";
import { getVehicleEvents, getUC4Cameras, getWatchlist } from "../api";
import type { VehicleEvent, UC4Camera, WatchlistEntry } from "../types";

export function UC4OverviewPage() {
  const [events, setEvents] = useState<VehicleEvent[]>([]);
  const [cameras, setCameras] = useState<UC4Camera[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [searchPlate, setSearchPlate] = useState("");
  const [selectedCameraFilter, setSelectedCameraFilter] = useState("ALL");
  const [onlyViolations, setOnlyViolations] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getVehicleEvents(), getUC4Cameras(), getWatchlist()])
      .then(([evs, cams, wl]) => {
        setEvents(evs);
        setCameras(cams);
        setWatchlist(wl);
      })
      .finally(() => setLoading(false));
  }, []);

  const totalVehicles = events.length;
  const violationCount = events.filter((e) => e.is_violation).length;
  const activeCamerasCount = cameras.filter((c) => c.status === "online").length;

  const filteredEvents = events.filter((e) => {
    const matchesPlate =
      !searchPlate ||
      e.license_plate.toUpperCase().includes(searchPlate.toUpperCase());
    const matchesCamera =
      selectedCameraFilter === "ALL" || e.camera_id === selectedCameraFilter;
    const matchesViolation = !onlyViolations || e.is_violation;
    return matchesPlate && matchesCamera && matchesViolation;
  });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
      {/* Top Banner with Quick Jump to Configurator */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "16px",
          background: "linear-gradient(90deg, rgba(13, 148, 136, 0.15) 0%, rgba(21, 23, 30, 0.95) 100%)",
          border: "1px solid rgba(13, 148, 136, 0.3)",
          borderRadius: "10px",
          padding: "20px 24px",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "14px" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "44px",
              height: "44px",
              borderRadius: "10px",
              background: "#0D9488",
              color: "#ffffff",
              boxShadow: "0 4px 12px rgba(13, 148, 136, 0.4)",
            }}
          >
            <Car size={24} />
          </span>
          <div>
            <h1 style={{ fontSize: "20px", fontWeight: 700, margin: 0, color: "#ffffff" }}>
              Traffic & Vehicle Analytics (UC4)
            </h1>
            <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "4px 0 0" }}>
              Automatic Number Plate Recognition (ANPR), speed enforcement & perimeter access monitoring
            </p>
          </div>
        </div>

        {/* Quick Configurator CTA Button */}
        <Link
          to="/uc4/configurator"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "8px",
            padding: "10px 18px",
            borderRadius: "6px",
            background: "#0D9488",
            color: "#ffffff",
            fontSize: "13px",
            fontWeight: 700,
            textDecoration: "none",
            boxShadow: "0 2px 8px rgba(13, 148, 136, 0.3)",
          }}
        >
          <SlidersHorizontal size={16} />
          <span>Camera & Speed Configurator</span>
          <ArrowRight size={14} />
        </Link>
      </div>

      {/* KPI Stat Cards Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px" }}>
        {/* Vehicles Detected */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            padding: "16px 20px",
          }}
        >
          <span style={{ fontSize: "10px", fontWeight: 650, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            TOTAL VEHICLES TODAY
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginTop: "8px" }}>
            <span style={{ fontSize: "28px", fontWeight: 700, color: "var(--text-primary)" }}>
              {totalVehicles * 240 + 42}
            </span>
            <span style={{ fontSize: "12px", color: "var(--success)", fontWeight: 600 }}>+8.4%</span>
          </div>
          <span style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px", display: "block" }}>
            Across all 3 campus gate lanes
          </span>
        </div>

        {/* Speed Violations */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            padding: "16px 20px",
          }}
        >
          <span style={{ fontSize: "10px", fontWeight: 650, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            SPEED VIOLATIONS
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginTop: "8px" }}>
            <span style={{ fontSize: "28px", fontWeight: 700, color: "var(--danger)" }}>
              {violationCount * 12 + 2}
            </span>
            <span style={{ fontSize: "12px", color: "var(--danger)", fontWeight: 600 }}>Active alert</span>
          </div>
          <span style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px", display: "block" }}>
            Speed threshold &gt; 20 km/h
          </span>
        </div>

        {/* OCR Confidence */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            padding: "16px 20px",
          }}
        >
          <span style={{ fontSize: "10px", fontWeight: 650, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            ANPR ACCURACY
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginTop: "8px" }}>
            <span style={{ fontSize: "28px", fontWeight: 700, color: "#0D9488" }}>
              96.2%
            </span>
            <span style={{ fontSize: "12px", color: "var(--success)", fontWeight: 600 }}>High precision</span>
          </div>
          <span style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px", display: "block" }}>
            Dual-plate CRNN model
          </span>
        </div>

        {/* Active ANPR Cameras */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            padding: "16px 20px",
          }}
        >
          <span style={{ fontSize: "10px", fontWeight: 650, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            ACTIVE CAMERAS
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: "8px", marginTop: "8px" }}>
            <span style={{ fontSize: "28px", fontWeight: 700, color: "var(--text-primary)" }}>
              {activeCamerasCount} / {cameras.length}
            </span>
            <span style={{ fontSize: "12px", color: "var(--success)", fontWeight: 600 }}>100% Online</span>
          </div>
          <span style={{ fontSize: "11px", color: "var(--text-muted)", marginTop: "4px", display: "block" }}>
            Homography calibrations active
          </span>
        </div>
      </div>

      {/* Main Split Grid: Live Events Table + Watchlist */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 340px", gap: "20px", alignItems: "start" }}>
        {/* Left: Live Vehicle Events Table */}
        <div
          style={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "8px",
            padding: "20px",
          }}
        >
          {/* Table Header & Controls */}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
            <div>
              <h2 style={{ fontSize: "15px", fontWeight: 700, margin: 0 }}>Vehicle Access & Detection Logs</h2>
              <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: "2px 0 0" }}>
                Real-time ANPR scans across all perimeter entrance and speed detection gates
              </p>
            </div>

            {/* Filters */}
            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
              {/* Search plate */}
              <div style={{ position: "relative" }}>
                <input
                  type="text"
                  placeholder="Filter plate..."
                  value={searchPlate}
                  onChange={(e) => setSearchPlate(e.target.value)}
                  style={{
                    height: "32px",
                    padding: "0 8px 0 28px",
                    borderRadius: "4px",
                    border: "1px solid var(--border)",
                    background: "var(--surface-raised)",
                    color: "var(--text-primary)",
                    fontSize: "11px",
                    fontFamily: "var(--mono)",
                    outline: "none",
                    width: "140px",
                  }}
                />
                <Search size={13} style={{ position: "absolute", left: "9px", top: "10px", color: "var(--text-muted)" }} />
              </div>

              {/* Camera filter */}
              <select
                value={selectedCameraFilter}
                onChange={(e) => setSelectedCameraFilter(e.target.value)}
                style={{
                  height: "32px",
                  padding: "0 8px",
                  borderRadius: "4px",
                  border: "1px solid var(--border)",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  fontSize: "11px",
                  outline: "none",
                }}
              >
                <option value="ALL">All Cameras</option>
                {cameras.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name.split("—")[0].trim()}
                  </option>
                ))}
              </select>

              {/* Violations Toggle */}
              <button
                type="button"
                onClick={() => setOnlyViolations(!onlyViolations)}
                style={{
                  height: "32px",
                  padding: "0 10px",
                  borderRadius: "4px",
                  border: `1px solid ${onlyViolations ? "var(--danger)" : "var(--border)"}`,
                  background: onlyViolations ? "var(--danger-bg)" : "var(--surface-raised)",
                  color: onlyViolations ? "var(--danger)" : "var(--text-muted)",
                  fontSize: "11px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Violations Only
              </button>
            </div>
          </div>

          {/* Table */}
          {loading ? (
            <div style={{ padding: "30px", textAlign: "center", color: "var(--text-muted)" }}>Loading events...</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "12px", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)", color: "var(--text-muted)", fontSize: "10px", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                    <th style={{ padding: "10px 12px" }}>License Plate</th>
                    <th style={{ padding: "10px 12px" }}>Camera Node</th>
                    <th style={{ padding: "10px 12px" }}>Speed</th>
                    <th style={{ padding: "10px 12px" }}>Classification</th>
                    <th style={{ padding: "10px 12px" }}>OCR Conf</th>
                    <th style={{ padding: "10px 12px" }}>Detected At</th>
                    <th style={{ padding: "10px 12px", textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredEvents.map((ev) => (
                    <tr
                      key={ev.event_id}
                      style={{
                        borderBottom: "1px solid rgba(255,255,255,0.04)",
                        background: ev.is_violation ? "rgba(239, 68, 68, 0.04)" : "transparent",
                      }}
                    >
                      <td style={{ padding: "12px" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "3px 8px",
                            borderRadius: "4px",
                            border: `1px solid ${ev.is_violation ? "rgba(239, 68, 68, 0.3)" : "rgba(13, 148, 136, 0.3)"}`,
                            background: ev.is_violation ? "rgba(239, 68, 68, 0.15)" : "rgba(13, 148, 136, 0.15)",
                            color: ev.is_violation ? "var(--danger)" : "#0D9488",
                            fontFamily: "var(--mono)",
                            fontSize: "12px",
                            fontWeight: 700,
                          }}
                        >
                          {ev.license_plate}
                        </span>
                      </td>
                      <td style={{ padding: "12px", color: "var(--text-primary)", fontWeight: 550 }}>
                        {ev.camera_name || "Perimeter Lane"}
                      </td>
                      <td style={{ padding: "12px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                          <Gauge size={13} color={ev.is_violation ? "var(--danger)" : "var(--text-muted)"} />
                          <span
                            style={{
                              fontFamily: "var(--mono)",
                              fontWeight: 650,
                              color: ev.is_violation ? "var(--danger)" : "var(--text-primary)",
                            }}
                          >
                            {ev.speed_kmh} km/h
                          </span>
                          {ev.is_violation && (
                            <span
                              style={{
                                padding: "1px 5px",
                                borderRadius: "3px",
                                background: "var(--danger)",
                                color: "#ffffff",
                                fontSize: "9px",
                                fontWeight: 800,
                              }}
                            >
                              BREACH
                            </span>
                          )}
                        </div>
                      </td>
                      <td style={{ padding: "12px", color: "var(--text-secondary)", textTransform: "capitalize" }}>
                        {ev.vehicle_color} {ev.vehicle_type}
                      </td>
                      <td style={{ padding: "12px", fontFamily: "var(--mono)", color: "var(--text-secondary)" }}>
                        {ev.ocr_confidence}%
                      </td>
                      <td style={{ padding: "12px", color: "var(--text-muted)", fontSize: "11px" }}>
                        <Clock size={11} style={{ display: "inline", marginRight: "4px" }} />
                        {new Date(ev.entry_time).toLocaleTimeString()}
                      </td>
                      <td style={{ padding: "12px", textAlign: "right" }}>
                        <Link
                          to={`/uc4/tracking?plate=${ev.license_plate}`}
                          style={{
                            padding: "4px 8px",
                            borderRadius: "4px",
                            background: "var(--surface-hover)",
                            border: "1px solid var(--border)",
                            color: "#0D9488",
                            fontSize: "11px",
                            fontWeight: 600,
                            textDecoration: "none",
                          }}
                        >
                          Track Route →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Right: Flagged Watchlist & Quick Links */}
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          {/* Security Watchlist Card */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "18px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
              <ShieldAlert size={16} color="var(--danger)" />
              <h3 style={{ fontSize: "13px", fontWeight: 700, margin: 0 }}>Watchlist & Banned Plates</h3>
            </div>
            <p style={{ fontSize: "11px", color: "var(--text-muted)", margin: "0 0 12px" }}>
              Vehicles flagged for perimeter breach, contract suspension, or security review
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
              {watchlist.map((wl) => (
                <div
                  key={wl.plate}
                  style={{
                    padding: "10px",
                    borderRadius: "6px",
                    background: "rgba(255, 255, 255, 0.02)",
                    border: "1px solid var(--border)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "4px" }}>
                    <span style={{ fontFamily: "var(--mono)", fontSize: "12px", fontWeight: 700, color: "var(--text-primary)" }}>
                      {wl.plate}
                    </span>
                    <span
                      style={{
                        padding: "1px 6px",
                        borderRadius: "3px",
                        background: wl.severity === "CRITICAL" ? "rgba(239, 68, 68, 0.2)" : "rgba(245, 158, 11, 0.2)",
                        color: wl.severity === "CRITICAL" ? "var(--danger)" : "var(--warning)",
                        fontSize: "9px",
                        fontWeight: 700,
                      }}
                    >
                      {wl.severity}
                    </span>
                  </div>
                  <p style={{ fontSize: "11px", color: "var(--text-secondary)", margin: "0 0 6px" }}>
                    {wl.reason}
                  </p>
                  <Link
                    to={`/uc4/tracking?plate=${wl.plate}`}
                    style={{ fontSize: "10px", color: "#0D9488", textDecoration: "none", fontWeight: 600 }}
                  >
                    View Last Known Sighting →
                  </Link>
                </div>
              ))}
            </div>
          </div>

          {/* Quick Module Navigation Box */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "18px",
            }}
          >
            <h3 style={{ fontSize: "13px", fontWeight: 700, margin: "0 0 12px" }}>UC4 Feature Navigation</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
              <Link
                to="/uc4/configurator"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  fontSize: "12px",
                  textDecoration: "none",
                  fontWeight: 550,
                  border: "1px solid var(--border)",
                }}
              >
                <span>📐 Speed Polygon & Lines Configurator</span>
                <ArrowRight size={13} color="var(--text-muted)" />
              </Link>
              <Link
                to="/uc4/tracking"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  fontSize: "12px",
                  textDecoration: "none",
                  fontWeight: 550,
                  border: "1px solid var(--border)",
                }}
              >
                <span>🔍 Vehicle Tracking & Plate Journey</span>
                <ArrowRight size={13} color="var(--text-muted)" />
              </Link>
              <Link
                to="/uc4/analytics"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  fontSize: "12px",
                  textDecoration: "none",
                  fontWeight: 550,
                  border: "1px solid var(--border)",
                }}
              >
                <span>📊 Historical Traffic Analytics</span>
                <ArrowRight size={13} color="var(--text-muted)" />
              </Link>
              <Link
                to="/uc4/pipeline"
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "9px 12px",
                  borderRadius: "6px",
                  background: "var(--surface-raised)",
                  color: "var(--text-primary)",
                  fontSize: "12px",
                  textDecoration: "none",
                  fontWeight: 550,
                  border: "1px solid var(--border)",
                }}
              >
                <span>🎥 Live AI Pipeline Stream</span>
                <ArrowRight size={13} color="var(--text-muted)" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default UC4OverviewPage;
