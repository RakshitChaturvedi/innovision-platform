import { useState } from "react";
import {
  useCameras,
  useCreateCamera,
  useDeleteCamera,
  useUpdateCameraConfig,
} from "../../hooks/useCameras";
import type { Camera } from "@/types/camera";

const USE_CASES = ["uc1", "uc2", "uc3", "uc4"];
const LOCAL_VIDEO_PREFIX = "/app/test_data/videos/";

const TEST_VIDEOS = [
  {
    label: "UC1 — uc1.mp4",
    path: "/app/test_data/videos/uc1.mp4",
  },
  {
    label: "UC2 — uc2.mp4",
    path: "/app/test_data/videos/uc2.mp4",
  },
  {
    label: "UC3 — uc3.mp4",
    path: "/app/test_data/videos/uc3.mp4",
  },
  {
    label: "UC4 — uc4.mp4",
    path: "/app/test_data/videos/uc4.mp4",
  },
];

type SourceType = "local" | "rtsp";

interface CameraFormState {
  name: string;
  location: string;
  sourceType: SourceType;
  source: string;
  fps: number;
  useCases: string[];
}

const EMPTY_FORM: CameraFormState = {
  name: "",
  location: "",
  sourceType: "local",
  source: TEST_VIDEOS[0].path,
  fps: 10,
  useCases: ["uc1"],
};

function formatUseCase(value: string) {
  return value.toUpperCase();
}

function statusLabel(status: Camera["status"]) {
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export default function CameraAdministration() {
  const { data: cameras = [], isLoading, isError } = useCameras();

  const createMutation = useCreateCamera();
  const updateMutation = useUpdateCameraConfig();
  const deleteMutation = useDeleteCamera();

  const [showAdd, setShowAdd] = useState(false);
  const [editingCamera, setEditingCamera] = useState<Camera | null>(null);
  const [deletingCamera, setDeletingCamera] = useState<Camera | null>(null);

  const [form, setForm] = useState<CameraFormState>(EMPTY_FORM);

  function openAdd() {
    setForm({
      ...EMPTY_FORM,
      useCases: [...EMPTY_FORM.useCases],
    });
    setShowAdd(true);
  }

  function closeAdd() {
    if (!createMutation.isPending) {
      setShowAdd(false);
    }
  }

  function openEdit(camera: Camera) {
    setForm({
      name: camera.name,
      location: camera.location ?? "",
      sourceType: camera.rtsp_url?.startsWith("rtsp://")
      ? "rtsp"
      : "local",
      source: camera.rtsp_url ?? "",
      fps: camera.fps,
      useCases: [...camera.use_cases],
    });

    setEditingCamera(camera);
  }

  function toggleUseCase(useCase: string) {
    setForm((current) => ({
      ...current,
      useCases: current.useCases.includes(useCase)
        ? current.useCases.filter((value) => value !== useCase)
        : [...current.useCases, useCase],
    }));
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault();

    await createMutation.mutateAsync({
      name: form.name.trim(),
      location: form.location.trim() || undefined,
      rtsp_url: form.source.trim(),
      use_cases: form.useCases,
      fps: form.fps,
    });

    setShowAdd(false);
  }

  async function handleUpdate(event: React.FormEvent) {
    event.preventDefault();

    if (!editingCamera) return;

    await updateMutation.mutateAsync({
      cameraId: editingCamera.id,
      payload: {
        fps: form.fps,
        use_cases: form.useCases,
      },
    });

    setEditingCamera(null);
  }

  async function handleDelete() {
    if (!deletingCamera) return;

    await deleteMutation.mutateAsync(deletingCamera.id);
    setDeletingCamera(null);
  }

  return (
    <div className="admin-page">
      <header className="admin-page-header">
        <div>
          <p className="page-eyebrow">Administration</p>
          <h1>Camera Administration</h1>
          <p className="page-description">
            Manage video sources, frame rates, and assigned use cases.
          </p>
        </div>

        <button
          type="button"
          className="button button-primary"
          onClick={openAdd}
        >
          + Add Video Source
        </button>
      </header>

      <section className="admin-table-section">
        <div className="admin-table-header">
          <div>
            <h2>Video Sources</h2>
            <span>{cameras.length} configured</span>
          </div>
        </div>

        {isLoading && (
          <div className="admin-table-state">
            Loading cameras...
          </div>
        )}

        {isError && (
          <div className="admin-table-state admin-table-error">
            Failed to load cameras.
          </div>
        )}

        {!isLoading && !isError && cameras.length === 0 && (
          <div className="admin-table-state">
            No video sources configured.
          </div>
        )}

        {!isLoading && !isError && cameras.length > 0 && (
          <div className="admin-table-wrapper">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>Camera</th>
                  <th>Location</th>
                  <th>Source</th>
                  <th>Status</th>
                  <th>FPS</th>
                  <th>Use Cases</th>
                  <th />
                </tr>
              </thead>

              <tbody>
                {cameras.map((camera) => (
                  <tr key={camera.id}>
                    <td>
                      <div className="camera-admin-name">
                        <strong>{camera.name}</strong>
                        <span>{camera.id}</span>
                      </div>
                    </td>

                    <td>{camera.location || "—"}</td>

                    <td>
                      <span
                        className={`source-badge ${
                          camera.rtsp_url?.startsWith("rtsp://")
                            ? "source-rtsp"
                            : "source-local"
                        }`}
                      >
                        {camera.rtsp_url?.startsWith("rtsp://")
                          ? "RTSP"
                          : "Local"}
                      </span>
                    </td>

                    <td>
                      <span
                        className={`status-badge status-${camera.status}`}
                      >
                        <span className="status-dot" />
                        {statusLabel(camera.status)}
                      </span>
                    </td>

                    <td>{camera.fps}</td>

                    <td>
                      <div className="use-case-list">
                        {camera.use_cases.length > 0
                          ? camera.use_cases.map((useCase) => (
                              <span key={useCase} className="use-case-badge">
                                {formatUseCase(useCase)}
                              </span>
                            ))
                          : "—"}
                      </div>
                    </td>

                    <td>
                      <div className="table-actions">
                        <button
                          type="button"
                          className="button button-secondary button-small"
                          onClick={() => openEdit(camera)}
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          className="button button-danger button-small"
                          onClick={() => setDeletingCamera(camera)}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {showAdd && (
        <CameraModal
          title="Add Video Source"
          form={form}
          setForm={setForm}
          onSubmit={handleCreate}
          onCancel={closeAdd}
          submitLabel="Add Camera"
          pending={createMutation.isPending}
          error={createMutation.isError}
          toggleUseCase={toggleUseCase}
          showSourceFields
        />
      )}

    {editingCamera && (
    <CameraModal
        title={`Edit ${editingCamera.name}`}
        form={form}
        setForm={setForm}
        onSubmit={handleUpdate}
        onCancel={() => setEditingCamera(null)}
        submitLabel="Save Changes"
        pending={updateMutation.isPending}
        error={updateMutation.isError}
        toggleUseCase={toggleUseCase}
        showSourceFields={false}
    />
    )}

      {deletingCamera && (
        <div className="modal-backdrop">
          <section
            className="modal modal-small"
            role="dialog"
            aria-modal="true"
          >
            <header className="modal-header">
              <div>
                <p className="page-eyebrow">Camera Administration</p>
                <h2>Delete Camera</h2>
              </div>

              <button
                type="button"
                className="modal-close"
                onClick={() => setDeletingCamera(null)}
              >
                ×
              </button>
            </header>

            <div className="modal-body">
              <p>
                Delete <strong>{deletingCamera.name}</strong>?
              </p>
              <p className="modal-muted">
                This removes the camera from the active camera registry.
              </p>
            </div>

            <footer className="modal-footer">
              <button
                type="button"
                className="button button-secondary"
                onClick={() => setDeletingCamera(null)}
                disabled={deleteMutation.isPending}
              >
                Cancel
              </button>

              <button
                type="button"
                className="button button-danger"
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete Camera"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </div>
  );
}

interface CameraModalProps {
  title: string;
  form: CameraFormState;
  setForm: React.Dispatch<React.SetStateAction<CameraFormState>>;
  onSubmit: (event: React.FormEvent) => void;
  onCancel: () => void;
  submitLabel: string;
  pending: boolean;
  error: boolean;
  toggleUseCase: (useCase: string) => void;
  showSourceFields: boolean;
}

function CameraModal({
  title,
  form,
  setForm,
  onSubmit,
  onCancel,
  submitLabel,
  pending,
  error,
  toggleUseCase,
  showSourceFields,
}: CameraModalProps) {
  return (
    <div className="modal-backdrop">
      <form className="modal" onSubmit={onSubmit}>
        <header className="modal-header">
          <div>
            <p className="page-eyebrow">Camera Administration</p>
            <h2>{title}</h2>
          </div>

          <button
            type="button"
            className="modal-close"
            onClick={onCancel}
            disabled={pending}
          >
            ×
          </button>
        </header>

        <div className="modal-body">
          {showSourceFields && (
            <>
              <label className="form-field">
                <span>Camera Name</span>
                <input
                  value={form.name}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      name: event.target.value,
                    }))
                  }
                  required
                />
              </label>

              <label className="form-field">
                <span>Location</span>
                <input
                  value={form.location}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      location: event.target.value,
                    }))
                  }
                />
              </label>

              <div className="form-field">
                <span>Source Type</span>

                <div className="source-type-toggle">
                  <label>
                    <input
                      type="radio"
                      checked={form.sourceType === "local"}
                      onChange={() =>
                        setForm((current) => ({
                          ...current,
                          sourceType: "local",
                          source: TEST_VIDEOS[0].path,
                        }))
                      }
                    />
                    Local Video
                  </label>

                  <label>
                    <input
                      type="radio"
                      checked={form.sourceType === "rtsp"}
                      onChange={() =>
                        setForm((current) => ({
                          ...current,
                          sourceType: "rtsp",
                          source: "",
                        }))
                      }
                    />
                    RTSP Stream
                  </label>
                </div>
              </div>

              {form.sourceType === "local" ? (
                <>
                  <label className="form-field">
                    <span>Test Video</span>

                    <select
                      value={
                        TEST_VIDEOS.some((video) => video.path === form.source)
                          ? form.source
                          : "__custom__"
                      }
                      onChange={(event) => {
                        const value = event.target.value;

                        if (value === "__custom__") {
                          setForm((current) => ({
                            ...current,
                            source: "",
                          }));
                          return;
                        }

                        setForm((current) => ({
                          ...current,
                          source: value,
                        }));
                      }}
                    >
                      {TEST_VIDEOS.map((video) => (
                        <option key={video.path} value={video.path}>
                          {video.label}
                        </option>
                      ))}

                      <option value="__custom__">Custom Video...</option>
                    </select>
                  </label>

                  {!TEST_VIDEOS.some((video) => video.path === form.source) && (
                    <label className="form-field">
                      <span>Video Filename</span>

                      <input
                        value={
                          form.source.startsWith(LOCAL_VIDEO_PREFIX)
                            ? form.source.slice(LOCAL_VIDEO_PREFIX.length)
                            : form.source
                        }
                        onChange={(event) => {
                          const filename = event.target.value;

                          setForm((current) => ({
                            ...current,
                            source: filename
                              ? `${LOCAL_VIDEO_PREFIX}${filename}`
                              : "",
                          }));
                        }}
                        placeholder="uc2.mp4"
                        required
                      />

                      <small>
                        File must exist in test_data/videos.
                      </small>
                    </label>
                  )}
                </>
              ) : (
                <label className="form-field">
                  <span>RTSP URL</span>

                  <input
                    value={form.source}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        source: event.target.value,
                      }))
                    }
                    placeholder="rtsp://192.168.1.100:554/stream"
                    required
                  />
                </label>
              )}
            </>
          )}

          <label className="form-field">
            <span>FPS</span>
            <input
              type="number"
              min={1}
              max={60}
              value={form.fps}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  fps: Number(event.target.value),
                }))
              }
              required
            />
          </label>

          <fieldset className="form-fieldset">
            <legend>Use Cases</legend>

            <div className="use-case-selector">
              {USE_CASES.map((useCase) => (
                <label key={useCase} className="checkbox-option">
                  <input
                    type="checkbox"
                    checked={form.useCases.includes(useCase)}
                    onChange={() => toggleUseCase(useCase)}
                  />
                  {formatUseCase(useCase)}
                </label>
              ))}
            </div>
          </fieldset>

          {error && (
            <p className="form-error">
              Operation failed. Check the Camera Registry service.
            </p>
          )}
        </div>

        <footer className="modal-footer">
          <button
            type="button"
            className="button button-secondary"
            onClick={onCancel}
            disabled={pending}
          >
            Cancel
          </button>

          <button
            type="submit"
            className="button button-primary"
            disabled={pending}
          >
            {pending ? "Saving..." : submitLabel}
          </button>
        </footer>
      </form>
    </div>
  );
}