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