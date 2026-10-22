import type { UCRoute, UCNavItem } from "../registry";
import { ConfiguratorPage } from "./pages/ConfiguratorPage";
import { TrackingPage } from "./pages/TrackingPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { PipelinePage } from "./pages/PipelinePage";
import { UC4OverviewPage } from "./pages/UC4OverviewPage";

export const uc4Routes: UCRoute[] = [
  {
    path: "/uc4",
    element: <UC4OverviewPage />,
    requiredRole: "viewer",
  },
  {
    path: "/uc4/configurator",
    element: <ConfiguratorPage />,
    requiredRole: "operator",
  },
  {
    path: "/uc4/tracking",
    element: <TrackingPage />,
    requiredRole: "viewer",
  },
  {
    path: "/uc4/analytics",
    element: <AnalyticsPage />,
    requiredRole: "viewer",
  },
  {
    path: "/uc4/pipeline",
    element: <PipelinePage />,
    requiredRole: "operator",
  },
];

export const uc4NavItems: UCNavItem[] = [
  {
    label: "Traffic Overview",
    to: "/uc4",
    icon: "📊",
    requiredRole: "viewer",
  },
  {
    label: "Camera Configurator",
    to: "/uc4/configurator",
    icon: "📐",
    requiredRole: "operator",
  },
  {
    label: "Vehicle Tracking",
    to: "/uc4/tracking",
    icon: "🔍",
    requiredRole: "viewer",
  },
  {
    label: "Traffic Analytics",
    to: "/uc4/analytics",
    icon: "📈",
    requiredRole: "viewer",
  },
  {
    label: "Live Pipeline",
    to: "/uc4/pipeline",
    icon: "🎥",
    requiredRole: "operator",
  },
];

export {
  ConfiguratorPage,
  TrackingPage,
  AnalyticsPage,
  PipelinePage,
  UC4OverviewPage,
};
