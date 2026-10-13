import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "@/store/useAuth";
import { hasMinimumRole } from "@/lib/rbac";
import type { UserRole } from "@/types/auth";
import { getEnabledUCModules, type UCModule } from "@/modules/registry";

interface NavigationItem {
  label: string;
  to: string;
  minimumRole: UserRole;
  icon?: string;
}

const CORE_NAVIGATION: Record<string, NavigationItem[]> = {
  Overview: [
    {
      label: "Master Dashboard",
      to: "/",
      minimumRole: "viewer",
      icon: "📊",
    },
  ],
  Monitoring: [
    {
      label: "Alert Center",
      to: "/alerts",
      minimumRole: "operator",
      icon: "🔔",
    },
    {
      label: "Incidents",
      to: "/incidents",
      minimumRole: "operator",
      icon: "⚠️",
    },
  ],
  Reporting: [
    {
      label: "Reports",
      to: "/reports",
      minimumRole: "operator",
      icon: "📈",
    },
  ],
  Administration: [
    {
      label: "Camera Administration",
      to: "/admin/cameras",
      minimumRole: "admin",
      icon: "📹",
    },
    {
      label: "Compliance",
      to: "/compliance",
      minimumRole: "admin",
      icon: "🛡️",
    },
    {
      label: "User Administration",
      to: "/admin/users",
      minimumRole: "superadmin",
      icon: "👥",
    },
  ],
};

export function AppLayout() {
  const { user, logout } = useAuth();
  const [collapsedSections, setCollapsedSections] = useState<Record<string, boolean>>({});

  const enabledModules: UCModule[] = getEnabledUCModules();

  const toggleSection = (sectionKey: string) => {
    setCollapsedSections((prev) => ({
      ...prev,
      [sectionKey]: !prev[sectionKey],
    }));
  };

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark">I</div>
          <div>
            <div className="brand-name">Innovision</div>
            <div className="brand-subtitle">Platform Dashboard</div>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          {/* Core Sections */}
          {Object.entries(CORE_NAVIGATION).map(([section, items]) => {
            const visibleItems = items.filter((item) =>
              hasMinimumRole(user, item.minimumRole),
            );

            if (visibleItems.length === 0) {
              return null;
            }

            return (
              <div className="nav-section" key={section}>
                <div className="nav-section-label">{section}</div>
                <div className="nav-section-items">
                  {visibleItems.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      end={item.to === "/"}
                      className={({ isActive }) =>
                        `nav-item ${isActive ? "active" : ""}`
                      }
                    >
                      {item.icon && <span className="nav-item-icon">{item.icon}</span>}
                      <span>{item.label}</span>
                    </NavLink>
                  ))}
                </div>
              </div>
            );
          })}

          {/* Enabled UC Modules (Driven dynamically by registry with zero UC-specific code) */}
          {enabledModules.length > 0 && (
            <div className="nav-section uc-modules-section">
              <div className="nav-section-label">Active Modules</div>
              {enabledModules.map((module) => {
                const visibleNavItems = module.navItems.filter((item) =>
                  hasMinimumRole(user, item.requiredRole ?? "viewer"),
                );
                const isCollapsed = Boolean(collapsedSections[`uc-${module.id}`]);

                return (
                  <div
                    key={module.id}
                    className="uc-module-nav-group"
                    style={{
                      borderLeft: `3px solid ${module.color}`,
                    }}
                  >
                    <button
                      type="button"
                      className="uc-module-header-button"
                      onClick={() => toggleSection(`uc-${module.id}`)}
                      aria-expanded={!isCollapsed}
                    >
                      <div className="uc-module-title-wrapper">
                        <span className="uc-module-icon">{module.icon}</span>
                        <span className="uc-module-name">{module.shortName}</span>
                      </div>
                      <span className="uc-module-toggle-chevron">
                        {isCollapsed ? "▸" : "▾"}
                      </span>
                    </button>

                    {!isCollapsed && visibleNavItems.length > 0 && (
                      <div className="nav-section-items uc-sub-items">
                        {visibleNavItems.map((item) => (
                          <NavLink
                            key={item.to}
                            to={item.to}
                            className={({ isActive }) =>
                              `nav-item uc-sub-item ${isActive ? "active" : ""}`
                            }
                          >
                            {item.icon && <span className="nav-item-icon">{item.icon}</span>}
                            <span>{item.label}</span>
                          </NavLink>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
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
            {user && <div className="header-role">{user.role}</div>}
          </div>
        </header>

        <main className="app-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
export default AppLayout;