import { notificationClient } from "./client";

export interface NotificationItem {
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
  read_at: string | null;
}

export interface NotificationListResponse {
  items: NotificationItem[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface UnreadCountResponse {
  unread_count: number;
}

export interface NotificationPreferenceItem {
  notification_type: string;
  display_name: string;
  description: string;
  in_app_enabled: boolean;
  email_enabled: boolean;
}

export interface NotificationPreferenceUpdate {
  notification_type: string;
  in_app_enabled?: boolean;
  email_enabled?: boolean;
}

export async function fetchNotifications(params?: {
  page?: number;
  page_size?: number;
  is_read?: boolean;
  type_filter?: string;
  severity_filter?: string;
}): Promise<NotificationListResponse> {
  const queryParams: Record<string, unknown> = {};
  if (params?.page) queryParams.page = params.page;
  if (params?.page_size) queryParams.page_size = params.page_size;
  if (params?.is_read !== undefined) queryParams.is_read = params.is_read;
  if (params?.type_filter) queryParams.type_filter = params.type_filter;
  if (params?.severity_filter) queryParams.severity_filter = params.severity_filter;

  const res = await notificationClient.get<NotificationListResponse>("/api/v1/notifications/", {
    params: queryParams,
  });
  return res.data;
}

export async function fetchUnreadCount(): Promise<UnreadCountResponse> {
  const res = await notificationClient.get<UnreadCountResponse>("/api/v1/notifications/unread-count");
  return res.data;
}

export async function markNotificationAsRead(id: string): Promise<NotificationItem> {
  const res = await notificationClient.put<NotificationItem>(`/api/v1/notifications/${id}/read`);
  return res.data;
}

export async function markAllNotificationsAsRead(): Promise<UnreadCountResponse> {
  const res = await notificationClient.put<UnreadCountResponse>("/api/v1/notifications/read-all");
  return res.data;
}

export async function fetchNotificationPreferences(): Promise<NotificationPreferenceItem[]> {
  const res = await notificationClient.get<NotificationPreferenceItem[]>("/api/v1/notifications/preferences");
  return res.data;
}

export async function updateNotificationPreferences(
  items: NotificationPreferenceUpdate[]
): Promise<NotificationPreferenceItem[]> {
  const res = await notificationClient.put<NotificationPreferenceItem[]>("/api/v1/notifications/preferences", {
    preferences: items,
  });
  return res.data;
}
