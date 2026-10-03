import axios from "axios";
import { buildDetectionsUrl } from "@/lib/overlay";

// Dedicated client for the detections endpoint.
// Proxied via Vite dev server: /<useCase> → http://localhost:8030 (or configured UC endpoint).
const uc3Client = axios.create({
  baseURL: import.meta.env.VITE_UC3_API_URL ?? "",
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
  timestamp?: string;
  [key: string]: unknown;
}

export async function getLatestDetections(
  cameraId: string,
  useCase: string = "uc3",
): Promise<LatestDetectionsResponse> {
  const url = buildDetectionsUrl(cameraId, useCase);
  const { data } = await uc3Client.get<LatestDetectionsResponse>(url);
  return data;
}
