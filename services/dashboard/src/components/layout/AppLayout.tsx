import React from "react";
import { NavLink, Outlet, Link } from "react-router-dom";
import { useAuth } from "@/store/useAuth";
import type { UserRole } from "@/types/auth";
import { NotificationCenter } from "./NotificationCenter";
import { ThemeToggle } from "./ThemeToggle";

interface NavigationItem {
  label: string;
  to: string;
  allowedRoles: UserRole[];
  section: string;
  icon: React.ReactNode;
}

const allNavigation: NavigationItem[] = [
  // SUPERADMIN (Platform Sovereign)
  {
    label: "Platform Control Center",
    to: "/",
    allowedRoles: ["superadmin"],
    section: "Platform Control",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="9" rx="1" />
        <rect x="14" y="3" width="7" height="5" rx="1" />
        <rect x="14" y="12" width="7" height="9" rx="1" />
        <rect x="3" y="16" width="7" height="5" rx="1" />
      </svg>
    ),
  },
  {
    label: "AI Analytics Catalog",
    to: "/analytics",
    allowedRoles: ["superadmin"],
    section: "Platform Control",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
    ),
  },
  {
    label: "User Accounts",
    to: "/admin/users",
    allowedRoles: ["superadmin"],
    section: "Governance & Security",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    label: "Forensic Audit Ledger",
    to: "/audit-log",
    allowedRoles: ["superadmin"],
    section: "Governance & Security",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 14 14" />
      </svg>
    ),
  },
  {
    label: "Platform Settings",
    to: "/settings",
    allowedRoles: ["superadmin"],
    section: "Governance & Security",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
  },

  // ORG_ADMIN / ADMIN (Operational Plant Authority)
  {
    label: "Operations Dashboard",
    to: "/",
    allowedRoles: ["admin", "org_admin"],
    section: "Command & Live Ops",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="7" height="9" rx="1" />
        <rect x="14" y="3" width="7" height="5" rx="1" />
        <rect x="14" y="12" width="7" height="9" rx="1" />
        <rect x="3" y="16" width="7" height="5" rx="1" />
      </svg>
    ),
  },
  {
    label: "Live Video Wall",
    to: "/live-monitoring",
    allowedRoles: ["admin", "org_admin", "operator", "viewer"],
    section: "Command & Live Ops",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M23 7l-7 5 7 5V7z" />
        <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
      </svg>
    ),
  },
  {
    label: "Alert Center",
    to: "/alerts",
    allowedRoles: ["admin", "org_admin", "operator"],
    section: "Command & Live Ops",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
    ),
  },
  {
    label: "Incident Triage",
    to: "/incidents",
    allowedRoles: ["admin", "org_admin", "operator"],
    section: "Command & Live Ops",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
    ),
  },
  {
    label: "Sites & Zones",
    to: "/sites-zones",
    allowedRoles: ["admin", "org_admin"],
    section: "Fleet & Hierarchy",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
        <path d="M9 22v-4h6v4" />
        <line x1="8" y1="6" x2="10" y2="6" />
        <line x1="14" y1="6" x2="16" y2="6" />
        <line x1="8" y1="10" x2="10" y2="10" />
        <line x1="14" y1="10" x2="16" y2="10" />
      </svg>
    ),
  },
  {
    label: "Camera Registry",
    to: "/admin/cameras",
    allowedRoles: ["admin", "org_admin"],
    section: "Fleet & Hierarchy",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="13" r="3" />
        <path d="M5 7h2l2-3h6l2 3h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z" />
      </svg>
    ),
  },
  {
    label: "AI Analytics Catalog",
    to: "/analytics",
    allowedRoles: ["admin", "org_admin", "operator", "viewer"],
    section: "Fleet & Hierarchy",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
      </svg>
    ),
  },
  {
    label: "Safety Reports",
    to: "/reports",
    allowedRoles: ["admin", "org_admin", "operator"],
    section: "Governance & Reporting",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
      </svg>
    ),
  },
  {
    label: "Forensic Audit Log",
    to: "/audit-log",
    allowedRoles: ["admin", "org_admin"],
    section: "Governance & Reporting",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 14 14" />
      </svg>
    ),
  },
  {
    label: "Platform Settings",
    to: "/settings",
    allowedRoles: ["admin", "org_admin"],
    section: "Governance & Reporting",
    icon: (
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="3" />
        <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
      </svg>
    ),
  },
];

export function AppLayout() {
  const { user, logout } = useAuth();

  const userRole = user?.role || "viewer";

  // Filter navigation strictly by current user's role
  const visibleNavigation = allNavigation.filter((item) =>
    item.allowedRoles.includes(userRole)
  );

  // Group into ordered distinct sections
  const sections = Array.from(new Set(visibleNavigation.map((item) => item.section)));

  const defaultHomeLink = userRole === "operator" ? "/alerts" : userRole === "viewer" ? "/live-monitoring" : "/";
  const brandSubTitle = userRole === "superadmin" ? "Platform Sovereign Command" : "Safety & Operations Command";


  return (
    <div className="app-shell">
      {/* Sleek, Professional Sidebar */}
      <aside className="app-sidebar">
        {/* Brand Header */}
        <Link to={defaultHomeLink} className="sidebar-brand-link">
          <div className="brand-mark-red">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#ffffff"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M3 12h2m14 0h2M12 3v2m0 14v2" />
              <path d="M5.6 5.6l1.4 1.4m10 10l1.4 1.4M5.6 18.4l1.4-1.4m10-10l1.4-1.4" />
            </svg>
          </div>

          <div className="brand-text-wrap">
            <div className="brand-name-text">
              INNOVISION
              <span className="brand-mini-badge">AI</span>
            </div>
            <div className="brand-sub-text">{brandSubTitle}</div>
          </div>
        </Link>

        {/* Navigation Section */}
        <nav className="sidebar-nav" aria-label="Main navigation">
          {sections.map((section) => {
            const items = visibleNavigation.filter(
              (item) => item.section === section,
            );

            if (items.length === 0) {
              return null;
            }

            return (
              <div className="nav-section-group" key={section}>
                <div className="nav-section-title">{section}</div>

                <div className="nav-section-items">
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        `nav-link-item ${isActive ? "active" : ""}`
                      }
                    >
                      <span className="nav-item-icon">{item.icon}</span>
                      <span className="nav-item-label">{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        {/* Sidebar Footer with User Card & Logout */}
        <div className="sidebar-footer-box">
          {user && (
            <div className="user-profile-badge">
              <div className="user-avatar-circle">
                {user.role.charAt(0).toUpperCase()}
                <span className="avatar-online-dot" />
              </div>

              <div className="user-profile-info">
                <span className="user-email-text" title={user.email || user.id}>
                  {user.email ? user.email.split("@")[0] : "Operator"}
                </span>
                <span className="user-role-pill">{user.role}</span>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => void logout()}
            className="sidebar-logout-btn"
            title="Sign out of platform"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
              <polyline points="16 17 21 12 16 7" />
              <line x1="21" y1="12" x2="9" y2="12" />
            </svg>
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="app-main">
        {/* Top Header */}
        <header className="app-header">
          <div className="header-breadcrumbs">
            <span className="header-status-pulse">
              <span className="status-ping-dot" />
              <span>{userRole === "superadmin" ? "PLATFORM SOVEREIGNTY ACTIVE" : "CLUSTER OPERATIONAL"}</span>
            </span>
          </div>

          <div className="header-right">
            {/* Quick Link to Landing / Showcase Page */}
            <Link
              to="/landing"
              className="header-showcase-btn"
              title="View Public Showcase"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polygon points="10 8 16 12 10 16 10 8" fill="currentColor" />
              </svg>
              <span>Showcase View</span>
            </Link>

            <ThemeToggle />

            <NotificationCenter />

            <div className="realtime-indicator">
              <span className="realtime-dot" />
              <span>Active Streams</span>
            </div>

            {user && (
              <div className="header-role-badge">
                {user.role}
              </div>
            )}
          </div>
        </header>

        {/* Dynamic Page Content */}
        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}