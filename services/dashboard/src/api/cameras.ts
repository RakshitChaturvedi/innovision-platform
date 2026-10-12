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