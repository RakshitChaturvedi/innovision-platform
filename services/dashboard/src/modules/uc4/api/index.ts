import { uc4Client } from "@/api/client";
import { getCameras } from "@/api/cameras";
import type {
  UC4Camera,
  UC4CameraCalibration,
  VehicleEvent,
  WatchlistEntry,
  TrackingResult,
  AnalyticsData,
} from "../types";

const UC4_BASE_URL =
  import.meta.env.VITE_UC4_API_URL || "http://localhost:8024";

// Local state for standalone demo mode
const localCalibrations: Record<string, UC4CameraCalibration> = {
  "00000000-0000-0000-0000-000000000004": {
    camera_id: "00000000-0000-0000-0000-000000000004",
    speed_polygon_normalized: [
      { x: 0.15, y: 0.45 },
      { x: 0.85, y: 0.45 },
      { x: 0.90, y: 0.85 },
      { x: 0.10, y: 0.85 },
    ],
    distance_between_lines_meters: 18.5,
    entry_line: { x1: 0.18, y1: 0.50, x2: 0.82, y2: 0.50 },
    exit_line: { x1: 0.12, y1: 0.80, x2: 0.88, y2: 0.80 },
    calibration_polygon_normalized: [
      { x: 0.25, y: 0.55 },
      { x: 0.75, y: 0.55 },
      { x: 0.75, y: 0.75 },
      { x: 0.25, y: 0.75 },
    ],
    speed_limit_kmh: 20,
    updated_at: new Date().toISOString(),
  },
  "00000000-0000-0000-0000-000000000402": {
    camera_id: "00000000-0000-0000-0000-000000000402",
    speed_polygon_normalized: [
      { x: 0.20, y: 0.40 },
      { x: 0.80, y: 0.40 },
      { x: 0.85, y: 0.90 },
      { x: 0.15, y: 0.90 },
    ],
    distance_between_lines_meters: 25.0,
    entry_line: { x1: 0.22, y1: 0.45, x2: 0.78, y2: 0.45 },
    exit_line: { x1: 0.16, y1: 0.85, x2: 0.84, y2: 0.85 },
    speed_limit_kmh: 20,
    updated_at: new Date().toISOString(),
  },
  "00000000-0000-0000-0000-000000000403": {
    camera_id: "00000000-0000-0000-0000-000000000403",
    speed_polygon_normalized: [
      { x: 0.12, y: 0.38 },
      { x: 0.88, y: 0.38 },
      { x: 0.92, y: 0.82 },
      { x: 0.08, y: 0.82 },
    ],
    distance_between_lines_meters: 20.0,
    entry_line: { x1: 0.15, y1: 0.42, x2: 0.85, y2: 0.42 },
    exit_line: { x1: 0.10, y1: 0.78, x2: 0.90, y2: 0.78 },
    speed_limit_kmh: 15,
    updated_at: new Date().toISOString(),
  },
};

const SEED_UC4_CAMERAS: UC4Camera[] = [
  {
    id: "00000000-0000-0000-0000-000000000004",
    name: "Camera 4 — Main Vehicle Gate B",
    location: "Main Vehicle Gate B",
    video_source: "/videos/uc4_demo.mp4",
    status: "online",
    fps: 25,
    latitude: 17.5385,
    longitude: 78.3848,
    speed_limit_kmh: 20,
    entry_line: localCalibrations["00000000-0000-0000-0000-000000000004"].entry_line,
    exit_line: localCalibrations["00000000-0000-0000-0000-000000000004"].exit_line,
    speed_polygon_normalized: localCalibrations["00000000-0000-0000-0000-000000000004"].speed_polygon_normalized,
    calibration_polygon_normalized: localCalibrations["00000000-0000-0000-0000-000000000004"].calibration_polygon_normalized,
    distance_between_lines_meters: 18.5,
  },
  {
    id: "00000000-0000-0000-0000-000000000402",
    name: "Camera 4B — Perimeter Speed Lane",
    location: "North Perimeter Road",
    video_source: "/videos/uc4_demo.mp4",
    status: "online",
    fps: 25,
    latitude: 17.5402,
    longitude: 78.3865,
    speed_limit_kmh: 20,
    entry_line: localCalibrations["00000000-0000-0000-0000-000000000402"].entry_line,
    exit_line: localCalibrations["00000000-0000-0000-0000-000000000402"].exit_line,
    speed_polygon_normalized: localCalibrations["00000000-0000-0000-0000-000000000402"].speed_polygon_normalized,
    distance_between_lines_meters: 25.0,
  },
  {
    id: "00000000-0000-0000-0000-000000000403",
    name: "Camera 4C — Logistics Yard & Staging",
    location: "Warehouse Logistics Bay",
    video_source: "/videos/uc4_demo.mp4",
    status: "online",
    fps: 25,
    latitude: 17.5372,
    longitude: 78.3878,
    speed_limit_kmh: 15,
    entry_line: localCalibrations["00000000-0000-0000-0000-000000000403"].entry_line,
    exit_line: localCalibrations["00000000-0000-0000-0000-000000000403"].exit_line,
    speed_polygon_normalized: localCalibrations["00000000-0000-0000-0000-000000000403"].speed_polygon_normalized,
    distance_between_lines_meters: 20.0,
  },
];

const SEED_EVENTS: VehicleEvent[] = [
  {
    event_id: "ev-101",
    camera_id: "00000000-0000-0000-0000-000000000004",
    camera_name: "Camera 4 — Main Vehicle Gate B",
    license_plate: "KA01MJ4921",
    ocr_confidence: 96,
    vehicle_type: "car",
    vehicle_color: "white",
    entry_time: new Date(Date.now() - 4 * 60 * 1000).toISOString(),
    speed_kmh: 18.5,
    is_violation: false,
  },
  {
    event_id: "ev-102",
    camera_id: "00000000-0000-0000-0000-000000000402",
    camera_name: "Camera 4B — Perimeter Speed Lane",
    license_plate: "KA01MJ4921",
    ocr_confidence: 94,
    vehicle_type: "car",
    vehicle_color: "white",
    entry_time: new Date(Date.now() - 1 * 60 * 1000).toISOString(),
    speed_kmh: 38.2,
    is_violation: true,
  },
  {
    event_id: "ev-103",
    camera_id: "00000000-0000-0000-0000-000000000004",
    camera_name: "Camera 4 — Main Vehicle Gate B",
    license_plate: "DL08CA2020",
    ocr_confidence: 98,
    vehicle_type: "truck",
    vehicle_color: "yellow",
    entry_time: new Date(Date.now() - 28 * 60 * 1000).toISOString(),
    speed_kmh: 14.0,
    is_violation: true,
  },
  {
    event_id: "ev-104",
    camera_id: "00000000-0000-0000-0000-000000000403",
    camera_name: "Camera 4C — Logistics Yard & Staging",
    license_plate: "MH12DE1433",
    ocr_confidence: 92,
    vehicle_type: "suv",
    vehicle_color: "black",
    entry_time: new Date(Date.now() - 45 * 60 * 1000).toISOString(),
    speed_kmh: 16.8,
    is_violation: false,
  },
  {
    event_id: "ev-105",
    camera_id: "00000000-0000-0000-0000-000000000004",
    camera_name: "Camera 4 — Main Vehicle Gate B",
    license_plate: "TS09FA8811",
    ocr_confidence: 95,
    vehicle_type: "motorcycle",
    vehicle_color: "red",
    entry_time: new Date(Date.now() - 75 * 60 * 1000).toISOString(),
    speed_kmh: 22.0,
    is_violation: true,
  },
  {
    event_id: "ev-106",
    camera_id: "00000000-0000-0000-0000-000000000402",
    camera_name: "Camera 4B — Perimeter Speed Lane",
    license_plate: "HR26DK8392",
    ocr_confidence: 91,
    vehicle_type: "bus",
    vehicle_color: "blue",
    entry_time: new Date(Date.now() - 90 * 60 * 1000).toISOString(),
    speed_kmh: 19.4,
    is_violation: false,
  },
  {
    event_id: "ev-107",
    camera_id: "00000000-0000-0000-0000-000000000403",
    camera_name: "Camera 4C — Logistics Yard & Staging",
    license_plate: "KA01MJ4921",
    ocr_confidence: 97,
    vehicle_type: "car",
    vehicle_color: "white",
    entry_time: new Date(Date.now() - 110 * 60 * 1000).toISOString(),
    speed_kmh: 12.5,
    is_violation: false,
  },
];

const SEED_WATCHLIST: WatchlistEntry[] = [
  { plate: "DL08CA2020", reason: "Flagged unauthorized cargo transport", severity: "CRITICAL" },
  { plate: "HR26DK8392", reason: "Suspended contractor vehicle", severity: "HIGH" },
  { plate: "UP16BT9911", reason: "Security incident reported", severity: "MEDIUM" },
];

export async function getUC4Cameras(): Promise<UC4Camera[]> {
  try {
    const allCameras = await getCameras();
    const uc4Cameras = allCameras.filter((c) =>
      c.use_cases.some((u) => u.toLowerCase() === "uc4"),
    );

    if (uc4Cameras.length > 0) {
      return uc4Cameras.map((c, index) => {
        const cal = localCalibrations[c.id];
        const seedCoord = SEED_UC4_CAMERAS[index % SEED_UC4_CAMERAS.length];
        return {
          id: c.id,
          name: c.name,
          location: c.zone_name || c.location || "UC4 Perimeter Lane",
          video_source: c.demo_video || "/videos/uc4_demo.mp4",
          status: c.status,
          fps: c.fps,
          latitude: seedCoord.latitude,
          longitude: seedCoord.longitude,
          speed_limit_kmh: cal?.speed_limit_kmh ?? 20,
          entry_line: cal?.entry_line ?? null,
          exit_line: cal?.exit_line ?? null,
          speed_polygon_normalized: cal?.speed_polygon_normalized ?? null,
          calibration_polygon_normalized: cal?.calibration_polygon_normalized ?? null,
          distance_between_lines_meters: cal?.distance_between_lines_meters ?? 15,
        };
      });
    }
  } catch {
    // Offline fallback
  }

  return SEED_UC4_CAMERAS;
}

export async function getCameraCalibration(
  cameraId: string,
): Promise<UC4CameraCalibration | null> {
  try {
    const { data } = await uc4Client.get<UC4CameraCalibration>(
      `/uc4/cameras/${cameraId}/calibration`,
    );
    if (data) return data;
  } catch {
    // Offline demo fallback
  }

  return localCalibrations[cameraId] ?? null;
}

export async function saveCameraCalibration(
  cameraId: string,
  payload: Partial<UC4CameraCalibration>,
): Promise<{ status: string; message: string }> {
  try {
    const { data } = await uc4Client.put<{ status: string; message: string }>(
      `/uc4/cameras/${cameraId}/calibration`,
      payload,
    );
    return data;
  } catch {
    // Save to local cache in standalone dev
    localCalibrations[cameraId] = {
      camera_id: cameraId,
      speed_polygon_normalized: payload.speed_polygon_normalized ?? null,
      distance_between_lines_meters: payload.distance_between_lines_meters ?? 15,
      entry_line: payload.entry_line ?? null,
      exit_line: payload.exit_line ?? null,
      calibration_polygon_normalized: payload.calibration_polygon_normalized ?? null,
      speed_limit_kmh: payload.speed_limit_kmh ?? 20,
      updated_at: new Date().toISOString(),
    };
    return { status: "success", message: "Calibration saved successfully" };
  }
}

export function getCameraPreviewFrameUrl(cameraId: string): string {
  return `${UC4_BASE_URL}/uc4/cameras/${cameraId}/latest-frame?t=${Date.now()}`;
}

export async function uploadCameraVideo(
  cameraId: string,
  file: File,
): Promise<{ status: string; message: string }> {
  try {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await uc4Client.post<{ status: string; message: string }>(
      `/uc4/cameras/${cameraId}/upload`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return data;
  } catch {
    return { status: "success", message: `Video ${file.name} uploaded to ${cameraId}` };
  }
}

export async function getVehicleEvents(): Promise<VehicleEvent[]> {
  try {
    const { data } = await uc4Client.get<VehicleEvent[]>("/uc4/events");
    if (Array.isArray(data) && data.length > 0) return data;
  } catch {
    // Offline demo fallback
  }
  return SEED_EVENTS;
}

export async function searchVehiclePlate(plate: string): Promise<VehicleEvent[]> {
  const query = plate.trim().toUpperCase();
  if (!query) return [];

  try {
    const { data } = await uc4Client.get<VehicleEvent[]>(
      `/uc4/tracking/search?plate=${encodeURIComponent(query)}`,
    );
    if (Array.isArray(data) && data.length > 0) return data;
  } catch {
    // Offline demo search
  }

  return SEED_EVENTS.filter((e) =>
    e.license_plate.toUpperCase().includes(query),
  ).sort(
    (a, b) => new Date(a.entry_time).getTime() - new Date(b.entry_time).getTime(),
  );
}

export async function getTrackingJourney(plate: string): Promise<TrackingResult> {
  const events = await searchVehiclePlate(plate);
  const cameras = await getUC4Cameras();
  const cameraMap = new Map(cameras.map((c) => [c.id, c]));

  const nodes = events.map((event) => {
    const camera = cameraMap.get(event.camera_id) || {
      id: event.camera_id,
      name: event.camera_name || `Camera ${event.camera_id.slice(-4)}`,
      location: "Campus Perimeter",
      status: "online" as const,
      latitude: 17.5385,
      longitude: 78.3848,
    };
    return { event, camera };
  });

  const routePath = nodes.map((node) => ({
    lat: node.camera.latitude ?? 17.5385,
    lng: node.camera.longitude ?? 78.3848,
    camera_id: node.camera.id,
    location_name: node.camera.location || node.camera.name,
    timestamp: node.event.entry_time,
  }));

  const lastSeen = nodes.length > 0 ? nodes[nodes.length - 1] : null;

  return { nodes, routePath, lastSeen };
}

export async function getWatchlist(): Promise<WatchlistEntry[]> {
  try {
    const { data } = await uc4Client.get<WatchlistEntry[]>("/uc4/watchlist");
    if (Array.isArray(data) && data.length > 0) return data;
  } catch {
    // Offline demo fallback
  }
  return SEED_WATCHLIST;
}

export async function getAnalytics(
  timeframe: "day" | "week" | "month" = "day",
): Promise<AnalyticsData> {
  try {
    const { data } = await uc4Client.get<AnalyticsData>(
      `/uc4/analytics?timeframe=${timeframe}`,
    );
    if (data) return data;
  } catch {
    // Offline demo analytics
  }

  if (timeframe === "day") {
    return {
      trafficVolume: [
        { name: "00:00", count: 12 },
        { name: "03:00", count: 6 },
        { name: "06:00", count: 28 },
        { name: "09:00", count: 94 },
        { name: "12:00", count: 112 },
        { name: "15:00", count: 86 },
        { name: "18:00", count: 124 },
        { name: "21:00", count: 54 },
      ],
      vehicleComposition: [
        { name: "Cars & Sedans", value: 342, color: "#0D9488" },
        { name: "Commercial Trucks", value: 128, color: "#F59E0B" },
        { name: "SUVs & Vans", value: 164, color: "#3B82F6" },
        { name: "Motorcycles", value: 89, color: "#8B5CF6" },
        { name: "Buses", value: 32, color: "#10B981" },
      ],
      violationDensity: [
        { name: "Gate B", speeding: 18, unauthorized: 4, redLight: 2 },
        { name: "North Lane", speeding: 34, unauthorized: 1, redLight: 0 },
        { name: "Logistics Bay", speeding: 8, unauthorized: 9, redLight: 3 },
        { name: "Perimeter Road", speeding: 22, unauthorized: 2, redLight: 1 },
      ],
      cameraAlerts: [
        { name: "Camera 4B (Perimeter Lane)", count: 42 },
        { name: "Camera 4 (Gate B Entry)", count: 26 },
        { name: "Camera 4C (Logistics Yard)", count: 19 },
        { name: "Camera 4D (Depot Exit)", count: 11 },
      ],
    };
  } else if (timeframe === "week") {
    return {
      trafficVolume: [
        { name: "Mon", count: 640 },
        { name: "Tue", count: 710 },
        { name: "Wed", count: 680 },
        { name: "Thu", count: 790 },
        { name: "Fri", count: 850 },
        { name: "Sat", count: 420 },
        { name: "Sun", count: 310 },
      ],
      vehicleComposition: [
        { name: "Cars & Sedans", value: 2450, color: "#0D9488" },
        { name: "Commercial Trucks", value: 920, color: "#F59E0B" },
        { name: "SUVs & Vans", value: 1180, color: "#3B82F6" },
        { name: "Motorcycles", value: 640, color: "#8B5CF6" },
        { name: "Buses", value: 210, color: "#10B981" },
      ],
      violationDensity: [
        { name: "Gate B", speeding: 95, unauthorized: 21, redLight: 8 },
        { name: "North Lane", speeding: 182, unauthorized: 9, redLight: 2 },
        { name: "Logistics Bay", speeding: 48, unauthorized: 38, redLight: 14 },
        { name: "Perimeter Road", speeding: 124, unauthorized: 12, redLight: 5 },
      ],
      cameraAlerts: [
        { name: "Camera 4B (Perimeter Lane)", count: 210 },
        { name: "Camera 4 (Gate B Entry)", count: 142 },
        { name: "Camera 4C (Logistics Yard)", count: 98 },
        { name: "Camera 4D (Depot Exit)", count: 64 },
      ],
    };
  } else {
    return {
      trafficVolume: [
        { name: "Week 1", count: 4200 },
        { name: "Week 2", count: 4650 },
        { name: "Week 3", count: 4890 },
        { name: "Week 4", count: 5120 },
      ],
      vehicleComposition: [
        { name: "Cars & Sedans", value: 10200, color: "#0D9488" },
        { name: "Commercial Trucks", value: 3850, color: "#F59E0B" },
        { name: "SUVs & Vans", value: 4920, color: "#3B82F6" },
        { name: "Motorcycles", value: 2680, color: "#8B5CF6" },
        { name: "Buses", value: 890, color: "#10B981" },
      ],
      violationDensity: [
        { name: "Gate B", speeding: 410, unauthorized: 88, redLight: 34 },
        { name: "North Lane", speeding: 760, unauthorized: 36, redLight: 8 },
        { name: "Logistics Bay", speeding: 198, unauthorized: 152, redLight: 52 },
        { name: "Perimeter Road", speeding: 512, unauthorized: 48, redLight: 20 },
      ],
      cameraAlerts: [
        { name: "Camera 4B (Perimeter Lane)", count: 880 },
        { name: "Camera 4 (Gate B Entry)", count: 590 },
        { name: "Camera 4C (Logistics Yard)", count: 412 },
        { name: "Camera 4D (Depot Exit)", count: 280 },
      ],
    };
  }
}
