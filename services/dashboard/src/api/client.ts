import axios from "axios";

export const authClient = axios.create({
  baseURL: import.meta.env.VITE_AUTH_API_URL,
  withCredentials: true,
});

export const cameraClient = axios.create({
  baseURL: import.meta.env.VITE_CAMERA_API_URL,
});

export const apiClient = authClient;

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("innovision_access_token");

  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  return config;
});