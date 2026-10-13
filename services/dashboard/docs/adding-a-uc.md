# Adding a New Use Case (UC) to Innovision Master Dashboard

The Innovision Master Dashboard is architected as an **extensible, pluggable shell**. New use cases (e.g. UC1, UC2, UC3, UC5) can be integrated **without modifying any core shell files** (`AppLayout.tsx`, `AppRoutes.tsx`, `api/client.ts`, or core pages).

---

## Architecture Overview

```
services/dashboard/
├── src/
│   ├── modules/
│   │   ├── registry.ts          <-- ONLY registration point
│   │   ├── uc4/                 <-- UC4 Self-contained module
│   │   │   ├── pages/           <-- Module-specific pages
│   │   │   ├── components/      <-- Module-specific UI
│   │   │   ├── api/             <-- Module-specific API client & hooks
│   │   │   └── types/           <-- Module-specific TypeScript schemas
│   │   └── ucN/                 <-- Your new UC goes here
│   ├── components/
│   │   ├── common/              <-- Shared design system (StatCard, Badge, PageHeader, etc.)
│   │   ├── layout/              <-- Core AppLayout (dynamically renders active modules)
│   │   └── cameras/             <-- Generic CameraOverlay & CameraTile
│   └── routes/                  <-- Dynamic AppRoutes (mounts module routes automatically)
```

---

## Step-by-Step Implementation Guide

### Step 1: Create your UC Module Directory

Create a folder for your module under `src/modules/uc<N>/`:

```bash
mkdir -p services/dashboard/src/modules/ucN/pages
mkdir -p services/dashboard/src/modules/ucN/components
mkdir -p services/dashboard/src/modules/ucN/api
mkdir -p services/dashboard/src/modules/ucN/types
```

### Step 2: Implement your Pages and Components

Build native React components following the platform's design system:
- Use reusable components from `@/components/common`:
  - `<PageHeader title="..." description="..." />`
  - `<StatCard title="..." value={...} icon="..." />`
  - `<Badge variant="severity" severity="high">High</Badge>`
  - `<Badge variant="uc" ucId="ucN" />`
  - `<DataTable ... />`, `<EmptyState />`, `<ErrorState />`, `<LoadingState />`
- Use the shared dark theme variables (`--bg`, `--surface`, `--border`, `--text-primary`, etc.) from `src/index.css`.

Example page (`src/modules/ucN/pages/OverviewPage.tsx`):
```tsx
import { PageHeader } from "@/components/common/PageHeader";
import { StatCard } from "@/components/common/StatCard";

export function UCOverviewPage() {
  return (
    <div className="page">
      <PageHeader
        title="UC Name Analytics"
        description="Real-time monitoring and CV insights"
      />
      <div className="stats-grid">
        <StatCard title="Active Scans" value={142} icon="🔍" />
        <StatCard title="Detected Events" value={18} icon="⚠️" color="#E11D48" />
      </div>
    </div>
  );
}
```

### Step 3: Register your Module in `src/modules/registry.ts`

Open [src/modules/registry.ts](file:///d:/Internship/integration_uc4/innovision-platform/services/dashboard/src/modules/registry.ts) and add or enable your entry in `UC_MODULES`:

```typescript
import { UCOverviewPage } from "@/modules/ucN/pages/OverviewPage";
import { UCAnalyticsPage } from "@/modules/ucN/pages/AnalyticsPage";

export const UC_MODULES: Record<string, UCModule> = {
  // ... existing modules ...
  ucN: {
    id: "ucN",
    name: "Worker Safety & Presence",
    shortName: "Worker Safety (UCN)",
    description: "Real-time occupancy monitoring and worker density tracking",
    color: "#1E3A8A",                   // Distinct primary color
    colorBg: "rgba(30, 58, 138, 0.15)", // Translucent badge background
    icon: "👷",
    overlayBaseUrl: import.meta.env.VITE_UCN_API_URL || "http://localhost:802N",
    enabled: true,                       // Set to true to activate
    requiredRole: "viewer",              // Optional minimum role for module
    navItems: [
      { label: "Overview", to: "/ucN/overview", icon: "📊" },
      { label: "Analytics", to: "/ucN/analytics", icon: "📈", requiredRole: "operator" },
    ],
    routes: [
      { path: "/ucN/overview", element: <UCOverviewPage /> },
      { path: "/ucN/analytics", element: <UCAnalyticsPage />, requiredRole: "operator" },
    ],
  },
};
```

**That is all!** The shell automatically:
1. Adds your module to the sidebar as a collapsible menu section colored with your brand color.
2. Registers your routes in `AppRoutes` with proper authentication and RBAC protection.
3. Renders your UC badges across the Master Dashboard camera grid and Alert Center filters.

---

## Live Video Overlay Endpoint Specification

For the Master Dashboard and Camera Detail pages to render real-time CV bounding boxes on top of camera feeds, your backend service must provide:

### `GET /uc{N}/cameras/{camera_id}/latest-detections`
- **Response Time**: < 100ms
- **Authentication**: None required (public read endpoint for frontend polling)
- **Response Format**:
```json
{
  "timestamp": "2026-10-09T06:30:00.000Z",
  "camera_id": "00000000-0000-0000-0000-000000000001",
  "frame_seq": 1042,
  "detections": [
    {
      "track_id": 4,
      "bbox": {
        "x1": 0.25,
        "y1": 0.40,
        "x2": 0.55,
        "y2": 0.85
      },
      "label": "Person (ID 4)",
      "color": "#00FF00",
      "metadata": {
        "confidence": 0.94
      }
    }
  ],
  "zones": [
    {
      "zone_id": "zone-1",
      "zone_name": "Restricted Area",
      "color": "#EF4444",
      "polygon": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.9], [0.1, 0.9]]
    }
  ]
}
```

> **Rules**:
> 1. Coordinates `x1, y1, x2, y2` and polygon vertices must be **normalized (0.0 to 1.0)** relative to frame width and height.
> 2. Always return HTTP 200 with `detections: []` if no objects are present (never 404).
> 3. Standard detection colors:
>    - Normal / Safe: `#00FF00`
>    - Warning / Anomaly: `#FFA500`
>    - Violation / Critical: `#FF0000`

---

## Local Development & Proxy Configuration

Add your service to `vite.config.ts` proxy table:
```ts
"/api/ucN": {
  target: "http://localhost:802N",
  changeOrigin: true,
  rewrite: (p) => p.replace(/^\/api\/ucN/, ""),
}
```
And add your port in `.env.example`:
```env
VITE_UCN_API_URL=http://localhost:802N
```
