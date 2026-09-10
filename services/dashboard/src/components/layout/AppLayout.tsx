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

export function AppLayout() {
  const { user, logout } = useAuth();

  const visibleNavigation = navigation.filter((item) =>
    hasMinimumRole(user, item.minimumRole),
  );

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b bg-white px-6 py-4">
        <div className="flex items-center justify-between">
          <h1 className="text-lg font-semibold">
            Innovision Platform
          </h1>

          {user && (
            <div className="text-sm text-slate-500">
              {user.role}
            </div>
          )}
        </div>
      </header>

      <div className="flex">
        <aside className="flex min-h-[calc(100vh-65px)] w-64 flex-col border-r bg-white p-4">
          <nav className="flex-1 space-y-1">
            {visibleNavigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `block rounded px-3 py-2 text-sm ${
                    isActive
                      ? "bg-slate-200 font-medium"
                      : "text-slate-600 hover:bg-slate-100"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <button
            onClick={() => void logout()}
            className="mt-4 w-full rounded px-3 py-2 text-left text-sm text-red-600 hover:bg-red-50"
          >
            Logout
          </button>
        </aside>

        <main className="flex-1 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}