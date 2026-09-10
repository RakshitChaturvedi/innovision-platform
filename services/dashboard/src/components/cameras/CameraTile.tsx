import { useNavigate } from "react-router-dom";

import type { Camera } from "@/types/camera";

interface CameraTileProps {
  camera: Camera;
}

export default function CameraTile({ camera }: CameraTileProps) {
  const navigate = useNavigate();

  return (
    <button
      type="button"
      onClick={() => navigate(`/cameras/${camera.id}`)}
      style={{
        width: "100%",
        textAlign: "left",
        cursor: "pointer",
        padding: 0,
        border: "none",
        background: "transparent",
      }}
    >
      <article
        style={{
          border: "1px solid #ddd",
          borderRadius: "8px",
          padding: "16px",
        }}
      >
        <header>
          <h2>{camera.name}</h2>
          <p>
            Status: <strong>{camera.status}</strong>
          </p>
        </header>

        <p>FPS: {camera.fps}</p>

        <p>
          Use cases:{" "}
          {camera.use_cases.length > 0
            ? camera.use_cases.join(", ")
            : "None"}
        </p>
      </article>
    </button>
  );
}