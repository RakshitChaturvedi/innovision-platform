import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  fetchNotifications,
  fetchUnreadCount,
  markNotificationAsRead,
  markAllNotificationsAsRead,
  type NotificationItem,
} from "@/api/notifications";

export function NotificationCenter() {
  const [isOpen, setIsOpen] = useState(false);
  const [filter, setFilter] = useState<"all" | "unread" | "critical">("all");
  const panelRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Unread Count Query
  const unreadQuery = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: fetchUnreadCount,
    refetchInterval: 30000,
  });

  // Notifications List Query
  const notificationsQuery = useQuery({
    queryKey: ["notifications", filter],
    queryFn: () =>
      fetchNotifications({
        page: 1,
        page_size: 20,
        is_read: filter === "unread" ? false : undefined,
        severity_filter: filter === "critical" ? "critical" : undefined,
      }),
    enabled: isOpen,
  });

  // Mark single as read mutation
  const markReadMutation = useMutation({
    mutationFn: markNotificationAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["notifications", "unread-count"] });
    },
  });

  // Mark all as read mutation
  const markAllReadMutation = useMutation({
    mutationFn: markAllNotificationsAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["notifications", "unread-count"] });
    },
  });

  // Close panel on click outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  const handleNotificationClick = (item: NotificationItem) => {
    if (!item.is_read) {
      markReadMutation.mutate(item.id);
    }
    setIsOpen(false);

    if (item.resource_type === "alert" && item.resource_id) {
      navigate(`/alerts`);
    } else if (item.resource_type === "incident" && item.resource_id) {
      navigate(`/incidents`);
    }
  };

  const unreadCount = unreadQuery.data?.unread_count ?? 0;

  return (
    <div className="relative inline-block text-left" ref={panelRef} style={{ position: "relative" }}>
      {/* Bell Button */}
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="btn-notification-bell"
        aria-label="Notifications"
        style={{
          background: "transparent",
          border: "1px solid var(--border-color, #334155)",
          borderRadius: "8px",
          padding: "8px 12px",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          color: "var(--text-main, #f8fafc)",
          position: "relative",
        }}
      >
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>

        {unreadCount > 0 && (
          <span
            style={{
              background: "#ef4444",
              color: "#ffffff",
              fontSize: "0.72rem",
              fontWeight: 700,
              padding: "2px 6px",
              borderRadius: "9999px",
              lineHeight: 1,
            }}
          >
            {unreadCount > 99 ? "99+" : unreadCount}
          </span>
        )}
      </button>

      {/* Popover Dropdown Panel */}
      {isOpen && (
        <div
          style={{
            position: "absolute",
            right: 0,
            marginTop: "8px",
            width: "360px",
            maxHeight: "480px",
            backgroundColor: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: "12px",
            boxShadow: "var(--shadow-dropdown)",
            zIndex: 100,
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: "12px 16px",
              borderBottom: "1px solid var(--border)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ fontWeight: 600, fontSize: "0.95rem", color: "var(--text-primary)" }}>
              Notifications
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => markAllReadMutation.mutate()}
                disabled={markAllReadMutation.isPending}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--primary)",
                  fontSize: "0.8rem",
                  cursor: "pointer",
                  fontWeight: 500,
                }}
              >
                {markAllReadMutation.isPending ? "Processing..." : "Mark all as read"}
              </button>
            )}
          </div>

          {/* Filter Tabs */}
          <div
            style={{
              display: "flex",
              borderBottom: "1px solid var(--border)",
              background: "var(--surface-raised)",
              padding: "4px",
              gap: "4px",
            }}
          >
            {(["all", "unread", "critical"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setFilter(t)}
                style={{
                  flex: 1,
                  padding: "6px 0",
                  fontSize: "0.75rem",
                  fontWeight: 500,
                  borderRadius: "6px",
                  border: "none",
                  cursor: "pointer",
                  textTransform: "capitalize",
                  backgroundColor: filter === t ? "var(--surface)" : "transparent",
                  color: filter === t ? "var(--primary)" : "var(--text-muted)",
                  boxShadow: filter === t ? "var(--shadow-card)" : "none",
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {/* List Content */}
          <div style={{ flex: 1, overflowY: "auto", padding: "8px 0" }}>
            {notificationsQuery.isLoading && (
              <div style={{ padding: "20px", textAlign: "center", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                Loading notifications...
              </div>
            )}

            {notificationsQuery.isError && (
              <div style={{ padding: "20px", textAlign: "center", color: "var(--danger)", fontSize: "0.85rem" }}>
                Failed to load notifications.
              </div>
            )}

            {notificationsQuery.isSuccess && notificationsQuery.data.items.length === 0 && (
              <div style={{ padding: "30px 20px", textAlign: "center", color: "var(--text-muted)" }}>
                <div style={{ fontSize: "1.2rem", marginBottom: "4px" }}>🎉</div>
                <div style={{ fontSize: "0.85rem", fontWeight: 500, color: "var(--text-primary)" }}>
                  You're all caught up
                </div>
                <div style={{ fontSize: "0.75rem", marginTop: "2px" }}>No notifications found</div>
              </div>
            )}

            {notificationsQuery.isSuccess &&
              notificationsQuery.data.items.map((item) => (
                <div
                  key={item.id}
                  onClick={() => handleNotificationClick(item)}
                  style={{
                    padding: "10px 14px",
                    borderBottom: "1px solid var(--border)",
                    cursor: "pointer",
                    backgroundColor: item.is_read ? "transparent" : "var(--primary-bg)",
                    transition: "background 0.15s ease",
                    display: "flex",
                    gap: "10px",
                    alignItems: "flex-start",
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLDivElement).style.backgroundColor = "var(--surface-hover)";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLDivElement).style.backgroundColor = item.is_read
                      ? "transparent"
                      : "var(--primary-bg)";
                  }}
                >
                  {/* Severity Indicator Dot */}
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      marginTop: "6px",
                      flexShrink: 0,
                      backgroundColor:
                        item.severity === "critical"
                          ? "var(--danger)"
                          : item.severity === "high"
                          ? "var(--warning)"
                          : item.severity === "medium"
                          ? "var(--warning)"
                          : "var(--info)",
                    }}
                  />

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "0.82rem",
                          fontWeight: item.is_read ? 500 : 700,
                          color: "var(--text-primary)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                        }}
                      >
                        {item.title}
                      </span>
                      <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", flexShrink: 0, marginLeft: "6px" }}>
                        {new Date(item.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      </span>
                    </div>

                    <p
                      style={{
                        fontSize: "0.75rem",
                        color: "var(--text-secondary)",
                        margin: "3px 0 0 0",
                        lineHeight: 1.3,
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {item.message}
                    </p>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
