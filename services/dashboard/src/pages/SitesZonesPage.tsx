import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getOrganizations,
  getSites,
  createSite,
  getZones,
  createZone,
  getZoneAnalyticsPolicies,
  updateZoneAnalyticsPolicy,
  getZonePPERules,
  updateZonePPERules,
  getOrganizationSubscriptions,
  getAnalyticsCatalog,
} from "@/api/platform";
import { getCameras } from "@/api/cameras";
import { LoadingState } from "@/components/common/LoadingState";
import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";
import type { ZonePPERuleItem } from "@/types/platform";

const PPE_TYPES = [
  { key: "helmet", label: "Helmet" },
  { key: "safety_vest", label: "Safety Vest" },
  { key: "mask", label: "Mask" },
  { key: "safety_shoes", label: "Safety Shoes" },
  { key: "gloves", label: "Gloves" },
  { key: "safety_glasses", label: "Safety Glasses" },
  { key: "face_guard", label: "Face Guard" },
  { key: "medical_suit", label: "Medical Suit" },
];

export function SitesZonesPage() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const isUserAdmin = hasMinimumRole(user, "admin");

  const [selectedSiteId, setSelectedSiteId] = useState<string>("");
  const [selectedZoneId, setSelectedZoneId] = useState<string>("");
  const [showCreateSiteModal, setShowCreateSiteModal] = useState<boolean>(false);
  const [showCreateZoneModal, setShowCreateZoneModal] = useState<boolean>(false);

  // New site form state
  const [newSiteName, setNewSiteName] = useState("");
  const [newSiteCode, setNewSiteCode] = useState("");
  const [newSiteAddress, setNewSiteAddress] = useState("");

  // New zone form state
  const [newZoneName, setNewZoneName] = useState("");
  const [newZoneType, setNewZoneType] = useState("general");
  const [newZoneRiskLevel, setNewZoneRiskLevel] = useState("medium");

  // Error/Success messages
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Queries
  const { data: orgs, isLoading: loadingOrgs } = useQuery({
    queryKey: ["organizations"],
    queryFn: getOrganizations,
  });

  const activeOrgId = orgs && orgs.length > 0 ? orgs[0].id : "";

  const { data: catalog } = useQuery({
    queryKey: ["analyticsCatalog"],
    queryFn: getAnalyticsCatalog,
  });

  const { data: subscriptions } = useQuery({
    queryKey: ["organizationSubscriptions", activeOrgId],
    queryFn: () => getOrganizationSubscriptions(activeOrgId),
    enabled: Boolean(activeOrgId),
  });

  const { data: sites, isLoading: loadingSites } = useQuery({
    queryKey: ["sites", activeOrgId],
    queryFn: () => getSites(activeOrgId),
    enabled: Boolean(activeOrgId),
  });

  const activeSiteId = selectedSiteId || (sites && sites.length > 0 ? sites[0].id : "");

  const { data: zones, isLoading: loadingZones } = useQuery({
    queryKey: ["zones", activeSiteId],
    queryFn: () => getZones(activeSiteId),
    enabled: Boolean(activeSiteId),
  });

  const activeZoneId = selectedZoneId || (zones && zones.length > 0 ? zones[0].id : "");

  const { data: cameras } = useQuery({
    queryKey: ["cameras"],
    queryFn: getCameras,
  });

  // Selected Zone Analytics Policies
  const { data: zonePolicies, isLoading: loadingPolicies } = useQuery({
    queryKey: ["zoneAnalyticsPolicies", activeZoneId],
    queryFn: () => getZoneAnalyticsPolicies(activeZoneId),
    enabled: Boolean(activeZoneId),
  });

  // Selected Zone PPE Rules
  const { data: ppeRulesConfig, isLoading: loadingPPERules } = useQuery({
    queryKey: ["zonePPERules", activeZoneId],
    queryFn: () => getZonePPERules(activeZoneId),
    enabled: Boolean(activeZoneId),
  });

  // PPE Rules Form State
  const [localPPERules, setLocalPPERules] = useState<Record<string, boolean>>({});
  const [localMinConfidence, setLocalMinConfidence] = useState<number | null>(null);

  // Sync PPE Rules query into local state when activeZoneId or query changes
  const activePpeRules = ppeRulesConfig?.ppe_rules || [];
  const activeMinConfidence = ppeRulesConfig?.min_confidence ?? 0.50;
  const currentConfidence = localMinConfidence !== null ? localMinConfidence : activeMinConfidence;

  // Create Site Mutation
  const createSiteMutation = useMutation({
    mutationFn: () => createSite({ organization_id: activeOrgId, name: newSiteName, code: newSiteCode, address: newSiteAddress }),
    onSuccess: (site) => {
      queryClient.invalidateQueries({ queryKey: ["sites", activeOrgId] });
      setSelectedSiteId(site.id);
      setShowCreateSiteModal(false);
      setNewSiteName("");
      setNewSiteCode("");
      setNewSiteAddress("");
      setSuccessMsg(`Site '${site.name}' created successfully.`);
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to create site"),
  });

  // Create Zone Mutation
  const createZoneMutation = useMutation({
    mutationFn: () => createZone({ site_id: activeSiteId, name: newZoneName, zone_type: newZoneType, risk_level: newZoneRiskLevel }),
    onSuccess: (zone) => {
      queryClient.invalidateQueries({ queryKey: ["zones", activeSiteId] });
      setSelectedZoneId(zone.id);
      setShowCreateZoneModal(false);
      setNewZoneName("");
      setSuccessMsg(`Zone '${zone.name}' created successfully.`);
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to create zone"),
  });

  // Toggle Policy Mutation
  const togglePolicyMutation = useMutation({
    mutationFn: ({ analyticId, isEnabled }: { analyticId: string; isEnabled: boolean }) =>
      updateZoneAnalyticsPolicy(activeZoneId, analyticId, isEnabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zoneAnalyticsPolicies", activeZoneId] });
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setSuccessMsg("Zone analytic policy updated.");
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to update zone policy"),
  });

  // Save PPE Rules Mutation
  const savePPERulesMutation = useMutation({
    mutationFn: ({ rules, minConf }: { rules: ZonePPERuleItem[]; minConf: number }) =>
      updateZonePPERules(activeZoneId, rules, minConf),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zonePPERules", activeZoneId] });
      setSuccessMsg("Zone PPE rules saved successfully.");
    },
    onError: (err: Error) => setErrorMsg(err.message || "Failed to save PPE rules"),
  });

  if (loadingOrgs || loadingSites) return <LoadingState />;

  const subsMap = new Map((subscriptions || []).map((s) => [s.analytic_id, s]));
  const activeZone = zones?.find((z) => z.id === activeZoneId);
  const zoneCameras = (cameras || []).filter((c) => (c as unknown as { zone_id?: string }).zone_id === activeZoneId);

  // Check if UC3 is enabled for the active zone
  const uc3Policy = zonePolicies?.find((p) => p.code === "uc3" || p.internal_code === "uc3");
  const isUc3EnabledForZone = Boolean(uc3Policy?.is_enabled);

  // Current PPE rule map helper
  const getCurrentPPERuleState = (typeKey: string): boolean => {
    if (typeKey in localPPERules) {
      return localPPERules[typeKey];
    }
    const found = activePpeRules.find((r) => r.ppe_type === typeKey);
    return found ? found.required : false;
  };

  const handlePPEToggle = (typeKey: string, checked: boolean) => {
    setLocalPPERules((prev) => ({ ...prev, [typeKey]: checked }));
  };

  const handleSavePPERules = () => {
    const rulesToSave: ZonePPERuleItem[] = PPE_TYPES.map(({ key }) => ({
      ppe_type: key,
      required: getCurrentPPERuleState(key),
      severity: key === "helmet" || key === "safety_vest" ? "high" : "medium",
      grace_seconds: 0,
    }));
    savePPERulesMutation.mutate({ rules: rulesToSave, minConf: currentConfidence });
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">Sites & Zones Management</h1>
          <p className="page-description">
            Configure plant sites, physical zones, zone analytics policies, and UC3 PPE requirements.
          </p>
        </div>
      </header>

      {errorMsg && (
        <div style={{ padding: "12px", background: "var(--danger-bg)", border: "1px solid rgba(248,113,113,0.3)", color: "var(--danger)", borderRadius: "6px", marginBottom: "16px" }}>
          {errorMsg}
          <button onClick={() => setErrorMsg(null)} style={{ float: "right", background: "none", border: "none", color: "var(--danger)" }}>✕</button>
        </div>
      )}

      {successMsg && (
        <div style={{ padding: "12px", background: "var(--success-bg)", border: "1px solid rgba(70,189,146,0.3)", color: "var(--success)", borderRadius: "6px", marginBottom: "16px" }}>
          {successMsg}
          <button onClick={() => setSuccessMsg(null)} style={{ float: "right", background: "none", border: "none", color: "var(--success)" }}>✕</button>
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "24px" }}>
        {/* Left Column: Navigation tree (Sites & Zones list) */}
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "16px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", paddingBottom: "8px", borderBottom: "1px solid var(--border)" }}>
            <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 650, color: "var(--text-primary)" }}>PLANT SITES</h3>
            {isUserAdmin && (
              <button
                type="button"
                onClick={() => setShowCreateSiteModal(true)}
                style={{ background: "var(--primary-bg)", border: "1px solid var(--primary)", color: "var(--primary)", padding: "3px 8px", borderRadius: "4px", fontSize: "12px" }}
              >
                + Add Site
              </button>
            )}
          </div>

          {sites && sites.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
              {sites.map((site) => {
                const isSiteSelected = site.id === activeSiteId;
                return (
                  <div key={site.id} style={{ border: isSiteSelected ? "1px solid var(--primary)" : "1px solid var(--border)", borderRadius: "6px", background: isSiteSelected ? "var(--surface-raised)" : "transparent", padding: "10px" }}>
                    <div
                      onClick={() => { setSelectedSiteId(site.id); setSelectedZoneId(""); }}
                      style={{ cursor: "pointer", fontWeight: 600, fontSize: "14px", color: isSiteSelected ? "var(--primary)" : "var(--text-primary)" }}
                    >
                      📍 {site.name} ({site.code})
                    </div>

                    {isSiteSelected && (
                      <div style={{ marginTop: "10px", paddingLeft: "12px", borderLeft: "2px solid var(--border)" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                          <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>Zones</span>
                          {isUserAdmin && (
                            <button
                              type="button"
                              onClick={() => setShowCreateZoneModal(true)}
                              style={{ background: "transparent", border: "1px solid var(--border-hover)", color: "var(--text-secondary)", padding: "2px 6px", borderRadius: "3px", fontSize: "10px" }}
                            >
                              + Zone
                            </button>
                          )}
                        </div>

                        {loadingZones ? (
                          <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>Loading zones...</div>
                        ) : zones && zones.length > 0 ? (
                          zones.map((zone) => {
                            const isZoneSelected = zone.id === activeZoneId;
                            return (
                              <div
                                key={zone.id}
                                onClick={() => setSelectedZoneId(zone.id)}
                                style={{
                                  padding: "6px 8px",
                                  borderRadius: "4px",
                                  fontSize: "13px",
                                  cursor: "pointer",
                                  marginBottom: "4px",
                                  background: isZoneSelected ? "var(--primary-bg)" : "transparent",
                                  color: isZoneSelected ? "var(--primary)" : "var(--text-secondary)",
                                  fontWeight: isZoneSelected ? 600 : 400,
                                }}
                              >
                                🏢 {zone.name}
                              </div>
                            );
                          })
                        ) : (
                          <div style={{ fontSize: "12px", color: "var(--text-muted)" }}>No zones created.</div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            <div style={{ fontSize: "13px", color: "var(--text-muted)", textAlign: "center", padding: "20px 0" }}>
              No sites configured.
            </div>
          )}
        </div>

        {/* Right Column: Active Zone Configuration */}
        <div>
          {activeZone ? (
            <div>
              {/* Zone Header Info */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "20px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--primary)", textTransform: "uppercase", letterSpacing: "0.5px" }}>
                      PHYSICAL ZONE DETAILED POLICY
                    </span>
                    <h2 style={{ fontSize: "22px", fontWeight: 600, margin: "4px 0 6px 0" }}>{activeZone.name}</h2>
                    <div style={{ display: "flex", gap: "16px", fontSize: "13px", color: "var(--text-secondary)" }}>
                      <span>Type: <strong>{activeZone.zone_type}</strong></span>
                      <span>Risk Level: <strong style={{ color: activeZone.risk_level === "high" || activeZone.risk_level === "critical" ? "var(--danger)" : "var(--text-primary)" }}>{activeZone.risk_level.toUpperCase()}</strong></span>
                      <span>Cameras Assigned: <strong>{zoneCameras.length}</strong></span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Zone Analytics Policy Section */}
              <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px", marginBottom: "20px" }}>
                <h3 style={{ margin: "0 0 4px 0", fontSize: "16px", fontWeight: 600 }}>Zone Analytics Policies</h3>
                <p style={{ margin: "0 0 16px 0", fontSize: "13px", color: "var(--text-muted)" }}>
                  Cameras inside this zone inherit enabled analytics automatically unless overridden.
                </p>

                {loadingPolicies ? (
                  <LoadingState />
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "16px" }}>
                    {catalog?.map((catItem) => {
                      const policy = zonePolicies?.find((p) => p.analytic_id === catItem.id || p.code === catItem.code);
                      const sub = subsMap.get(catItem.id);
                      const isSubscribed = sub && sub.status === "enabled";
                      const isPolicyEnabled = Boolean(policy?.is_enabled);

                      return (
                        <div
                          key={catItem.id}
                          style={{
                            background: "var(--surface-raised)",
                            border: "1px solid var(--border)",
                            borderRadius: "6px",
                            padding: "16px",
                            opacity: isSubscribed ? 1 : 0.65,
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                            <span style={{ fontSize: "11px", fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase" }}>
                              {catItem.category}
                            </span>
                            {!isSubscribed && (
                              <span style={{ fontSize: "10px", fontWeight: "600", padding: "2px 6px", borderRadius: "4px", background: "var(--danger-bg)", color: "var(--danger)" }}>
                                Not Subscribed
                              </span>
                            )}
                          </div>

                          <h4 style={{ fontSize: "15px", fontWeight: 600, margin: "0 0 6px 0" }}>{catItem.display_name}</h4>
                          <p style={{ fontSize: "12px", color: "var(--text-secondary)", margin: "0 0 12px 0", minHeight: "36px" }}>
                            {catItem.description}
                          </p>

                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border)", paddingTop: "10px" }}>
                            <span style={{ fontSize: "12px", color: isPolicyEnabled ? "var(--success)" : "var(--text-muted)", fontWeight: 600 }}>
                              {isPolicyEnabled ? "✓ Active for Zone" : "Disabled for Zone"}
                            </span>

                            {isUserAdmin && (
                              <label style={{ display: "flex", alignItems: "center", cursor: isSubscribed ? "pointer" : "not-allowed" }}>
                                <input
                                  type="checkbox"
                                  disabled={!isSubscribed || togglePolicyMutation.isPending}
                                  checked={isPolicyEnabled}
                                  onChange={(e) =>
                                    togglePolicyMutation.mutate({
                                      analyticId: catItem.id,
                                      isEnabled: e.target.checked,
                                    })
                                  }
                                />
                              </label>
                            )}
                          </div>

                          {!isSubscribed && (
                            <div style={{ marginTop: "8px", fontSize: "11px", color: "var(--text-muted)" }}>
                              Unavailable: Organization subscription required.
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* UC3 PPE Configuration Section */}
              {isUc3EnabledForZone && (
                <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "20px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                    <div>
                      <h3 style={{ margin: "0 0 4px 0", fontSize: "16px", fontWeight: 600, color: "var(--primary)" }}>
                        🛡️ UC3 — PPE Requirements for {activeZone.name}
                      </h3>
                      <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted)" }}>
                        Define mandatory personal protective equipment for personnel entering this zone.
                      </p>
                    </div>

                    {isUserAdmin && (
                      <button
                        type="button"
                        onClick={handleSavePPERules}
                        disabled={savePPERulesMutation.isPending}
                        style={{
                          background: "var(--primary)",
                          border: "none",
                          color: "#fff",
                          padding: "8px 16px",
                          borderRadius: "4px",
                          fontSize: "13px",
                          fontWeight: 600,
                        }}
                      >
                        {savePPERulesMutation.isPending ? "Saving..." : "Save PPE Rules"}
                      </button>
                    )}
                  </div>

                  {loadingPPERules ? (
                    <LoadingState />
                  ) : (
                    <div>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: "12px", marginBottom: "20px" }}>
                        {PPE_TYPES.map(({ key, label }) => {
                          const isRequired = getCurrentPPERuleState(key);
                          return (
                            <label
                              key={key}
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "10px",
                                background: "var(--surface-raised)",
                                border: isRequired ? "1px solid var(--primary)" : "1px solid var(--border)",
                                borderRadius: "6px",
                                padding: "12px 14px",
                                cursor: isUserAdmin ? "pointer" : "default",
                              }}
                            >
                              <input
                                type="checkbox"
                                disabled={!isUserAdmin}
                                checked={isRequired}
                                onChange={(e) => handlePPEToggle(key, e.target.checked)}
                              />
                              <span style={{ fontSize: "13px", fontWeight: isRequired ? 600 : 400, color: isRequired ? "var(--text-primary)" : "var(--text-secondary)" }}>
                                {label}
                              </span>
                            </label>
                          );
                        })}
                      </div>

                      <div style={{ borderTop: "1px solid var(--border)", paddingTop: "16px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                          <label style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-secondary)" }}>
                            Minimum Detection Confidence Threshold:
                          </label>
                          <span style={{ fontSize: "14px", fontWeight: 700, color: "var(--primary)" }}>
                            {Math.round(currentConfidence * 100)}%
                          </span>
                        </div>

                        <input
                          type="range"
                          min="0.10"
                          max="0.95"
                          step="0.05"
                          disabled={!isUserAdmin}
                          value={currentConfidence}
                          onChange={(e) => {
                            setLocalMinConfidence(parseFloat(e.target.value));
                          }}
                          style={{ width: "100%", accentColor: "var(--primary)" }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "40px", textAlign: "center", color: "var(--text-muted)" }}>
              Select a Site and Zone on the left to configure zone analytics policy and PPE rules.
            </div>
          )}
        </div>
      </div>

      {/* Modal: Create Site */}
      {showCreateSiteModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "420px" }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Create New Plant Site</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Site Name *</label>
                <input
                  type="text"
                  placeholder="e.g. JK Cement Plant 01"
                  value={newSiteName}
                  onChange={(e) => setNewSiteName(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Site Code *</label>
                <input
                  type="text"
                  placeholder="e.g. PLANT-01"
                  value={newSiteCode}
                  onChange={(e) => setNewSiteCode(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Address / Location</label>
                <input
                  type="text"
                  placeholder="e.g. Nimbahera, Rajasthan"
                  value={newSiteAddress}
                  onChange={(e) => setNewSiteAddress(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                />
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button onClick={() => setShowCreateSiteModal(false)} style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "6px 14px", borderRadius: "4px" }}>
                Cancel
              </button>
              <button
                onClick={() => createSiteMutation.mutate()}
                disabled={!newSiteName || !newSiteCode || createSiteMutation.isPending}
                style={{ background: "var(--primary)", border: "none", color: "#fff", padding: "6px 16px", borderRadius: "4px", fontWeight: 600 }}
              >
                {createSiteMutation.isPending ? "Creating..." : "Create Site"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Create Zone */}
      {showCreateZoneModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "8px", padding: "24px", width: "100%", maxWidth: "420px" }}>
            <h3 style={{ margin: "0 0 16px 0", fontSize: "18px" }}>Create Zone for Active Site</h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "12px", marginBottom: "20px" }}>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Zone Name *</label>
                <input
                  type="text"
                  placeholder="e.g. Kiln Area Zone"
                  value={newZoneName}
                  onChange={(e) => setNewZoneName(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                />
              </div>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Zone Type</label>
                <select
                  value={newZoneType}
                  onChange={(e) => setNewZoneType(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                >
                  <option value="general">General</option>
                  <option value="kiln">Kiln Area</option>
                  <option value="loading_yard">Loading Yard</option>
                  <option value="conveyor">Conveyor Belt</option>
                  <option value="storage">Storage & Silo</option>
                  <option value="entrance">Main Gate / Entrance</option>
                </select>
              </div>
              <div>
                <label style={{ display: "block", fontSize: "12px", color: "var(--text-secondary)", marginBottom: "4px" }}>Risk Level</label>
                <select
                  value={newZoneRiskLevel}
                  onChange={(e) => setNewZoneRiskLevel(e.target.value)}
                  style={{ width: "100%", background: "var(--surface-raised)", border: "1px solid var(--border)", color: "var(--text-primary)", padding: "8px 12px", borderRadius: "4px" }}
                >
                  <option value="low">Low Risk</option>
                  <option value="medium">Medium Risk</option>
                  <option value="high">High Risk</option>
                  <option value="critical">Critical Risk</option>
                </select>
              </div>
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "12px" }}>
              <button onClick={() => setShowCreateZoneModal(false)} style={{ background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", padding: "6px 14px", borderRadius: "4px" }}>
                Cancel
              </button>
              <button
                onClick={() => createZoneMutation.mutate()}
                disabled={!newZoneName || createZoneMutation.isPending}
                style={{ background: "var(--primary)", border: "none", color: "#fff", padding: "6px 16px", borderRadius: "4px", fontWeight: 600 }}
              >
                {createZoneMutation.isPending ? "Creating..." : "Create Zone"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
