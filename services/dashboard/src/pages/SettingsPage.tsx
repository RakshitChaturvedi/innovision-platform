import { useEffect, useState } from "react";
import { fetchSettings, updateOrganizationSettings, type SettingsResponse } from "../api/settings";
import {
  fetchNotificationPreferences,
  updateNotificationPreferences,
  type NotificationPreferenceItem,
} from "../api/notifications";

const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

type SettingsTab = "organization" | "security" | "platform" | "subscriptions" | "notifications";

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("organization");
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [notificationPrefs, setNotificationPrefs] = useState<NotificationPreferenceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Editable Form fields
  const [orgName, setOrgName] = useState("");
  const [timezone, setTimezone] = useState("UTC");

  useEffect(() => {
    let isMounted = true;

    Promise.all([fetchSettings(), fetchNotificationPreferences()])
      .then(([settingsData, prefsData]) => {
        if (isMounted) {
          setSettings(settingsData);
          if (settingsData.organization) {
            setOrgName(settingsData.organization.name);
            setTimezone(settingsData.organization.timezone || "UTC");
          }
          setNotificationPrefs(prefsData);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (isMounted) {
          const errorObj = err as { response?: { data?: { detail?: string } } };
          setError(errorObj?.response?.data?.detail || "Failed to load platform settings.");
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleTogglePref = (typeStr: string, channel: "in_app_enabled" | "email_enabled") => {
    setNotificationPrefs((prev) =>
      prev.map((item) => {
        if (item.notification_type === typeStr) {
          return {
            ...item,
            [channel]: !item[channel],
          };
        }
        return item;
      })
    );
  };

  const handleSaveNotificationPrefs = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const updates = notificationPrefs.map((item) => ({
        notification_type: item.notification_type,
        in_app_enabled: item.in_app_enabled,
        email_enabled: item.email_enabled,
      }));

      const updated = await updateNotificationPreferences(updates);
      setNotificationPrefs(updated);
      setSuccessMsg("Notification preferences updated successfully. Audit log recorded.");
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } } };
      setError(errorObj?.response?.data?.detail || "Failed to update notification preferences.");
    } finally {
      setSaving(false);
    }
  };

  const handleSaveOrganization = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!orgName.trim()) {
      setError("Organization name cannot be empty.");
      return;
    }

    setSaving(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const updated = await updateOrganizationSettings({
        name: orgName.trim(),
        timezone: timezone,
      });

      setSuccessMsg("Organization settings updated successfully. Audit entry recorded.");
      if (settings) {
        setSettings({
          ...settings,
          organization: updated,
        });
      }
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: unknown) {
      const errorObj = err as { response?: { data?: { detail?: string } } };
      setError(errorObj?.response?.data?.detail || "Failed to update organization settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page" style={{ padding: "24px" }}>
      <header className="page-header" style={{ marginBottom: "24px" }}>
        <div>
          <h1 className="page-title" style={{ margin: 0, fontSize: "24px", fontWeight: 600 }}>
            Enterprise Settings
          </h1>
          <p className="page-description" style={{ margin: "4px 0 0 0", color: "var(--text-secondary)", fontSize: "14px" }}>
            Organization profile, security policies, service health status, and analytics subscriptions.
          </p>
        </div>
      </header>

      {/* Tabs */}
      <div style={{ display: "flex", gap: "8px", borderBottom: "1px solid var(--border)", marginBottom: "24px" }}>
        {[
          { id: "organization", label: "Organization Profile" },
          { id: "notifications", label: "Notification Preferences" },
          { id: "security", label: "Security & Access" },
          { id: "platform", label: "Platform & System Health" },
          { id: "subscriptions", label: "Analytics Subscriptions" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id as SettingsTab)}
            style={{
              padding: "10px 16px",
              background: "none",
              border: "none",
              borderBottom: activeTab === tab.id ? "2px solid var(--accent)" : "2px solid transparent",
              color: activeTab === tab.id ? "var(--text-primary)" : "var(--text-secondary)",
              fontWeight: activeTab === tab.id ? 600 : 400,
              fontSize: "14px",
              cursor: "pointer",
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Alert Banners */}
      {error && (
        <div
          style={{
            padding: "12px 16px",
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.3)",
            borderRadius: "6px",
            color: "#ef4444",
            marginBottom: "20px",
            fontSize: "14px",
          }}
        >
          {error}
        </div>
      )}

      {successMsg && (
        <div
          style={{
            padding: "12px 16px",
            background: "rgba(16, 185, 129, 0.1)",
            border: "1px solid rgba(16, 185, 129, 0.3)",
            borderRadius: "6px",
            color: "#10b981",
            marginBottom: "20px",
            fontSize: "14px",
          }}
        >
          {successMsg}
        </div>
      )}

      {loading ? (
        <div style={{ padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
          Loading platform configuration...
        </div>
      ) : (
        <div>
          {/* Tab 1: Organization Profile */}
          {activeTab === "organization" && (
            <div
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "24px",
                maxWidth: "680px",
              }}
            >
              <h2 style={{ margin: "0 0 16px 0", fontSize: "16px", fontWeight: 600 }}>Organization Details</h2>
              <form onSubmit={handleSaveOrganization} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "13px", fontWeight: 500, marginBottom: "6px" }}>
                    Organization Name
                  </label>
                  <input
                    type="text"
                    value={orgName}
                    onChange={(e) => setOrgName(e.target.value)}
                    placeholder="Enterprise Organization Name"
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      border: "1px solid var(--border)",
                      background: "var(--background)",
                      color: "var(--text-primary)",
                      fontSize: "14px",
                    }}
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "13px", fontWeight: 500, marginBottom: "6px" }}>
                      Organization Code (Read-Only)
                    </label>
                    <input
                      type="text"
                      value={settings?.organization?.code || ""}
                      readOnly
                      style={{
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: "6px",
                        border: "1px solid var(--border)",
                        background: "var(--surface-hover)",
                        color: "var(--text-muted)",
                        fontSize: "14px",
                        cursor: "not-allowed",
                      }}
                    />
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "13px", fontWeight: 500, marginBottom: "6px" }}>
                      Tier
                    </label>
                    <input
                      type="text"
                      value={settings?.organization?.tier?.toUpperCase() || "ENTERPRISE"}
                      readOnly
                      style={{
                        width: "100%",
                        padding: "8px 12px",
                        borderRadius: "6px",
                        border: "1px solid var(--border)",
                        background: "var(--surface-hover)",
                        color: "var(--text-muted)",
                        fontSize: "14px",
                        cursor: "not-allowed",
                      }}
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "13px", fontWeight: 500, marginBottom: "6px" }}>
                    Platform Timezone
                  </label>
                  <select
                    value={timezone}
                    onChange={(e) => setTimezone(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "8px 12px",
                      borderRadius: "6px",
                      border: "1px solid var(--border)",
                      background: "var(--background)",
                      color: "var(--text-primary)",
                      fontSize: "14px",
                    }}
                  >
                    {TIMEZONES.map((tz) => (
                      <option key={tz} value={tz}>
                        {tz}
                      </option>
                    ))}
                  </select>
                </div>

                <div style={{ paddingTop: "12px", display: "flex", justifyContent: "flex-end" }}>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={saving}
                    style={{
                      padding: "8px 20px",
                      borderRadius: "6px",
                      fontSize: "14px",
                      fontWeight: 500,
                      cursor: saving ? "not-allowed" : "pointer",
                    }}
                  >
                    {saving ? "Saving Changes..." : "Save Changes"}
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Tab 2: Security & Access */}
          {activeTab === "security" && (
            <div
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "24px",
                maxWidth: "680px",
              }}
            >
              <h2 style={{ margin: "0 0 16px 0", fontSize: "16px", fontWeight: 600 }}>Security & Authentication</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: "16px", fontSize: "14px" }}>
                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>Authentication Mechanism</label>
                  <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                    {settings?.security?.auth_provider}
                  </div>
                </div>

                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>JWT Session Token Validity</label>
                  <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                    {settings?.security?.session_duration}
                  </div>
                </div>

                <div>
                  <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>Active RBAC Roles Supported</label>
                  <div style={{ display: "flex", gap: "8px", marginTop: "6px" }}>
                    {settings?.security?.supported_roles?.map((role) => (
                      <span
                        key={role}
                        style={{
                          padding: "4px 10px",
                          borderRadius: "4px",
                          background: "var(--background)",
                          border: "1px solid var(--border)",
                          fontSize: "12px",
                          fontWeight: 600,
                          color: "var(--accent)",
                        }}
                      >
                        {role}
                      </span>
                    ))}
                  </div>
                </div>

                <div style={{ paddingTop: "12px" }}>
                  <a
                    href="/admin/users"
                    className="btn btn-secondary"
                    style={{
                      display: "inline-block",
                      padding: "8px 16px",
                      borderRadius: "6px",
                      fontSize: "13px",
                      textDecoration: "none",
                    }}
                  >
                    Manage Organization Users & Roles →
                  </a>
                </div>
              </div>
            </div>
          )}

          {/* Tab 3: Platform & System Health */}
          {activeTab === "platform" && (
            <div
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "24px",
                maxWidth: "680px",
              }}
            >
              <h2 style={{ margin: "0 0 16px 0", fontSize: "16px", fontWeight: 600 }}>Platform System Status</h2>
              <div style={{ display: "flex", flexDirection: "column", gap: "16px", fontSize: "14px" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                  <div>
                    <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>Platform Name</label>
                    <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                      {settings?.platform?.platform_name}
                    </div>
                  </div>

                  <div>
                    <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>Platform Version</label>
                    <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                      {settings?.platform?.version}
                    </div>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                  <div>
                    <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>Environment</label>
                    <div style={{ fontWeight: 500, color: "var(--text-primary)", marginTop: "2px" }}>
                      {settings?.platform?.environment}
                    </div>
                  </div>

                  <div>
                    <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>System Health</label>
                    <div style={{ fontWeight: 600, color: "var(--success)", marginTop: "2px" }}>
                      ● Operational
                    </div>
                  </div>
                </div>

                <hr style={{ border: "none", borderTop: "1px solid var(--border)", margin: "8px 0" }} />

                <label style={{ color: "var(--text-muted)", fontSize: "12px" }}>Core Backend Services Status</label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px" }}>
                  {[
                    "Auth Service (8000)",
                    "Camera Registry (8011)",
                    "Alert Management (8000)",
                    "Incident Management (8000)",
                    "Audit & Settings (8000)",
                    "Reporting Service (8000)",
                    "UC3 Inference Engine (8023)",
                  ].map((svc) => (
                    <div
                      key={svc}
                      style={{
                        padding: "8px 12px",
                        background: "var(--background)",
                        border: "1px solid var(--border)",
                        borderRadius: "6px",
                        fontSize: "12px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <span style={{ color: "var(--text-primary)" }}>{svc}</span>
                      <span style={{ color: "var(--success)", fontWeight: 600 }}>Active</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Tab 4: Analytics Subscriptions */}
          {activeTab === "subscriptions" && (
            <div
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "24px",
                maxWidth: "760px",
              }}
            >
              <h2 style={{ margin: "0 0 8px 0", fontSize: "16px", fontWeight: 600 }}>Active Analytics Catalog</h2>
              <p style={{ margin: "0 0 16px 0", color: "var(--text-muted)", fontSize: "13px" }}>
                Summary of analytics enabled for this organization. Specific camera policies and overrides are managed in
                Sites & Zones.
              </p>

              <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                {settings?.subscriptions?.map((sub) => (
                  <div
                    key={sub.analytic_id}
                    style={{
                      padding: "16px",
                      background: "var(--background)",
                      border: "1px solid var(--border)",
                      borderRadius: "6px",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                        <span style={{ fontWeight: 600, fontSize: "14px", color: "var(--text-primary)" }}>
                          {sub.name}
                        </span>
                        <span
                          style={{
                            padding: "2px 6px",
                            borderRadius: "4px",
                            background: "var(--surface)",
                            border: "1px solid var(--border)",
                            fontSize: "11px",
                            fontWeight: 600,
                            color: "var(--text-secondary)",
                          }}
                        >
                          {sub.code}
                        </span>
                      </div>
                      {sub.description && (
                        <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                          {sub.description}
                        </div>
                      )}
                    </div>

                    <div>
                      <span
                        style={{
                          padding: "4px 10px",
                          borderRadius: "4px",
                          fontSize: "12px",
                          fontWeight: 600,
                          background: sub.status === "active" ? "rgba(16, 185, 129, 0.1)" : "rgba(239, 68, 68, 0.1)",
                          color: sub.status === "active" ? "var(--success)" : "var(--warning)",
                          border: `1px solid ${sub.status === "active" ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"}`,
                        }}
                      >
                        {sub.status === "active" ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tab 5: Notification Preferences */}
          {activeTab === "notifications" && (
            <div
              style={{
                background: "var(--surface)",
                border: "1px solid var(--border)",
                borderRadius: "8px",
                padding: "24px",
                maxWidth: "760px",
              }}
            >
              <h2 style={{ margin: "0 0 8px 0", fontSize: "16px", fontWeight: 600 }}>Real-Time & Email Notification Settings</h2>
              <p style={{ margin: "0 0 20px 0", color: "var(--text-muted)", fontSize: "13px" }}>
                Configure delivery channels for platform safety alerts, incident assignments, and status updates.
              </p>

              <form onSubmit={handleSaveNotificationPrefs} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                  {notificationPrefs.map((pref) => (
                    <div
                      key={pref.notification_type}
                      style={{
                        padding: "16px",
                        background: "var(--background)",
                        border: "1px solid var(--border)",
                        borderRadius: "8px",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <div style={{ flex: 1, paddingRight: "16px" }}>
                        <div style={{ fontWeight: 600, fontSize: "14px", color: "var(--text-primary)" }}>
                          {pref.display_name}
                        </div>
                        <div style={{ fontSize: "12px", color: "var(--text-muted)", marginTop: "4px" }}>
                          {pref.description}
                        </div>
                      </div>

                      <div style={{ display: "flex", gap: "20px", alignItems: "center" }}>
                        <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={pref.in_app_enabled}
                            onChange={() => handleTogglePref(pref.notification_type, "in_app_enabled")}
                            style={{ accentColor: "var(--accent)" }}
                          />
                          In-App
                        </label>

                        <label style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "13px", cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={pref.email_enabled}
                            onChange={() => handleTogglePref(pref.notification_type, "email_enabled")}
                            style={{ accentColor: "var(--accent)" }}
                          />
                          Email
                        </label>
                      </div>
                    </div>
                  ))}
                </div>

                <div style={{ paddingTop: "12px", display: "flex", justifyContent: "flex-end" }}>
                  <button
                    type="submit"
                    className="btn btn-primary"
                    disabled={saving}
                    style={{
                      padding: "8px 20px",
                      borderRadius: "6px",
                      fontSize: "14px",
                      fontWeight: 500,
                      cursor: saving ? "not-allowed" : "pointer",
                    }}
                  >
                    {saving ? "Saving Preferences..." : "Save Preferences"}
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
