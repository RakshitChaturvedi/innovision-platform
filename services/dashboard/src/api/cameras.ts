import { cameraClient } from "./client";
import type { Camera } from "@/types/camera";

export async function getCameras(): Promise<Camera[]> {
  const { data } = await cameraClient.get<Camera[]>("/cameras");
  return data;
}

export async function getCameraStatus(
  cameraId: string,
): Promise<Camera["status"]> {
  const { data } = await cameraClient.get<{
    status: Camera["status"];
  }>(`/cameras/${cameraId}/status`);

  return data.status;
}

export interface VideoSession {
  session_id: string;
  camera_id: string;
  organization_id?: string;
  original_filename: string;
  storage_path: string;
  file_size_bytes: number;
  status: "uploaded" | "queued" | "processing" | "completed" | "stopped" | "failed";
  fps: number;
  total_frames: number;
  processed_frames: number;
  error_message?: string;
  effective_analytics: string[];
  created_at: string;
  updated_at: string;
}

export interface VideoSessionProcessResponse {
  session_id: string;
  camera_id: string;
  status: string;
  message: string;
  effective_analytics: string[];
}

export async function uploadCameraVideo(
  cameraId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<VideoSession> {
  const { data } = await cameraClient.post<VideoSession>(
    `/cameras/${cameraId}/upload-video?filename=${encodeURIComponent(file.name)}`,
    file,
    {
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": file.name,
      },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          onProgress(Math.round((progressEvent.loaded * 100) / progressEvent.total));
        }
      },
    },
  );
  return data;
}

export async function createCameraVideoSessionFromTestFile(
  cameraId: string,
  filename: string,
): Promise<VideoSession> {
  const { data } = await cameraClient.post<VideoSession>(
    `/cameras/${cameraId}/upload-video`,
    { filename },
  );
  return data;
}

export async function getCameraVideoSessions(
  cameraId: string,
): Promise<VideoSession[]> {
  const { data } = await cameraClient.get<VideoSession[]>(
    `/cameras/${cameraId}/video-sessions`,
  );
  return data;
}

export async function getCameraVideoSession(
  cameraId: string,
  sessionId: string,
): Promise<VideoSession> {
  const { data } = await cameraClient.get<VideoSession>(
    `/cameras/${cameraId}/video-sessions/${sessionId}`,
  );
  return data;
}

export async function processCameraVideoSession(
  cameraId: string,
  sessionId: string,
): Promise<VideoSessionProcessResponse> {
  const { data } = await cameraClient.post<VideoSessionProcessResponse>(
    `/cameras/${cameraId}/video-sessions/${sessionId}/process`,
  );
  return data;
}

export async function stopCameraVideoSession(
  cameraId: string,
  sessionId: string,
): Promise<VideoSessionProcessResponse> {
  const { data } = await cameraClient.post<VideoSessionProcessResponse>(
    `/cameras/${cameraId}/video-sessions/${sessionId}/stop`,
  );
  return data;
}

export interface PipelineDetection {
  label: string;
  confidence: number;
  bbox?: number[];
  box?: number[];
  tracking_id?: number | string;
  zone_id?: string;
  [key: string]: unknown;
}

export interface UC1ImageResult {
  status: string;
  detections: PipelineDetection[];
  person_count?: number;
  intrusion_count?: number;
  error?: string;
}

export interface UC2ImageResult {
  status: string;
  detections: PipelineDetection[];
  candidate_count?: number;
  verified_count?: number;
  error?: string;
}

export interface UC3ImageResult {
  status: string;
  detections: PipelineDetection[];
  compliant_count?: number;
  violation_count?: number;
  error?: string;
}

export interface UC4ImageResult {
  status: string;
  detections: PipelineDetection[];
  vehicle_count?: number;
  plates_detected?: Array<{ text: string; confidence: number; bbox: number[] }>;
  temporal_tracking_available?: boolean;
  speed_kmh?: number;
  error?: string;
}

export interface MultiPipelineImageInferenceResponse {
  status: string;
  camera_id: string;
  timestamp: string;
  source_type: string;
  resolution: string;
  frame_reference?: string;
  results: {
    uc1?: UC1ImageResult;
    uc2?: UC2ImageResult;
    uc3?: UC3ImageResult;
    uc4?: UC4ImageResult;
  };
}

export async function inferCameraImage(
  cameraId: string,
  file: File,
): Promise<MultiPipelineImageInferenceResponse> {
  const { data } = await cameraClient.post<MultiPipelineImageInferenceResponse>(
    `/cameras/${cameraId}/infer-image`,
    file,
    {
      headers: {
        "Content-Type": "application/octet-stream",
        "X-Filename": file.name,
      },
    },
  );
  return data;
}