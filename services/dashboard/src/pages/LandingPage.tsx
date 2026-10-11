import { useState, useEffect } from "react";

import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/store/useAuth";
import "../landing.css";

interface ChannelData {
  id: string;
  code: string;
  name: string;
  badge: string;
  badgeColor: string;
  desc: string;
  latency: string;
  accuracy: string;
  activeCams: number;
  tags: string[];
}

const AI_CHANNELS: ChannelData[] = [
  {
    id: "uc1",
    code: "UC-01",
    name: "Perimeter & Intrusion Shield",
    badge: "Active Defense",
    badgeColor: "#3b82f6",
    desc: "Autonomous boundary tripwire & geo-fence breach detection. Distinguishes personnel from wildlife with temporal tracking.",
    latency: "38 ms",
    accuracy: "99.2%",
    activeCams: 18,
    tags: ["YOLOv11", "DeepSORT", "Geo-Fence"],
  },
  {
    id: "uc2",
    code: "UC-02",
    name: "Thermographic Flame & Smoke",
    badge: "Hazard Sentry",
    badgeColor: "#ef4444",
    desc: "Early ignition & smoke spectral signature recognition in kiln heads, raw mills, and high-heat processing silos.",
    latency: "45 ms",
    accuracy: "98.9%",
    activeCams: 12,
    tags: ["Thermal IR", "Spectral Fusion", "SLA < 3s"],
  },
  {
    id: "uc3",
    code: "UC-03",
    name: "PPE & Safety Enforcement",
    badge: "OSHA Compliant",
    badgeColor: "#10b981",
    desc: "Full-body safety compliance tracking. Real-time verification for hard hats, high-vis vests, protective eyewear, and safety boots.",
    latency: "42 ms",
    accuracy: "98.4%",
    activeCams: 26,
    tags: ["Keypoint Pose", "Multi-Label", "Zero-False"],
  },
  {
    id: "uc4",
    code: "UC-04",
    name: "ANPR & Vehicle Speed Radar",
    badge: "Logistics",
    badgeColor: "#f59e0b",
    desc: "Automated license plate recognition with consensus scoring, radar speed limit enforcement, and unauthorized truck dispatch.",
    latency: "60 ms",
    accuracy: "99.5%",
    activeCams: 8,
    tags: ["PaddleOCR", "Consensus Gate", "Speed Limit"],
  },
];

const PLATFORM_PILLARS = [
  {
    icon: "⚡",
    title: "Sub-Second Ingestion Core",
    desc: "FFmpeg accelerated decode pipeline with dynamic FPS decimation, Redis 2GB LRU hot-caching, and zero-loss stream fan-out.",
    tag: "High Throughput",
  },
  {
    icon: "🚨",
    title: "Multi-Tier Escalation Engine",
    desc: "Automated Celery distributed workers with 3-tier L1/L2/L3 protocol dispatching via WebSockets, SMS, and SMTP alerts.",
    tag: "Autonomous Dispatch",
  },
  {
    icon: "🔒",
    title: "Forensic Cryptographic Audit",
    desc: "Append-only tamper-evident audit ledger preserving incident chains-of-custody for industrial regulatory compliance.",
    tag: "Forensic Integrity",
  },
  {
    icon: "📊",
    title: "Automated Executive Reports",
    desc: "Scheduled and on-demand PDF audit generation with visual incident crops and compliance readiness heatmaps.",
    tag: "ISO / OSHA Ready",
  },
];

export function LandingPage() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [selectedChannel, setSelectedChannel] = useState<string>("uc3");
  const [timeStr, setTimeStr] = useState<string>("");

  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setTimeStr(
        now.toISOString().replace("T", " ").substring(0, 19) + " UTC"
      );
    };
    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, []);

  const currentChannel =
    AI_CHANNELS.find((c) => c.id === selectedChannel) || AI_CHANNELS[2];

  const handleLaunchConsole = () => {
    if (isAuthenticated) {
      if (user?.role === "operator") {
        navigate("/alerts");
      } else if (user?.role === "viewer") {
        navigate("/live-monitoring");
      } else {
        navigate("/");
      }
    } else {
      navigate("/login");
    }
  };

  return (
    <div className="netflix-root">
      {/* Ambient background glows */}
      <div className="netflix-ambient-glow" />
      <div className="netflix-cyber-grid" />

      {/* Navigation Bar */}
      <header className="netflix-header">
        <div className="netflix-nav-container">
          <Link to="/" className="netflix-logo-group">
            <div className="netflix-logo-badge">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M3 12h2m14 0h2M12 3v2m0 14v2" />
                <path d="M5.6 5.6l1.4 1.4m10 10l1.4 1.4M5.6 18.4l1.4-1.4m10-10l1.4-1.4" />
              </svg>
            </div>
            <div className="netflix-logo-text">
              INNOVISION
              <span className="netflix-logo-tag">AI OPS</span>
            </div>
          </Link>

          <nav className="netflix-nav-links">
            <a href="#channels" className="netflix-nav-link">
              AI Engines
            </a>
            <a href="#architecture" className="netflix-nav-link">
              Architecture
            </a>
            <a href="#fleet" className="netflix-nav-link">
              Plant Fleet
            </a>
            <div className="netflix-pulse-status">
              <span className="netflix-pulse-dot" />
              <span>CLUSTER OPERATIONAL</span>
            </div>
          </nav>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            {isAuthenticated ? (
              <button
                onClick={handleLaunchConsole}
                className="netflix-btn-signin"
                style={{ background: "#2563eb" }}
              >
                Command Center &rarr;
              </button>
            ) : (
              <Link to="/login" className="netflix-btn-signin">
                Sign In
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Hero Billboard */}
      <section className="netflix-hero-wrapper">
        <div className="netflix-hero-grid">
          <div>
            <div className="netflix-hero-badge">
              <span>●</span> Industrial Video Intelligence Platform
            </div>

            <h1 className="netflix-hero-title">
              Autonomous Video AI &amp; <span>Safety Command</span>
            </h1>

            <p className="netflix-hero-sub">
              Stream live RTSP feeds across distributed plants. Detect PPE
              violations, perimeter intrusions, smoke/flame, and vehicle hazards
              with sub-second inference and automated incident escalation.
            </p>

            <div className="netflix-hero-actions">
              <button
                onClick={handleLaunchConsole}
                className="netflix-btn-primary"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                {isAuthenticated ? "Enter Command Center" : "Launch Command Center"}
              </button>

              <a href="#channels" className="netflix-btn-secondary">
                <svg
                  width="18"
                  height="18"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
                  <line x1="7" y1="2" x2="7" y2="22" />
                  <line x1="17" y1="2" x2="17" y2="22" />
                  <line x1="2" y1="12" x2="22" y2="12" />
                  <line x1="2" y1="7" x2="7" y2="7" />
                  <line x1="2" y1="17" x2="7" y2="17" />
                  <line x1="17" y1="17" x2="22" y2="17" />
                  <line x1="17" y1="7" x2="22" y2="7" />
                </svg>
                Explore Live AI Feeds
              </a>
            </div>

            <div className="netflix-metrics-grid">
              <div className="netflix-metric-item">
                <span className="netflix-metric-val">&lt; 45ms</span>
                <span className="netflix-metric-lbl">Inference Latency</span>
              </div>
              <div className="netflix-metric-item">
                <span className="netflix-metric-val">64+</span>
                <span className="netflix-metric-lbl">Live RTSP Streams</span>
              </div>
              <div className="netflix-metric-item">
                <span className="netflix-metric-val">99.98%</span>
                <span className="netflix-metric-lbl">Platform SLA</span>
              </div>
            </div>
          </div>

          {/* CCTV Viewfinder Card */}
          <div>
            <div className="netflix-viewfinder-card">
              <div className="netflix-viewfinder-header">
                <div className="netflix-viewfinder-meta">
                  <span
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      backgroundColor: "#ef4444",
                      boxShadow: "0 0 6px #ef4444",
                    }}
                  />
                  <span
                    style={{
                      fontSize: "0.8rem",
                      fontWeight: 700,
                      color: "#ffffff",
                      fontFamily: "monospace",
                    }}
                  >
                    FEED: CAM-0001 // JK-PLANT-01
                  </span>
                </div>
                <span
                  style={{
                    fontSize: "0.72rem",
                    color: "#94a3b8",
                    fontFamily: "monospace",
                  }}
                >
                  30.0 FPS // 1080P
                </span>
              </div>

              <div className="netflix-viewfinder-screen">
                {/* Background Grid Pattern */}
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background:
                      "radial-gradient(circle at 60% 40%, rgba(30, 41, 59, 0.7) 0%, rgba(10, 13, 20, 0.95) 100%)",
                  }}
                />
                <div className="netflix-scanline" />
                <div className="netflix-radar-sweep" />

                {/* Simulated Bounding Boxes based on selected channel */}
                {selectedChannel === "uc3" && (
                  <>
                    <div
                      className="netflix-bbox bbox-success"
                      style={{ top: "22%", left: "32%", width: "22%", height: "55%" }}
                    >
                      <span className="netflix-bbox-label">PERSON: 99.4%</span>
                    </div>
                    <div
                      className="netflix-bbox bbox-cyan"
                      style={{ top: "23%", left: "38%", width: "10%", height: "14%" }}
                    >
                      <span className="netflix-bbox-label">HARDHAT: YES</span>
                    </div>
                    <div
                      className="netflix-bbox bbox-success"
                      style={{ top: "37%", left: "35%", width: "16%", height: "24%" }}
                    >
                      <span className="netflix-bbox-label">SAFETY_VEST: OK</span>
                    </div>
                  </>
                )}

                {selectedChannel === "uc1" && (
                  <>
                    <div
                      className="netflix-bbox bbox-danger"
                      style={{ top: "30%", left: "45%", width: "20%", height: "48%" }}
                    >
                      <span className="netflix-bbox-label">BREACH ALERT [ZONE-A]</span>
                    </div>
                  </>
                )}

                {selectedChannel === "uc2" && (
                  <>
                    <div
                      className="netflix-bbox bbox-danger"
                      style={{ top: "40%", left: "28%", width: "30%", height: "35%" }}
                    >
                      <span className="netflix-bbox-label">HEAT_TEMP: 480°C [KILN]</span>
                    </div>
                  </>
                )}

                {selectedChannel === "uc4" && (
                  <>
                    <div
                      className="netflix-bbox bbox-cyan"
                      style={{ top: "35%", left: "25%", width: "45%", height: "42%" }}
                    >
                      <span className="netflix-bbox-label">PLATE: RJ-14-GA-8921</span>
                    </div>
                  </>
                )}

                {/* HUD Overlay Info */}
                <div className="netflix-hud-overlay">
                  <div className="netflix-hud-top">
                    <span className="netflix-hud-tag">
                      {currentChannel.code} :: {currentChannel.name}
                    </span>
                    <span className="netflix-hud-tag" style={{ color: "#ef4444" }}>
                      ● REC
                    </span>
                  </div>

                  <div className="netflix-hud-bottom">
                    <span className="netflix-hud-tag">
                      ZONE: KILN &amp; PREHEATER 4A
                    </span>
                    <span className="netflix-hud-tag">{timeStr}</span>
                  </div>
                </div>
              </div>

              {/* Interactive Channel Selector Bar */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(4, 1fr)",
                  background: "#080b12",
                  borderTop: "1px solid rgba(255, 255, 255, 0.08)",
                }}
              >
                {AI_CHANNELS.map((ch) => (
                  <button
                    key={ch.id}
                    onClick={() => setSelectedChannel(ch.id)}
                    style={{
                      background:
                        selectedChannel === ch.id
                          ? "rgba(229, 9, 20, 0.15)"
                          : "transparent",
                      border: "none",
                      borderBottom:
                        selectedChannel === ch.id
                          ? "2px solid #e50914"
                          : "2px solid transparent",
                      color: selectedChannel === ch.id ? "#ffffff" : "#64748b",
                      padding: "0.65rem 0.5rem",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      cursor: "pointer",
                      transition: "all 0.2s ease",
                    }}
                  >
                    {ch.code}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Row 1: Featured AI Detection Engines (Netflix Channel Cards) */}
      <section id="channels" className="netflix-section">
        <div className="netflix-row-header">
          <h2 className="netflix-row-title">
            <span style={{ color: "#e50914" }}>▶</span> Featured AI Vision
            Pipelines
          </h2>
          <span className="netflix-row-subtitle">
            Sub-second autonomous edge inference models
          </span>
        </div>

        <div className="netflix-cards-grid">
          {AI_CHANNELS.map((channel) => (
            <div
              key={channel.id}
              className="netflix-channel-card"
              onClick={() => {
                setSelectedChannel(channel.id);
                window.scrollTo({ top: 120, behavior: "smooth" });
              }}
            >
              <div className="netflix-channel-thumb">
                <span
                  className="netflix-channel-badge"
                  style={{
                    backgroundColor: "rgba(0, 0, 0, 0.8)",
                    color: channel.badgeColor,
                    border: `1px solid ${channel.badgeColor}40`,
                  }}
                >
                  {channel.badge}
                </span>

                <span className="netflix-channel-live">
                  <span
                    style={{
                      width: "6px",
                      height: "6px",
                      borderRadius: "50%",
                      backgroundColor: "#10b981",
                    }}
                  />
                  LIVE FEED
                </span>

                {/* Simulated CCTV graphic pattern */}
                <div
                  style={{
                    fontSize: "2.8rem",
                    opacity: 0.15,
                    color: "#ffffff",
                    userSelect: "none",
                  }}
                >
                  {channel.id === "uc1" && "🛡️"}
                  {channel.id === "uc2" && "🔥"}
                  {channel.id === "uc3" && "🦺"}
                  {channel.id === "uc4" && "🚛"}
                </div>
              </div>

              <div className="netflix-channel-body">
                <span className="netflix-channel-code">{channel.code}</span>
                <h3 className="netflix-channel-name">{channel.name}</h3>
                <p className="netflix-channel-desc">{channel.desc}</p>

                <div
                  style={{
                    display: "flex",
                    gap: "0.35rem",
                    flexWrap: "wrap",
                    marginBottom: "0.75rem",
                  }}
                >
                  {channel.tags.map((tag) => (
                    <span
                      key={tag}
                      style={{
                        fontSize: "0.68rem",
                        padding: "2px 6px",
                        borderRadius: "4px",
                        background: "rgba(255, 255, 255, 0.05)",
                        color: "#94a3b8",
                      }}
                    >
                      {tag}
                    </span>
                  ))}
                </div>

                <div className="netflix-channel-stats">
                  <span>
                    Latency:{" "}
                    <span className="netflix-channel-stat-val">
                      {channel.latency}
                    </span>
                  </span>
                  <span>
                    Accuracy:{" "}
                    <span className="netflix-channel-stat-val">
                      {channel.accuracy}
                    </span>
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Row 2: Mission-Critical Architecture */}
      <section id="architecture" className="netflix-section">
        <div className="netflix-row-header">
          <h2 className="netflix-row-title">
            <span style={{ color: "#3b82f6" }}>▶</span> Mission-Critical
            Architecture
          </h2>
          <span className="netflix-row-subtitle">
            Engineered for zero-loss industrial 24/7 reliability
          </span>
        </div>

        <div className="netflix-cards-grid">
          {PLATFORM_PILLARS.map((p, idx) => (
            <div
              key={idx}
              className="netflix-channel-card"
              style={{ padding: "1.5rem" }}
            >
              <div
                style={{
                  width: "48px",
                  height: "48px",
                  borderRadius: "10px",
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: "1.5rem",
                  marginBottom: "1rem",
                }}
              >
                {p.icon}
              </div>
              <span
                style={{
                  fontSize: "0.7rem",
                  fontWeight: 700,
                  color: "#3b82f6",
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  marginBottom: "0.4rem",
                }}
              >
                {p.tag}
              </span>
              <h3
                style={{
                  fontSize: "1.1rem",
                  fontWeight: 700,
                  color: "#ffffff",
                  marginBottom: "0.6rem",
                }}
              >
                {p.title}
              </h3>
              <p
                style={{
                  fontSize: "0.85rem",
                  color: "#94a3b8",
                  lineHeight: 1.55,
                }}
              >
                {p.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Call to Action Banner */}
      <section className="netflix-cta-banner">
        <h2 className="netflix-cta-title">
          Ready to Deploy Autonomous Plant Surveillance?
        </h2>
        <p className="netflix-cta-sub">
          Log in with preconfigured role credentials to inspect live cameras,
          active safety incidents, forensic audits, and executive PDF compliance
          reports.
        </p>

        <button
          onClick={handleLaunchConsole}
          className="netflix-btn-primary"
          style={{ fontSize: "1.1rem", padding: "1rem 2.2rem" }}
        >
          {isAuthenticated ? "Launch Operations Console" : "Sign In to Operations Console"} &rarr;
        </button>
      </section>

      {/* Footer */}
      <footer className="netflix-footer">
        <div className="netflix-footer-container">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span style={{ fontWeight: 800, color: "#ffffff", letterSpacing: "-0.02em" }}>
              INNOVISION
            </span>
            <span>&copy; 2026 Innovision AI Industrial Platforms.</span>
          </div>

          <div style={{ display: "flex", gap: "1.5rem", color: "#64748b" }}>
            <span>PostgreSQL 16 (pgvector)</span>
            <span>Redis 7 (LRU Hot Path)</span>
            <span>MinIO S3 Evidence</span>
            <span>FastAPI Cluster</span>
            <span>Nginx Gateway</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
