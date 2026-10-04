import axios from "axios";

// Dedicated client for UC3 detections endpoint
const uc3Client = axios.create({
  baseURL: import.meta.env.VITE_UC3_API_URL || "http://localhost:8031",
});

export interface Detection {
  label: string;
  color: string;
  bbox: {
    x1: number; // normalized 0-1
    y1: number;
    x2: number;
    y2: number;
  };
  [key: string]: unknown;
}

export interface LatestDetectionsResponse {
  camera_id: string;
  detections: Detection[];
  [key: string]: unknown;
}

export async function getLatestDetections(
  cameraId: string,
): Promise<LatestDetectionsResponse> {
  const { data } = await uc3Client.get<LatestDetectionsResponse>(
    `/uc3/cameras/${cameraId}/latest-detections`,
  );
  return data;
}
