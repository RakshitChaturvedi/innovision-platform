import axios from "axios";

const UC2_BASE_URL =
  import.meta.env.VITE_UC2_STREAM_URL || "http://localhost:8030";

export interface DetectionItem {
  class_id: number;
  class_name: string;
  confidence: number;
  bbox: [number, number, number, number];
}

export interface ImageDetectionResponse {
  success: boolean;
  detections: DetectionItem[];
  annotated_image_base64: string | null;
  detection_count: number;
  has_alert: boolean;
  timestamp: string;
  error?: string;
}

export interface VideoTimelineFrame {
  frame_index: number;
  timestamp_seconds: number;
  detections: DetectionItem[];
}

export interface VideoDetectionResponse {
  success: boolean;
  processed_frames: number;
  total_detections: number;
  timeline: VideoTimelineFrame[];
  annotated_snapshot_base64: string | null;
  timestamp: string;
  error?: string;
}

export interface RtspConnectResponse {
  success: boolean;
  status: string;
  rtsp_url: string;
  error?: string;
}

export interface RtspStatusResponse {
  status: "idle" | "running" | "stopped" | "error";
  rtsp_url: string | null;
  fps: number;
  frame_count: number;
  latest_detections: DetectionItem[];
  latest_confidence: number;
  alert_status: "ALERT" | "CLEAR";
  error: string | null;
}

export interface DetectionModuleStatus {
  service: string;
  model: string;
  classes: Record<string, string>;
  status: string;
}

export async function getDetectionStatus(): Promise<DetectionModuleStatus> {
  const res = await axios.get<DetectionModuleStatus>(
    `${UC2_BASE_URL}/detection/status`,
    { timeout: 5000 }
  );
  return res.data;
}

export async function detectImage(file: File): Promise<ImageDetectionResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await axios.post<ImageDetectionResponse>(
    `${UC2_BASE_URL}/detection/image`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 30000,
    }
  );
  return res.data;
}

export async function detectVideo(
  file: File,
  sampleRate: number = 5
): Promise<VideoDetectionResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await axios.post<VideoDetectionResponse>(
    `${UC2_BASE_URL}/detection/video?sample_rate=${sampleRate}`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 60000,
    }
  );
  return res.data;
}

export async function connectRtsp(
  rtspUrl: string,
  sampleInterval: number = 2
): Promise<RtspConnectResponse> {
  const res = await axios.post<RtspConnectResponse>(
    `${UC2_BASE_URL}/detection/rtsp`,
    {
      rtsp_url: rtspUrl,
      sample_interval: sampleInterval,
    },
    { timeout: 10000 }
  );
  return res.data;
}

export async function stopRtsp(): Promise<{ success: boolean; status: string }> {
  const res = await axios.post<{ success: boolean; status: string }>(
    `${UC2_BASE_URL}/detection/rtsp/stop`,
    {},
    { timeout: 5000 }
  );
  return res.data;
}

export async function getRtspStatus(): Promise<RtspStatusResponse> {
  const res = await axios.get<RtspStatusResponse>(
    `${UC2_BASE_URL}/detection/rtsp/status`,
    { timeout: 5000 }
  );
  return res.data;
}
