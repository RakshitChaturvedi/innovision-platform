export type CameraStatus =
  | "online"
  | "offline"
  | "reconnecting"
  | "disabled";

export interface Camera {
  id: string;
  name: string;
  rtsp_url: string | null;
  status: CameraStatus;
  use_cases: string[];
  fps: number;
}