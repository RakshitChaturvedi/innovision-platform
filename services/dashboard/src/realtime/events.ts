export interface SocketAlert {
  id: string;
  alert_id: string;
  camera_id: string | null;
  source_uc: "uc1" | "uc2" | "uc3" | "uc4";
  alert_type: string;
  severity: "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  source_event_id: string;
  frame_reference: string | null;
  frame_provider: string | null;
  status:
    | "pending"
    | "acknowledged"
    | "in_progress"
    | "resolved"
    | "closed";
  metadata: Record<string, unknown>;
  created_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface SocketJoinPayload {
  camera_ids: string[];
  last_seen_timestamp?: string;
}

export interface SocketJoinError {
  error: "unauthorized_camera";
  camera_ids: string[];
}

export interface SocketNotification {
  id: string;
  organization_id: string | null;
  recipient_user_id: string;
  type: string;
  title: string;
  message: string;
  severity: "low" | "medium" | "high" | "critical";
  resource_type: string | null;
  resource_id: string | null;
  metadata: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
}

export const SOCKET_EVENTS = {
  ALERT_NEW: "alert:new",
  ALERT_UPDATED: "alert:updated",
  ALERT_MISSED: "alert:missed",
  NOTIFICATION_NEW: "notification:new",
} as const;