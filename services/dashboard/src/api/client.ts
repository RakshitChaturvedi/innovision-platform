import axios, { type InternalAxiosRequestConfig } from "axios";

const attachAuthToken = (config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("innovision_access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
};

const DEFAULT_HOST =
  typeof window !== "undefined" && window.location.hostname
    ? window.location.hostname
    : "localhost";

export const authClient = axios.create({
  baseURL: import.meta.env.VITE_AUTH_API_URL || `http://${DEFAULT_HOST}:8000`,
  withCredentials: true,
});

export const cameraClient = axios.create({
  baseURL: import.meta.env.VITE_CAMERA_API_URL || `http://${DEFAULT_HOST}:8011`,
});

export const alertClient = axios.create({
  baseURL: import.meta.env.VITE_ALERTS_API_URL || `http://${DEFAULT_HOST}:8010`,
});

authClient.interceptors.request.use(attachAuthToken);
cameraClient.interceptors.request.use(attachAuthToken);
alertClient.interceptors.request.use(attachAuthToken);

export const apiClient = authClient;