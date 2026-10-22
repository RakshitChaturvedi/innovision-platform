export type CameraStatus =
  | "online"
  | "offline"
  | "reconnecting"
  | "disabled";

export interface Camera {
  id: string;
  name: string;
  location?: string | null;
  rtsp_url: string | null;
  status: "online" | "offline" | "reconnecting" | "disabled";
  use_cases: string[];
  fps: number;
  organization_id?: string | null;
  site_id?: string | null;
  zone_id?: string | null;
  lifecycle_state?: string;
  source_type?: string;
}

export interface CameraCreatePayload {
  name: string;
  location?: string | null;
  rtsp_url: string;
  use_cases?: string[];
  fps?: number;
  organization_id?: string | null;
  site_id?: string | null;
  zone_id?: string | null;
  lifecycle_state?: string;
  source_type?: string;
}