export type CameraStatus =
  | "online"
  | "offline"
  | "reconnecting"
  | "disabled";

export type ZoneType =
  | "critical_hazard"
  | "deliberate_flame"
  | "restricted_entry"
  | "occupancy_flow"
  | "mandatory_ppe"
  | "speed_enforcement"
  | "access_control";

export interface ZoneConfig {
  id: string;
  name: string;
  use_case: "uc1" | "uc2" | "uc3" | "uc4";
  type: ZoneType;
  typeLabel: string;
  description: string;
  policy: string;
  badgeColor: string;
  badgeBg: string;
  borderColor: string;
  alertOnFire?: boolean;
  alertOnSmoke?: boolean;
}

export interface Camera {
  id: string;
  name: string;
  location?: string | null;
  rtsp_url: string | null;
  status: "online" | "offline" | "reconnecting" | "disabled";
  use_cases: string[];
  fps: number;
  zone_id?: string;
  zone_name?: string;
  zone_type?: ZoneType;
  zone_policy?: string;
  demo_video?: string;
  metadata?: Record<string, unknown>;
}

/** UC metadata used for zone-grouped dashboard layouts. */
export interface UseCaseConfig {
  id: string;
  label: string;
  description: string;
  model: string;
  color: string;
  colorBg: string;
  icon: string;
  zoneCount: number;
}

/** Pre-defined UC metadata. */
export const USE_CASE_CONFIGS: Record<string, UseCaseConfig> = {
  uc1: {
    id: "uc1",
    label: "Worker Count & Presence",
    description: "Real-time occupancy monitoring and worker density tracking",
    model: "YOLOv8n Person Tracking",
    color: "#3b82f6",
    colorBg: "rgba(59, 130, 246, 0.15)",
    icon: "👷",
    zoneCount: 3,
  },
  uc2: {
    id: "uc2",
    label: "Fire / Smoke / Sparks Detection",
    description: "Multi-stage CV pipeline with HSV, texture & deliberate fire zoning",
    model: "YOLOv8 best.pt + HSV",
    color: "#ef4444",
    colorBg: "rgba(239, 68, 68, 0.15)",
    icon: "🔥",
    zoneCount: 3,
  },
  uc3: {
    id: "uc3",
    label: "PPE Safety Compliance",
    description: "Safety helmet, vest & personal protection compliance verification",
    model: "Safety Helmet & Vest Inspection",
    color: "#06b6d4",
    colorBg: "rgba(6, 182, 212, 0.15)",
    icon: "🦺",
    zoneCount: 3,
  },
  uc4: {
    id: "uc4",
    label: "Vehicle Access & Speed",
    description: "ANPR plate reading, radar-based speed estimation & traffic access",
    model: "YOLO11m + PaddleOCR + SpeedEstimator",
    color: "#14b8a6",
    colorBg: "rgba(20, 184, 166, 0.15)",
    icon: "🚗",
    zoneCount: 3,
  },
};

/** Pre-defined operational Zone configurations with security & safety policies. */
export const ZONE_CONFIGS: Record<string, ZoneConfig> = {
  // UC1 Zones
  "uc1-zone-lobby": {
    id: "uc1-zone-lobby",
    name: "Zone A — Main Lobby & Turnstile",
    use_case: "uc1",
    type: "occupancy_flow",
    typeLabel: "Turnstile Flow",
    description: "Facility main entrance turnstiles and visitor check-in area",
    policy: "Continuous Headcount & Ingress Flow Monitoring (Threshold: 50 persons)",
    badgeColor: "#3b82f6",
    badgeBg: "rgba(59, 130, 246, 0.15)",
    borderColor: "rgba(59, 130, 246, 0.35)",
  },
  "uc1-zone-assembly": {
    id: "uc1-zone-assembly",
    name: "Zone B — Assembly Floor Line A",
    use_case: "uc1",
    type: "occupancy_flow",
    typeLabel: "Workstation Floor",
    description: "Active manufacturing and assembly conveyor stations",
    policy: "Occupancy Density Limit: Max 35 Operators across active stations",
    badgeColor: "#3b82f6",
    badgeBg: "rgba(59, 130, 246, 0.15)",
    borderColor: "rgba(59, 130, 246, 0.35)",
  },
  "uc1-zone-server": {
    id: "uc1-zone-server",
    name: "Zone C — Server Room & Archives",
    use_case: "uc1",
    type: "restricted_entry",
    typeLabel: "Restricted Vault",
    description: "High-security IT server vault and electrical control room",
    policy: "Strict Zero-Occupancy outside scheduled maintenance tickets (Instant Intruder Alert)",
    badgeColor: "#a855f7",
    badgeBg: "rgba(168, 85, 247, 0.15)",
    borderColor: "rgba(168, 85, 247, 0.35)",
  },

  // UC2 Zones (Deliberate flame vs. critical danger)
  "uc2-zone-boiler": {
    id: "uc2-zone-boiler",
    name: "Zone A — Boiler Room West",
    use_case: "uc2",
    type: "critical_hazard",
    typeLabel: "Critical Danger",
    description: "Thermal core, high-pressure boilers, and steam generators",
    policy: "Zero-Tolerance Fire Hazard: Immediate emergency alarm upon any flame/smoke detection",
    badgeColor: "#ef4444",
    badgeBg: "rgba(239, 68, 68, 0.18)",
    borderColor: "rgba(239, 68, 68, 0.4)",
    alertOnFire: true,
    alertOnSmoke: true,
  },
  "uc2-zone-welding": {
    id: "uc2-zone-welding",
    name: "Zone B — Welding & Fabrication Bay 4",
    use_case: "uc2",
    type: "deliberate_flame",
    typeLabel: "Controlled Flame (Deliberate)",
    description: "MIG/TIG welding workstations and oxy-acetylene torch cutting tables",
    policy: "Deliberate Flame Permitted: Controlled torches suppressed; alert only on rollout or heavy smoke",
    badgeColor: "#f59e0b",
    badgeBg: "rgba(245, 158, 11, 0.18)",
    borderColor: "rgba(245, 158, 11, 0.4)",
    alertOnFire: false,
    alertOnSmoke: true,
  },
  "uc2-zone-chemical": {
    id: "uc2-zone-chemical",
    name: "Zone C — Chemical Storage Warehouse",
    use_case: "uc2",
    type: "critical_hazard",
    typeLabel: "Extreme Hazard",
    description: "Volatile solvents, paints, lubricants, and flammable raw chemicals",
    policy: "High Hazard: Multi-stage HSV verification with instantaneous fire suppression trigger",
    badgeColor: "#ef4444",
    badgeBg: "rgba(239, 68, 68, 0.18)",
    borderColor: "rgba(239, 68, 68, 0.4)",
    alertOnFire: true,
    alertOnSmoke: true,
  },

  // UC3 Zones (PPE compliance)
  "uc3-zone-construction": {
    id: "uc3-zone-construction",
    name: "Zone A — Construction Sector A",
    use_case: "uc3",
    type: "mandatory_ppe",
    typeLabel: "Hardhat Mandate",
    description: "Structural renovation and heavy rigging area",
    policy: "Mandatory PPE: Hardhat & High-Visibility Vest required at all times (Zero tolerance)",
    badgeColor: "#06b6d4",
    badgeBg: "rgba(6, 182, 212, 0.18)",
    borderColor: "rgba(6, 182, 212, 0.4)",
  },
  "uc3-zone-dock": {
    id: "uc3-zone-dock",
    name: "Zone B — Freight Loading Dock",
    use_case: "uc3",
    type: "mandatory_ppe",
    typeLabel: "Vest & Boots Required",
    description: "Active forklift bays and freight trailer loading ramps",
    policy: "Mandatory PPE: Reflective Safety Jacket & Steel-Toe Boots required in forklift corridors",
    badgeColor: "#06b6d4",
    badgeBg: "rgba(6, 182, 212, 0.18)",
    borderColor: "rgba(6, 182, 212, 0.4)",
  },
  "uc3-zone-assembly": {
    id: "uc3-zone-assembly",
    name: "Zone C — Electronics Assembly Bay 3",
    use_case: "uc3",
    type: "mandatory_ppe",
    typeLabel: "Anti-Static & Eye Protection",
    description: "Precision component soldering and micro-circuit assembly cleanroom",
    policy: "Mandatory PPE: Eye Protection Goggles and Anti-Static Smocks required",
    badgeColor: "#06b6d4",
    badgeBg: "rgba(6, 182, 212, 0.18)",
    borderColor: "rgba(6, 182, 212, 0.4)",
  },

  // UC4 Zones (Traffic, ANPR & Speed)
  "uc4-zone-gate": {
    id: "uc4-zone-gate",
    name: "Zone A — Main Vehicle Gate B",
    use_case: "uc4",
    type: "access_control",
    typeLabel: "ANPR Ingress Lane",
    description: "Facility perimeter security barrier, inbound truck & car lanes",
    policy: "ANPR Access: Automated plate recognition against authorized whitelist; alert on unauthorized plates",
    badgeColor: "#14b8a6",
    badgeBg: "rgba(20, 184, 166, 0.18)",
    borderColor: "rgba(20, 184, 166, 0.4)",
  },
  "uc4-zone-speed": {
    id: "uc4-zone-speed",
    name: "Zone B — Perimeter Speed Lane",
    use_case: "uc4",
    type: "speed_enforcement",
    typeLabel: "Speed Enforcement (20 km/h)",
    description: "Internal perimeter access roadway connecting gate to warehouses",
    policy: "Speed Limit: 20 km/h. Radar + optical speed tracking with instant violation alerts",
    badgeColor: "#e11d48",
    badgeBg: "rgba(225, 29, 72, 0.18)",
    borderColor: "rgba(225, 29, 72, 0.4)",
  },
  "uc4-zone-yard": {
    id: "uc4-zone-yard",
    name: "Zone C — Logistics Yard & Staging",
    use_case: "uc4",
    type: "access_control",
    typeLabel: "Dwell-Time & Parking",
    description: "Heavy truck trailer parking bays and freight container depot",
    policy: "Unauthorized Parking & Dwell-Time Enforcement: Max 45 min idling limit",
    badgeColor: "#14b8a6",
    badgeBg: "rgba(20, 184, 166, 0.18)",
    borderColor: "rgba(20, 184, 166, 0.4)",
  },
};

/** All 12 operational zone cameras across the 4 integrated use cases. */
export const ZONE_CAMERAS: Camera[] = [
  // ── UC1: Worker Count & Presence ─────────────────────────────────────
  {
    id: "00000000-0000-0000-0000-000000000001",
    name: "Camera 1 — Main Lobby & Turnstile",
    location: "Zone A — Main Lobby & Turnstile",
    rtsp_url: "/app/test_data/videos/uc1.mp4",
    status: "online",
    use_cases: ["uc1"],
    fps: 10,
    zone_id: "uc1-zone-lobby",
    zone_name: "Zone A — Main Lobby & Turnstile",
    zone_type: "occupancy_flow",
    zone_policy: "Continuous Headcount & Ingress Flow Monitoring (Threshold: 50 persons)",
    demo_video: "/videos/uc1_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000102",
    name: "Camera 1B — Assembly Floor Line A",
    location: "Zone B — Assembly Floor Line A",
    rtsp_url: "/app/test_data/videos/uc1.mp4",
    status: "online",
    use_cases: ["uc1"],
    fps: 10,
    zone_id: "uc1-zone-assembly",
    zone_name: "Zone B — Assembly Floor Line A",
    zone_type: "occupancy_flow",
    zone_policy: "Occupancy Density Limit: Max 35 Operators across active stations",
    demo_video: "/videos/uc1_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000103",
    name: "Camera 1C — Server Room & Archives",
    location: "Zone C — Server Room & Archives",
    rtsp_url: "/app/test_data/videos/uc1.mp4",
    status: "online",
    use_cases: ["uc1"],
    fps: 10,
    zone_id: "uc1-zone-server",
    zone_name: "Zone C — Server Room & Archives",
    zone_type: "restricted_entry",
    zone_policy: "Strict Zero-Occupancy (Instant Intruder Alert)",
    demo_video: "/videos/uc1_demo.mp4",
  },

  // ── UC2: Fire, Smoke & Sparks Detection ──────────────────────────────
  {
    id: "00000000-0000-0000-0000-000000000002",
    name: "Camera 2 — Boiler Room West",
    location: "Zone A — Boiler Room West",
    rtsp_url: "/app/test_data/videos/uc2.mp4",
    status: "online",
    use_cases: ["uc2"],
    fps: 10,
    zone_id: "uc2-zone-boiler",
    zone_name: "Zone A — Boiler Room West",
    zone_type: "critical_hazard",
    zone_policy: "Critical Fire Danger: Zero-Tolerance. Immediate suppression alarm.",
    demo_video: "/videos/uc2_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000202",
    name: "Camera 2B — Welding & Torch Bay 4",
    location: "Zone B — Welding & Fabrication Bay 4",
    rtsp_url: "/app/test_data/videos/uc2.mp4",
    status: "online",
    use_cases: ["uc2"],
    fps: 10,
    zone_id: "uc2-zone-welding",
    zone_name: "Zone B — Welding & Fabrication Bay 4",
    zone_type: "deliberate_flame",
    zone_policy: "Deliberate Flame Permitted: Torches suppressed; alert on flame spread or toxic smoke.",
    demo_video: "/videos/uc2_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000203",
    name: "Camera 2C — Chemical Storage Warehouse",
    location: "Zone C — Chemical Storage Warehouse",
    rtsp_url: "/app/test_data/videos/uc2.mp4",
    status: "online",
    use_cases: ["uc2"],
    fps: 10,
    zone_id: "uc2-zone-chemical",
    zone_name: "Zone C — Chemical Storage Warehouse",
    zone_type: "critical_hazard",
    zone_policy: "Extreme Hazard: Multi-stage HSV verification with instant suppression trigger.",
    demo_video: "/videos/uc2_demo.mp4",
  },

  // ── UC3: PPE Safety Compliance ───────────────────────────────────────
  {
    id: "00000000-0000-0000-0000-000000000003",
    name: "Camera 3 — Construction Sector A",
    location: "Zone A — Construction Sector A",
    rtsp_url: "/app/test_data/videos/uc3.mp4",
    status: "online",
    use_cases: ["uc3"],
    fps: 10,
    zone_id: "uc3-zone-construction",
    zone_name: "Zone A — Construction Sector A",
    zone_type: "mandatory_ppe",
    zone_policy: "Mandatory PPE: Hardhat & High-Visibility Vest required 100% of time.",
    demo_video: "/videos/uc3_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000302",
    name: "Camera 3B — Freight Loading Dock",
    location: "Zone B — Freight Loading Dock",
    rtsp_url: "/app/test_data/videos/uc3.mp4",
    status: "online",
    use_cases: ["uc3"],
    fps: 10,
    zone_id: "uc3-zone-dock",
    zone_name: "Zone B — Freight Loading Dock",
    zone_type: "mandatory_ppe",
    zone_policy: "Mandatory PPE: Reflective Safety Jacket & Steel-Toe Boots required.",
    demo_video: "/videos/uc3_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000303",
    name: "Camera 3C — Electronics Assembly Bay 3",
    location: "Zone C — Electronics Assembly Bay 3",
    rtsp_url: "/app/test_data/videos/uc3.mp4",
    status: "online",
    use_cases: ["uc3"],
    fps: 10,
    zone_id: "uc3-zone-assembly",
    zone_name: "Zone C — Electronics Assembly Bay 3",
    zone_type: "mandatory_ppe",
    zone_policy: "Mandatory PPE: Anti-Static Smocks & Eye Protection Goggles required.",
    demo_video: "/videos/uc3_demo.mp4",
  },

  // ── UC4: Vehicle Access & Speed ──────────────────────────────────────
  {
    id: "00000000-0000-0000-0000-000000000004",
    name: "Camera 4 — Main Vehicle Gate B",
    location: "Zone A — Main Vehicle Gate B",
    rtsp_url: "/app/test_data/videos/uc4.mp4",
    status: "online",
    use_cases: ["uc4"],
    fps: 10,
    zone_id: "uc4-zone-gate",
    zone_name: "Zone A — Main Vehicle Gate B",
    zone_type: "access_control",
    zone_policy: "ANPR Access: Automated plate recognition against authorized whitelist.",
    demo_video: "/videos/uc4_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000402",
    name: "Camera 4B — Perimeter Speed Lane",
    location: "Zone B — Perimeter Speed Lane",
    rtsp_url: "/app/test_data/videos/uc4.mp4",
    status: "online",
    use_cases: ["uc4"],
    fps: 10,
    zone_id: "uc4-zone-speed",
    zone_name: "Zone B — Perimeter Speed Lane",
    zone_type: "speed_enforcement",
    zone_policy: "Speed Limit: 20 km/h. Radar + optical tracking alert on breach.",
    demo_video: "/videos/uc4_demo.mp4",
  },
  {
    id: "00000000-0000-0000-0000-000000000403",
    name: "Camera 4C — Logistics Yard & Staging",
    location: "Zone C — Logistics Yard & Staging",
    rtsp_url: "/app/test_data/videos/uc4.mp4",
    status: "online",
    use_cases: ["uc4"],
    fps: 10,
    zone_id: "uc4-zone-yard",
    zone_name: "Zone C — Logistics Yard & Staging",
    zone_type: "access_control",
    zone_policy: "Dwell-Time Monitoring: Max 45 min idling limit; unauthorized trailer alert.",
    demo_video: "/videos/uc4_demo.mp4",
  },
];