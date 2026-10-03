/**
 * Pure utility functions for DetectionOverlay and per-use-case overlay behavior.
 */

export function isOverlayEnabledForCamera(
  cameraUseCases: string[],
  enabledUseCasesConfig: string = "uc3",
): boolean {
  if (!cameraUseCases || cameraUseCases.length === 0) return false;
  const allowedList = enabledUseCasesConfig
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  return cameraUseCases.some((uc) => allowedList.includes(uc.toLowerCase()));
}

export function getActiveOverlayUseCase(
  cameraUseCases: string[],
  enabledUseCasesConfig: string = "uc3",
): string | null {
  if (!cameraUseCases || cameraUseCases.length === 0) return null;
  const allowedList = enabledUseCasesConfig
    .split(",")
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);

  const matched = cameraUseCases
    .map((uc) => uc.toLowerCase())
    .find((uc) => allowedList.includes(uc));

  return matched ?? null;
}

export function buildDetectionsUrl(cameraId: string, useCase: string = "uc3"): string {
  const uc = useCase.trim().toLowerCase();
  return `/${uc}/cameras/${cameraId}/latest-detections`;
}

export function shouldStopPollingOnStatus(statusCode: number): boolean {
  return statusCode === 404;
}

export function isTimestampStale(
  lastObservedChangeTimeMs: number,
  currentTimeMs: number,
  staleThresholdMs: number = 5000,
): boolean {
  return currentTimeMs - lastObservedChangeTimeMs > staleThresholdMs;
}
