export interface NormalizedLine {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface NormalizedPoint {
  x: number;
  y: number;
}

export interface UC4CameraCalibration {
  camera_id: string;
  speed_polygon_normalized: NormalizedPoint[] | null;
  distance_between_lines_meters: number;
  entry_line: NormalizedLine | null;
  exit_line: NormalizedLine | null;
  calibration_polygon_normalized?: NormalizedPoint[] | null;
  speed_limit_kmh?: number;
  updated_at?: string;
}

export interface UC4Camera {
  id: string;
  name: string;
  location?: string;
  video_source?: string;
  status: "online" | "offline" | "reconnecting" | "disabled";
  fps?: number;
  latitude?: number;
  longitude?: number;
  speed_limit_kmh?: number;
  entry_line?: NormalizedLine | null;
  exit_line?: NormalizedLine | null;
  speed_polygon_normalized?: NormalizedPoint[] | null;
  calibration_polygon_normalized?: NormalizedPoint[] | null;
  distance_between_lines_meters?: number | null;
}

export interface VehicleEvent {
  event_id: string;
  camera_id: string;
  camera_name?: string;
  license_plate: string;
  ocr_confidence: number;
  vehicle_type: string;
  vehicle_color: string;
  entry_time: string;
  exit_time?: string;
  speed_kmh?: number;
  is_violation: boolean;
  alert_id?: string | null;
}

export interface UC4Violation {
  violation_id: string;
  event_id: string;
  license_plate: string;
  violation_type: "SPEEDING" | "UNAUTHORIZED_ENTRY" | "RED_LIGHT" | "BLACKLISTED";
  recorded_value: number;
  zone_limit: number;
  severity_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  status: "UNRESOLVED" | "ACKNOWLEDGED" | "ESCALATED" | "RESOLVED";
  created_at: string;
}

export interface WatchlistEntry {
  plate: string;
  reason: string;
  severity: "MEDIUM" | "HIGH" | "CRITICAL";
  added_at?: string;
}

export interface TrackingNode {
  event: VehicleEvent;
  camera: UC4Camera;
}

export interface TrackingRoutePoint {
  lat: number;
  lng: number;
  camera_id: string;
  location_name: string;
  timestamp: string;
}

export interface TrackingResult {
  nodes: TrackingNode[];
  routePath: TrackingRoutePoint[];
  lastSeen: TrackingNode | null;
}

export interface TrafficVolumePoint {
  name: string;
  count: number;
}

export interface VehicleCompositionPoint {
  name: string;
  value: number;
  color: string;
}

export interface ViolationDensityPoint {
  name: string;
  speeding: number;
  unauthorized: number;
  redLight: number;
}

export interface CameraAlertPoint {
  name: string;
  count: number;
}

export interface AnalyticsData {
  trafficVolume: TrafficVolumePoint[];
  vehicleComposition: VehicleCompositionPoint[];
  violationDensity: ViolationDensityPoint[];
  cameraAlerts: CameraAlertPoint[];
}
