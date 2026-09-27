import type { ReactNode } from "react";

interface CameraOverlayProps {
  children?: ReactNode;
}

export default function CameraOverlay({
  children,
}: CameraOverlayProps) {
  return (
    <div
      aria-label="Camera analytics overlay"
      style={{
        position: "absolute",
        inset: 0,
        pointerEvents: "none",
      }}
    >
      {children}
    </div>
  );
}