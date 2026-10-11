import axios, { type InternalAxiosRequestConfig } from "axios";

const attachAuthToken = (config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("innovision_access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
};

export const authClient = axios.create({
  baseURL: import.meta.env.VITE_AUTH_API_URL,
  withCredentials: true,
});

export const cameraClient = axios.create({
  baseURL: import.meta.env.VITE_CAMERA_API_URL,
});

export const alertClient = axios.create({
  baseURL: import.meta.env.VITE_ALERTS_API_URL,
});

export const incidentClient = axios.create({
  baseURL: import.meta.env.VITE_INCIDENTS_API_URL || "http://localhost:8000",
});

export const reportsClient = axios.create({
  baseURL: import.meta.env.VITE_REPORTS_API_URL || "http://localhost:8000",
});

export const auditClient = axios.create({
  baseURL: import.meta.env.VITE_AUDIT_API_URL || "http://localhost:8000",
});

export const settingsClient = axios.create({
  baseURL: import.meta.env.VITE_SETTINGS_API_URL || "http://localhost:8000",
});

export const notificationClient = axios.create({
  baseURL: import.meta.env.VITE_NOTIFICATION_API_URL || "http://localhost:8000",
});

authClient.interceptors.request.use(attachAuthToken);
cameraClient.interceptors.request.use(attachAuthToken);
alertClient.interceptors.request.use(attachAuthToken);
incidentClient.interceptors.request.use(attachAuthToken);
reportsClient.interceptors.request.use(attachAuthToken);
auditClient.interceptors.request.use(attachAuthToken);
settingsClient.interceptors.request.use(attachAuthToken);
notificationClient.interceptors.request.use(attachAuthToken);

export const apiClient = authClient;