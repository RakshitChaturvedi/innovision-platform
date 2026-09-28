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

export interface CreateCameraPayload {
  name: string;
  location?: string;
  rtsp_url: string;
  use_cases: string[];
  fps: number;
}

export interface UpdateCameraConfigPayload {
  use_cases?: string[];
  fps?: number;
}

export async function createCamera(
  payload: CreateCameraPayload,
): Promise<Camera> {
  const { data } = await cameraClient.post<Camera>("/cameras", payload);
  return data;
}

export async function updateCameraConfig(
  cameraId: string,
  payload: UpdateCameraConfigPayload,
): Promise<void> {
  await cameraClient.put(`/cameras/${cameraId}/config`, payload);
}

export async function deleteCamera(cameraId: string): Promise<void> {
  await cameraClient.delete(`/cameras/${cameraId}`);
}