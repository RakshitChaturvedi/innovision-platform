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
}