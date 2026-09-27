export type AlertSeverity =
  | "low"
  | "medium"
  | "high"
  | "critical";

export type AlertStatus =
  | "pending"
  | "acknowledged"
  | "in_progress"
  | "resolved"
  | "closed";

export type AlertSourceUC =
  | "uc1"
  | "uc2"
  | "uc3"
  | "uc4";

export interface Alert {
  id: string;
  alert_id: string;
  camera_id: string | null;
  source_uc: AlertSourceUC;
  alert_type: string;
  severity: AlertSeverity;
  title: string;
  description: string;
  source_event_id: string;
  frame_reference: string | null;
  frame_provider: string | null;
  status: AlertStatus;
  metadata: Record<string, unknown>;
  created_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
}