import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";
import type { UserRole } from "@/types/auth";

interface NavigationItem {
  label: string;
  to: string;
  minimumRole: UserRole;
}

const navigation: NavigationItem[] = [
  {
    label: "Dashboard",
    to: "/",
    minimumRole: "viewer",
  },
  {
    label: "Alerts",
    to: "/alerts",
    minimumRole: "operator",
  },
  {
    label: "Incidents",
    to: "/incidents",
    minimumRole: "operator",
  },
  {
    label: "Reports",
    to: "/reports",
    minimumRole: "operator",
  },
  {
    label: "Camera Administration",
    to: "/admin/cameras",
    minimumRole: "admin",
  },
  {
    label: "Compliance",
    to: "/compliance",
    minimumRole: "admin",
  },
  {
    label: "User Administration",
    to: "/admin/users",
    minimumRole: "superadmin",
  },
];

function getSection(label: string) {
  if (label === "Dashboard") return "Overview";

  if (
    label === "Alerts" ||
    label === "Incidents"
  ) {
    return "Monitoring";
  }

  if (label === "Reports") return "Reporting";

  return "Administration";
}

export function AppLayout() {
  const { user, logout } = useAuth();

  const visibleNavigation = navigation.filter((item) =>
    hasMinimumRole(user, item.minimumRole),
  );

  const sections = [
    "Overview",
    "Monitoring",
    "Reporting",
    "Administration",
  ];

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">I</div>

          <div>
            <div className="brand-name">Innovision</div>
            <div className="brand-subtitle">Platform</div>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {sections.map((section) => {
            const items = visibleNavigation.filter(
              (item) => getSection(item.label) === section,
            );

            if (items.length === 0) {
              return null;
            }

            return (
              <div className="nav-section" key={section}>
                <div className="nav-section-label">
                  {section}
                </div>

                <div className="nav-section-items">
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        `nav-item ${isActive ? "active" : ""}`
                      }
                    >
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}
        </nav>

        <div className="sidebar-footer">
          {user && (
            <div className="user-summary">
              <div className="user-avatar">
                {user.role.charAt(0).toUpperCase()}
              </div>

              <div className="user-details">
                <span className="user-role">{user.role}</span>
                <span className="user-status">Authenticated</span>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={() => void logout()}
            className="logout-button"
          >
            Logout
          </button>
        </div>
      </aside>

      <div className="app-main">
        <header className="app-header">
          <div className="header-spacer" />

          <div className="header-right">
            <div className="realtime-indicator">
              <span className="realtime-dot" />
              <span>Realtime</span>
            </div>

            {user && (
              <div className="header-role">
                {user.role}
              </div>
            )}
          </div>
        </header>

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}