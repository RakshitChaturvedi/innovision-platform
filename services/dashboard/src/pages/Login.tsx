import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/store/useAuth";

export function Login() {
  const { login, loginAsDemo, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const [email, setEmail] = useState("admin@innovision.com");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError("");
    setLoading(true);

    try {
      await login(email, password);

      const from = location.state?.from?.pathname ?? "/";
      navigate(from, { replace: true });
    } catch {
      setError("Unable to authenticate with backend. Use Quick Demo Sign-In below if Docker is offline.");
    } finally {
      setLoading(false);
    }
  }

  function handleDemoSignIn(role: "superadmin" | "operator" = "superadmin") {
    loginAsDemo(role);
    const from = location.state?.from?.pathname ?? "/";
    navigate(from, { replace: true });
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "var(--bg, #0f1117)",
        padding: "20px",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: "420px",
          backgroundColor: "var(--surface, #15171e)",
          border: "1px solid var(--border, #292d36)",
          borderRadius: "14px",
          padding: "32px",
          boxShadow: "0 20px 40px rgba(0, 0, 0, 0.4)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
          <div
            style={{
              width: "36px",
              height: "36px",
              borderRadius: "8px",
              backgroundColor: "var(--primary, #A646BD)",
              color: "#fff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontWeight: 800,
              fontSize: "18px",
            }}
          >
            I
          </div>
          <div>
            <h1 style={{ fontSize: "20px", fontWeight: 700, margin: 0, color: "var(--text-primary, #f1f3f5)" }}>
              Innovision Platform
            </h1>
            <p style={{ fontSize: "12px", color: "var(--text-muted, #707786)", margin: 0 }}>
              Master Multi-Zone Operational Dashboard
            </p>
          </div>
        </div>

        {error && (
          <div
            style={{
              marginTop: "16px",
              padding: "10px 14px",
              borderRadius: "8px",
              backgroundColor: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.35)",
              color: "#f87171",
              fontSize: "12px",
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ marginTop: "24px" }}>
          <div style={{ marginBottom: "16px" }}>
            <label
              style={{
                display: "block",
                fontSize: "12px",
                fontWeight: 600,
                color: "var(--text-secondary, #a2a8b5)",
                marginBottom: "6px",
              }}
            >
              Email Address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={{
                width: "100%",
                padding: "10px 12px",
                borderRadius: "8px",
                border: "1px solid var(--border, #292d36)",
                backgroundColor: "var(--bg, #0f1117)",
                color: "var(--text-primary, #f1f3f5)",
                fontSize: "13px",
              }}
            />
          </div>

          <div style={{ marginBottom: "20px" }}>
            <label
              style={{
                display: "block",
                fontSize: "12px",
                fontWeight: 600,
                color: "var(--text-secondary, #a2a8b5)",
                marginBottom: "6px",
              }}
            >
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              style={{
                width: "100%",
                padding: "10px 12px",
                borderRadius: "8px",
                border: "1px solid var(--border, #292d36)",
                backgroundColor: "var(--bg, #0f1117)",
                color: "var(--text-primary, #f1f3f5)",
                fontSize: "13px",
              }}
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "11px",
              borderRadius: "8px",
              border: "none",
              backgroundColor: "var(--primary, #A646BD)",
              color: "#ffffff",
              fontSize: "13px",
              fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Authenticating..." : "Sign in via Platform"}
          </button>
        </form>

        <div
          style={{
            marginTop: "24px",
            paddingTop: "20px",
            borderTop: "1px solid var(--border, #292d36)",
          }}
        >
          <div
            style={{
              fontSize: "11px",
              fontWeight: 600,
              color: "var(--text-muted, #707786)",
              textTransform: "uppercase",
              letterSpacing: "0.04em",
              marginBottom: "12px",
              textAlign: "center",
            }}
          >
            Standalone Frontend Testing (No Docker)
          </div>

          <div style={{ display: "flex", gap: "10px" }}>
            <button
              type="button"
              onClick={() => handleDemoSignIn("superadmin")}
              style={{
                flex: 1,
                padding: "9px 12px",
                borderRadius: "8px",
                backgroundColor: "rgba(166, 70, 189, 0.15)",
                border: "1px solid rgba(166, 70, 189, 0.4)",
                color: "#e879f9",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              👑 Demo Admin
            </button>

            <button
              type="button"
              onClick={() => handleDemoSignIn("operator")}
              style={{
                flex: 1,
                padding: "9px 12px",
                borderRadius: "8px",
                backgroundColor: "rgba(59, 130, 246, 0.15)",
                border: "1px solid rgba(59, 130, 246, 0.4)",
                color: "#60a5fa",
                fontSize: "12px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              🛡️ Demo Operator
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
export default Login;