import { useState, useEffect } from "react";
import {
  BarChart3,
  Calendar,
  CalendarDays,
  CalendarRange,
  TrendingUp,
  PieChart,
  AlertTriangle,
  Camera,
} from "lucide-react";
import { getAnalytics } from "../api";
import type { AnalyticsData } from "../types";

export function AnalyticsPage() {
  const [timeframe, setTimeframe] = useState<"day" | "week" | "month">("day");
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getAnalytics(timeframe)
      .then(setData)
      .finally(() => setLoading(false));
  }, [timeframe]);

  // Donut chart calculations
  const totalVehicles =
    data?.vehicleComposition.reduce((sum, item) => sum + item.value, 0) || 1;

  let cumulativeAngle = 0;
  const donutSlices = (data?.vehicleComposition || []).map((item) => {
    const sliceAngle = (item.value / totalVehicles) * 360;
    const startAngle = cumulativeAngle;
    cumulativeAngle += sliceAngle;

    const startRad = (startAngle - 90) * (Math.PI / 180);
    const endRad = (startAngle + sliceAngle - 90) * (Math.PI / 180);

    const x1 = 100 + 70 * Math.cos(startRad);
    const y1 = 100 + 70 * Math.sin(startRad);
    const x2 = 100 + 70 * Math.cos(endRad);
    const y2 = 100 + 70 * Math.sin(endRad);

    const largeArc = sliceAngle > 180 ? 1 : 0;
    const pathData = `M 100 100 L ${x1} ${y1} A 70 70 0 ${largeArc} 1 ${x2} ${y2} Z`;

    return {
      ...item,
      percentage: ((item.value / totalVehicles) * 100).toFixed(1),
      pathData,
    };
  });

  // Area chart calculations
  const volumePoints = data?.trafficVolume || [];
  const maxVolume = Math.max(...volumePoints.map((p) => p.count), 10);
  const chartWidth = 520;
  const chartHeight = 180;
  const paddingX = 40;
  const paddingY = 20;

  const pointsSvg = volumePoints.map((p, i) => {
    const x = paddingX + (i / Math.max(volumePoints.length - 1, 1)) * (chartWidth - paddingX * 2);
    const y = chartHeight - paddingY - (p.count / maxVolume) * (chartHeight - paddingY * 2);
    return { ...p, x, y };
  });

  const polylineCoords = pointsSvg.map((p) => `${p.x},${p.y}`).join(" ");
  const areaCoords = `${paddingX},${chartHeight - paddingY} ${polylineCoords} ${chartWidth - paddingX},${chartHeight - paddingY}`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
      {/* Header with Timeframe Toggles */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "12px",
          background: "var(--surface)",
          border: "1px solid var(--border)",
          padding: "16px 20px",
          borderRadius: "8px",
        }}
      >
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
            <BarChart3 size={20} />
          </span>
          <div>
            <h1 style={{ fontSize: "20px", fontWeight: 700, margin: 0, letterSpacing: "-0.01em" }}>
              Traffic & Vehicle Analytics
            </h1>
            <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "2px 0 0" }}>
              Aggregated historical intelligence and multi-camera traffic insights
            </p>
          </div>
        </div>

        {/* Timeframe Control */}
        <div
          style={{
            display: "flex",
            background: "var(--surface-raised)",
            border: "1px solid var(--border)",
            borderRadius: "6px",
            padding: "3px",
            gap: "4px",
          }}
        >
          <button
            type="button"
            onClick={() => setTimeframe("day")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 12px",
              borderRadius: "4px",
              border: "none",
              background: timeframe === "day" ? "#0D9488" : "transparent",
              color: timeframe === "day" ? "#ffffff" : "var(--text-secondary)",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <CalendarDays size={14} />
            <span>Last 24h</span>
          </button>
          <button
            type="button"
            onClick={() => setTimeframe("week")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 12px",
              borderRadius: "4px",
              border: "none",
              background: timeframe === "week" ? "#0D9488" : "transparent",
              color: timeframe === "week" ? "#ffffff" : "var(--text-secondary)",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <CalendarRange size={14} />
            <span>7 Days</span>
          </button>
          <button
            type="button"
            onClick={() => setTimeframe("month")}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "6px 12px",
              borderRadius: "4px",
              border: "none",
              background: timeframe === "month" ? "#0D9488" : "transparent",
              color: timeframe === "month" ? "#ffffff" : "var(--text-secondary)",
              fontSize: "12px",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <Calendar size={14} />
            <span>30 Days</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
          Loading traffic analytics...
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px" }}>
          {/* Chart 1: Total Traffic Over Time */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px" }}>
              <TrendingUp size={16} color="#0D9488" />
              <div>
                <h3 style={{ fontSize: "14px", fontWeight: 700, margin: 0 }}>Traffic Volume Over Time</h3>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Cumulative vehicle detections across active camera nodes
                </span>
              </div>
            </div>

            <div style={{ width: "100%", height: "220px", position: "relative" }}>
              <svg width="100%" height="100%" viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none">
                <defs>
                  <linearGradient id="volumeGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0D9488" stopOpacity="0.4" />
                    <stop offset="100%" stopColor="#0D9488" stopOpacity="0.0" />
                  </linearGradient>
                </defs>

                {/* Horizontal Guide Lines */}
                <line x1={paddingX} y1={paddingY} x2={chartWidth - paddingX} y2={paddingY} stroke="rgba(255,255,255,0.06)" />
                <line x1={paddingX} y1={chartHeight / 2} x2={chartWidth - paddingX} y2={chartHeight / 2} stroke="rgba(255,255,255,0.06)" />
                <line x1={paddingX} y1={chartHeight - paddingY} x2={chartWidth - paddingX} y2={chartHeight - paddingY} stroke="rgba(255,255,255,0.12)" />

                {/* Shaded Area */}
                <polygon points={areaCoords} fill="url(#volumeGrad)" />

                {/* Stroke line */}
                <polyline points={polylineCoords} fill="none" stroke="#0D9488" strokeWidth="2.5" />

                {/* Data point dots */}
                {pointsSvg.map((p) => (
                  <circle key={p.name} cx={p.x} cy={p.y} r="4" fill="#0D9488" stroke="#ffffff" strokeWidth="1.5" />
                ))}

                {/* X-axis labels */}
                {pointsSvg.map((p) => (
                  <text key={p.name} x={p.x} y={chartHeight - 4} fill="var(--text-muted)" fontSize="9" textAnchor="middle" fontFamily="var(--mono)">
                    {p.name}
                  </text>
                ))}
              </svg>
            </div>
          </div>

          {/* Chart 2: Vehicle Composition Donut */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px" }}>
              <PieChart size={16} color="#3B82F6" />
              <div>
                <h3 style={{ fontSize: "14px", fontWeight: 700, margin: 0 }}>Vehicle Classification</h3>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Distribution of detected vehicle classes and body types
                </span>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "24px" }}>
              {/* SVG Donut */}
              <div style={{ width: "160px", height: "160px", position: "relative", flexShrink: 0 }}>
                <svg width="160" height="160" viewBox="0 0 200 200">
                  {donutSlices.map((slice) => (
                    <path key={slice.name} d={slice.pathData} fill={slice.color} />
                  ))}
                  {/* Donut Hole */}
                  <circle cx="100" cy="100" r="46" fill="var(--surface)" />
                </svg>
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    textAlign: "center",
                  }}
                >
                  <span style={{ fontSize: "18px", fontWeight: 750, color: "var(--text-primary)" }}>
                    {totalVehicles.toLocaleString()}
                  </span>
                  <span style={{ fontSize: "9px", color: "var(--text-muted)", letterSpacing: "0.05em" }}>
                    TOTAL
                  </span>
                </div>
              </div>

              {/* Legend List */}
              <div style={{ display: "flex", flexDirection: "column", gap: "8px", flex: 1 }}>
                {donutSlices.map((slice) => (
                  <div key={slice.name} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "11px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                      <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: slice.color }} />
                      <span style={{ color: "var(--text-secondary)" }}>{slice.name}</span>
                    </div>
                    <div style={{ display: "flex", gap: "8px" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{slice.value}</span>
                      <span style={{ color: "var(--text-muted)", fontFamily: "var(--mono)" }}>({slice.percentage}%)</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Chart 3: Violation Density Stacked Bars */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px" }}>
              <AlertTriangle size={16} color="#F59E0B" />
              <div>
                <h3 style={{ fontSize: "14px", fontWeight: 700, margin: 0 }}>Violation Density by Zone</h3>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Breakdown of speeding, unauthorized access, and traffic infractions
                </span>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
              {(data?.violationDensity || []).map((zone) => {
                const total = zone.speeding + zone.unauthorized + zone.redLight || 1;
                const pSpeeding = (zone.speeding / total) * 100;
                const pUnauth = (zone.unauthorized / total) * 100;
                const pRedLight = (zone.redLight / total) * 100;

                return (
                  <div key={zone.name}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "4px" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{zone.name}</span>
                      <span style={{ color: "var(--text-muted)" }}>{total} violations</span>
                    </div>
                    <div style={{ display: "flex", height: "10px", borderRadius: "5px", overflow: "hidden", background: "rgba(255,255,255,0.05)" }}>
                      <div style={{ width: `${pSpeeding}%`, background: "#EF4444" }} title={`Speeding: ${zone.speeding}`} />
                      <div style={{ width: `${pUnauth}%`, background: "#F59E0B" }} title={`Unauthorized: ${zone.unauthorized}`} />
                      <div style={{ width: `${pRedLight}%`, background: "#8B5CF6" }} title={`Red Light: ${zone.redLight}`} />
                    </div>
                  </div>
                );
              })}

              <div style={{ display: "flex", gap: "16px", marginTop: "8px", fontSize: "10px", color: "var(--text-muted)" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: "#EF4444" }} /> Speeding
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: "#F59E0B" }} /> Unauthorized
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  <span style={{ width: "8px", height: "8px", borderRadius: "2px", background: "#8B5CF6" }} /> Red Light
                </span>
              </div>
            </div>
          </div>

          {/* Chart 4: Camera-Wise Alert Ranking */}
          <div
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              padding: "20px",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "16px" }}>
              <Camera size={16} color="#10B981" />
              <div>
                <h3 style={{ fontSize: "14px", fontWeight: 700, margin: 0 }}>Camera Node Activity</h3>
                <span style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                  Cameras ranked by detection alerts and incident frequency
                </span>
              </div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {(data?.cameraAlerts || []).map((cam) => {
                const maxAlerts = Math.max(...(data?.cameraAlerts || []).map((c) => c.count), 50);
                const pct = (cam.count / maxAlerts) * 100;

                return (
                  <div key={cam.name}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "11px", marginBottom: "4px" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{cam.name}</span>
                      <span style={{ fontFamily: "var(--mono)", color: "#10B981", fontWeight: 600 }}>{cam.count} alerts</span>
                    </div>
                    <div style={{ height: "6px", borderRadius: "3px", background: "rgba(255,255,255,0.05)", overflow: "hidden" }}>
                      <div style={{ width: `${pct}%`, height: "100%", background: "#10B981", borderRadius: "3px" }} />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AnalyticsPage;
