import axios, { type InternalAxiosRequestConfig } from "axios";

const attachAuthToken = (config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("innovision_access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
};

export const authClient = axios.create({
  baseURL: import.meta.env.VITE_AUTH_API_URL || "/api/auth",
  withCredentials: true,
});

export const cameraClient = axios.create({
  baseURL: import.meta.env.VITE_CAMERA_API_URL || "/api/cameras",
});

export const alertClient = axios.create({
  baseURL: import.meta.env.VITE_ALERTS_API_URL || "/api/alerts",
});

export const incidentClient = axios.create({
  baseURL: import.meta.env.VITE_INCIDENTS_API_URL || "/api/incidents",
});

export const uc4Client = axios.create({
  baseURL: import.meta.env.VITE_UC4_API_URL || "/api/uc4",
});

authClient.interceptors.request.use(attachAuthToken);
cameraClient.interceptors.request.use(attachAuthToken);
alertClient.interceptors.request.use(attachAuthToken);
incidentClient.interceptors.request.use(attachAuthToken);
uc4Client.interceptors.request.use(attachAuthToken);

export const apiClient = authClient;