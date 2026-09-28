import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createCamera,
  deleteCamera,
  getCameras,
  updateCameraConfig,
  type CreateCameraPayload,
  type UpdateCameraConfigPayload,
} from "../api/cameras";

export const camerasQueryKey = ["cameras"];

export function useCameras() {
  return useQuery({
    queryKey: camerasQueryKey,
    queryFn: getCameras,
    refetchInterval: 5000,
  });
}

export function useCreateCamera() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateCameraPayload) =>
      createCamera(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: camerasQueryKey,
      });
    },
  });
}

export function useUpdateCameraConfig() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      cameraId,
      payload,
    }: {
      cameraId: string;
      payload: UpdateCameraConfigPayload;
    }) => updateCameraConfig(cameraId, payload),

    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: camerasQueryKey,
      });
    },
  });
}

export function useDeleteCamera() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (cameraId: string) =>
      deleteCamera(cameraId),

    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: camerasQueryKey,
      });
    },
  });
}