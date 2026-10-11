import { useState } from "react";

import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/store/useAuth";
import "../landing.css";

interface DemoAccount {
  label: string;
  role: string;
  email: string;
  pass: string;
  icon: string;
  desc: string;
}

const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    label: "Superadmin",
    role: "Full Authority",
    email: "admin@innovision.com",
    pass: "admin123",
    icon: "👑",
    desc: "Executive Oversight & Fleet Control",
  },
  {
    label: "Shift Operator",
    role: "Triage & Alerts",
    email: "operator@innovision.com",
    pass: "admin123",
    icon: "⚡",
    desc: "Live Monitoring & Incident Escalation",
  },
  {
    label: "Plant Viewer",
    role: "Read-Only Feeds",
    email: "viewer@innovision.com",
    pass: "admin123",
    icon: "👁️",
    desc: "CCTV Video Wall & Analytics",
  },
  {
    label: "Safety Admin",
    role: "System Settings",
    email: "devadmin@innovision.com",
    pass: "admin123",
    icon: "🛡️",
    desc: "Zone Rules & Camera Registry",
  },
];

export function Login() {
  const { login, isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("admin@innovision.com");
  const [password, setPassword] = useState("admin123");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedDemoIndex, setSelectedDemoIndex] = useState<number>(0);

  // If already authenticated, redirect to role dashboard
  if (isAuthenticated && user) {
    if (user.role === "operator") {
      return <Navigate to="/alerts" replace />;
    } else if (user.role === "viewer") {
      return <Navigate to="/live-monitoring" replace />;
    }
    return <Navigate to="/" replace />;
  }

  const handleSelectDemo = (idx: number) => {
    setSelectedDemoIndex(idx);
    setEmail(DEMO_ACCOUNTS[idx].email);
    setPassword(DEMO_ACCOUNTS[idx].pass);
    setError("");
  };

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const loggedUser = await login(email, password);

      // Check if there was an intended redirect
      const fromPath = location.state?.from?.pathname;
      if (fromPath && fromPath !== "/login" && fromPath !== "/") {
        navigate(fromPath, { replace: true });
        return;
      }

      // Role-based redirection to corresponding dashboard
      if (loggedUser.role === "operator") {
        navigate("/alerts", { replace: true });
      } else if (loggedUser.role === "viewer") {
        navigate("/live-monitoring", { replace: true });
      } else {
        navigate("/", { replace: true });
      }
    } catch (err: unknown) {
      console.error("Login failed:", err);
      setError("Authentication failed. Please verify your email and password.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="netflix-login-root">
      {/* Top Navbar */}
      <header className="netflix-login-nav">
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
            <span className="netflix-logo-tag">ACCESS</span>
          </div>
        </Link>

        <Link
          to="/"
          style={{
            color: "#9ca3af",
            fontSize: "0.88rem",
            textDecoration: "none",
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            fontWeight: 500,
          }}
        >
          &larr; Back to Platform Showcase
        </Link>
      </header>

      {/* Main Login Card */}
      <div className="netflix-login-card-container">
        <div className="netflix-login-card">
          <div style={{ textAlign: "center", marginBottom: "1.75rem" }}>
            <h1
              style={{
                fontSize: "1.85rem",
                fontWeight: 800,
                color: "#ffffff",
                letterSpacing: "-0.02em",
                marginBottom: "0.4rem",
              }}
            >
              Command Center Sign In
            </h1>
            <p style={{ color: "#94a3b8", fontSize: "0.88rem" }}>
              Access video analytics, active alerts, and incident triage
            </p>
          </div>

          {/* Quick Demo Role Selector Chips */}
          <div style={{ marginBottom: "1.5rem" }}>
            <label
              style={{
                display: "block",
                fontSize: "0.75rem",
                fontWeight: 700,
                color: "#64748b",
                textTransform: "uppercase",
                letterSpacing: "0.08em",
                marginBottom: "0.6rem",
              }}
            >
              1-Click Demo Profiles (Preconfigured)
            </label>
            <div className="netflix-role-pills">
              {DEMO_ACCOUNTS.map((acc, idx) => (
                <button
                  type="button"
                  key={acc.label}
                  onClick={() => handleSelectDemo(idx)}
                  className={`netflix-role-pill-btn ${
                    selectedDemoIndex === idx ? "active" : ""
                  }`}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      marginBottom: "2px",
                    }}
                  >
                    <span>
                      {acc.icon} {acc.label}
                    </span>
                    {selectedDemoIndex === idx && (
                      <span
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "50%",
                          backgroundColor: "#e50914",
                        }}
                      />
                    )}
                  </div>
                  <span
                    style={{
                      fontSize: "0.68rem",
                      color:
                        selectedDemoIndex === idx ? "#fca5a5" : "#64748b",
                    }}
                  >
                    {acc.role}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div
              style={{
                marginBottom: "1.25rem",
                padding: "0.75rem 1rem",
                background: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.35)",
                borderRadius: "8px",
                color: "#fca5a5",
                fontSize: "0.85rem",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <span>⚠️</span>
              <span>{error}</span>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit}>
            <div className="netflix-form-group">
              <label className="netflix-form-label">Work Email</label>
              <div className="netflix-input-wrap">
                <input
                  type="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setSelectedDemoIndex(-1);
                  }}
                  required
                  placeholder="operator@innovision.com"
                  className="netflix-input"
                />
              </div>
            </div>

            <div className="netflix-form-group">
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                }}
              >
                <label className="netflix-form-label">Password</label>
                <span
                  style={{
                    fontSize: "0.72rem",
                    color: "#64748b",
                    fontFamily: "monospace",
                  }}
                >
                  Default: admin123
                </span>
              </div>
              <div className="netflix-input-wrap">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setSelectedDemoIndex(-1);
                  }}
                  required
                  placeholder="••••••••"
                  className="netflix-input"
                  style={{ paddingRight: "40px" }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="netflix-input-eye"
                  title={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? "🙈" : "👁️"}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="netflix-btn-primary"
              style={{
                width: "100%",
                marginTop: "0.75rem",
                justifyContent: "center",
                padding: "0.85rem",
                fontSize: "1rem",
              }}
            >
              {loading ? (
                <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span
                    style={{
                      width: "16px",
                      height: "16px",
                      border: "2px solid #ffffff",
                      borderTopColor: "transparent",
                      borderRadius: "50%",
                      animation: "spin 0.8s linear infinite",
                    }}
                  />
                  Authenticating...
                </span>
              ) : (
                `Sign In as ${
                  selectedDemoIndex >= 0
                    ? DEMO_ACCOUNTS[selectedDemoIndex].label
                    : "Operator"
                } &rarr;`
              )}
            </button>
          </form>

          {/* Quick Guidance Info */}
          <div
            style={{
              marginTop: "1.75rem",
              paddingTop: "1.25rem",
              borderTop: "1px solid rgba(255, 255, 255, 0.08)",
              display: "flex",
              justifyContent: "space-between",
              fontSize: "0.75rem",
              color: "#64748b",
            }}
          >
            <span>Auth Server: Port 8000 (Active)</span>
            <span>RBAC: JWT Signed</span>
          </div>
        </div>
      </div>
    </div>
  );
}