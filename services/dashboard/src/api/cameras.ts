import { cameraClient } from "./client";
import { ZONE_CAMERAS, type Camera } from "@/types/camera";

export interface CamerasResult {
  cameras: Camera[];
  isDemoFallback: boolean;
}

/**
 * Fetches all cameras with fallback detection.
 */
export async function getCamerasResult(): Promise<CamerasResult> {
  try {
    const { data } = await cameraClient.get<Camera[]>("/cameras");
    if (!Array.isArray(data) || data.length === 0) {
      return {
        cameras: ZONE_CAMERAS,
        isDemoFallback: true,
      };
    }

    // Index backend cameras by ID for quick status & url lookup
    const backendMap = new Map<string, Camera>();
    for (const cam of data) {
      backendMap.set(cam.id, cam);
    }

    // Merge backend live data with the full zone topology
    const mergedList: Camera[] = ZONE_CAMERAS.map((zoneCam) => {
      const live = backendMap.get(zoneCam.id);
      if (live) {
        return {
          ...zoneCam,
          status: live.status || zoneCam.status,
          fps: live.fps || zoneCam.fps,
          rtsp_url: live.rtsp_url || zoneCam.rtsp_url,
        };
      }
      return zoneCam;
    });

    // Also include any custom cameras created in the backend not in the seed catalog
    for (const cam of data) {
      if (!ZONE_CAMERAS.some((zc) => zc.id === cam.id)) {
        mergedList.push(cam);
      }
    }

    return {
      cameras: mergedList,
      isDemoFallback: false,
    };
  } catch {
    // Graceful fallback to zone cameras catalog during dev or offline mode
    return {
      cameras: ZONE_CAMERAS,
      isDemoFallback: true,
    };
  }
}

/**
 * Fetches all cameras (returns Camera[] for backward compatibility).
 */
export async function getCameras(): Promise<Camera[]> {
  const result = await getCamerasResult();
  return result.cameras;
}

export async function getCameraStatus(
  cameraId: string,
): Promise<Camera["status"]> {
  try {
    const { data } = await cameraClient.get<{
      status: Camera["status"];
    }>(`/cameras/${cameraId}/status`);
    return data.status;
  } catch {
    const found = ZONE_CAMERAS.find((c) => c.id === cameraId);
    return found ? found.status : "online";
  }
}