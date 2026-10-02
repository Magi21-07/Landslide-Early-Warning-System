# Phase 7: GIS Monitoring Dashboard — Architecture & Reference Documentation

## Overview

Phase 7 implements a decoupled, React-based GIS monitoring frontend for the Landslide Early Warning System (LEWS). It connects to the Phase 1–6 FastAPI backend via a centralized Axios client and renders live geospatial risk data using MapLibre GL JS.

The dashboard follows a **mission-control / SCADA aesthetic**: high data density, dark-mode, monospaced typography, and zero fake data.

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Framework | React | 18.x |
| Build Tool | Vite | 8.x |
| Language | TypeScript | 5.x |
| Map Engine | MapLibre GL JS | 4.x |
| HTTP Client | Axios | 1.x |
| Charting | Recharts | 2.x |
| Styling | Tailwind CSS | 4.x |
| Icons | Lucide React | latest |

---

## Directory Structure

```
frontend/
├── src/
│   ├── App.tsx                    # Root: global state, layout, data fetching
│   ├── main.tsx                   # React entry point
│   ├── index.css                  # Global Tailwind CSS
│   ├── components/
│   │   ├── Header.tsx             # Compact system title + status bar
│   │   ├── Sidebar.tsx            # Monitoring list: search, filter, coord search
│   │   ├── DetailsPanel.tsx       # 7-section location detail readout
│   │   ├── MapArea.tsx            # Wrapper that passes props to RiskMap
│   │   ├── RiskMap.tsx            # MapLibre GL JS map + layers + controls
│   │   ├── RainfallChart.tsx      # Recharts bar chart: 15-day rainfall trace
│   │   └── StatusBar.tsx          # Footer: API/Model/DB status from backend
│   ├── services/
│   │   └── api.ts                 # Centralized Axios client + all endpoint methods
│   └── utils/
│       └── riskStyles.ts          # Single source of truth: risk level → visual styles
├── .env                           # Environment variable: VITE_API_BASE_URL
├── vite.config.ts
├── tailwind.config.js
└── package.json
```

---

## Architecture: State Flow

All global state is owned by `App.tsx`. No component shares state with a sibling directly.

```
App.tsx (State Owner)
├── selectedLocationId (string | null)
├── locations (any[])             ← derived from GeoJSON features
├── mapData (GeoJSON | null)      ← from /geospatial/risk-map
├── search (string)               ← lifted from Sidebar
├── riskFilter (string)           ← lifted from Sidebar
└── customView ({center, zoom})   ← set by coordinate search

         ┌──────────────────────────────────────┐
         │                                      │
    Sidebar.tsx          DetailsPanel.tsx      MapArea.tsx
    (renders list)       (renders detail)      (wraps RiskMap)
    ↓ onSelect()         ↓ location prop       ↓ multiple props
    sets selectedId      reads selectedLoc     syncs filter, selection
                         embeds RainfallChart   calls flyTo/fitBounds
```

---

## FastAPI Integration

### Base URL
Configured via `.env`:
```
VITE_API_BASE_URL=http://localhost:8000
```

### API Client (`services/api.ts`)
All HTTP communication routes through one Axios instance with:
- **10-second timeout** on all requests
- **Global error interceptor** (logs, re-rejects)
- **No scattered `fetch()` calls** in components

### Active Endpoints

| Method | Path | Used By | Purpose |
|---|---|---|---|
| `GET` | `/` | `App.tsx` | System status & model version |
| `GET` | `/api/v1/geospatial/risk-map` | `App.tsx` | GeoJSON feature collection |
| `POST` | `/api/v1/risk/evaluate` | `App.tsx` | Coordinate-based point risk |
| `GET` | `/api/v1/risk/history` | `api.ts` (defined, not yet wired to UI) | Risk history |
| `GET` | `/api/v1/rainfall/recent` | `RainfallChart.tsx` | 15-day daily trace |
| `GET` | `/api/v1/rainfall/summary` | `api.ts` (defined, not yet wired to UI) | Rainfall summary |

---

## GeoJSON Handling

1. `App.tsx` fetches `/api/v1/geospatial/risk-map` once on mount.
2. The raw GeoJSON `FeatureCollection` is stored in `mapData` and passed to `RiskMap`.
3. Feature `properties` are extracted as the `locations` array for the Sidebar list.
4. `RiskMap` calls `source.setData(mapData)` when the prop updates — **no redundant network call**.
5. MapLibre layers paint directly from `feature.properties.risk_level` via `match` expressions built by `getMapPaintMatchExpression()`.

---

## Risk Level Visual System (`riskStyles.ts`)

The `RISK_LEVELS` dictionary is the **single source of truth** for all visual representations of risk:

| Level | Fill Color | Marker Color | Text Class |
|---|---|---|---|
| `LOW` | `#10b981` (emerald) | `#10b981` | `text-emerald-700` |
| `MODERATE` | `#f59e0b` (amber) | `#f59e0b` | `text-amber-700` |
| `HIGH` | `#ef4444` (red) | `#ef4444` | `text-red-700` |
| `CRITICAL` | `#7f1d1d` (deep red) | `#7f1d1d` | `text-red-900` |
| `UNKNOWN` | `#94a3b8` (slate) | `#94a3b8` | `text-slate-700` |

`getRiskStyle(level)` safely returns `UNKNOWN` for any unrecognized backend string.

---

## Monitoring Panel (Sidebar)

- **Text search**: filters `location.name || location.id || location.location_id` client-side (no re-fetch).
- **Risk level dropdown**: filters to `ALL | LOW | MODERATE | HIGH | CRITICAL`.
- **Coordinate Search**: validates lat ∈ [-90,90], lon ∈ [-180,180] → POSTs to `/risk/evaluate` → `flyTo` on map → populates DetailsPanel.
- **Stale badge**: renders if `is_stale === true OR data_age_hours > 24`.
- **Selected state**: left blue border + background highlight.

---

## Location Details Panel

Seven structured sub-sections per selected location:

| Section | Fields Displayed |
|---|---|
| **Location Info** | Name/ID, Latitude, Longitude |
| **Dynamic Risk** | Risk level (colored badge + glow), Risk score |
| **Stale Warning** | Conditional red banner if data is stale |
| **Static Susceptibility** | Susceptibility score, susceptibility class |
| **Rainfall Analytics** | 1D / 3D / 7D / 15D cumulative + live chart |
| **Data Integrity** | Source, observation date, freshness state |
| **Evaluation Factors** | Array of backend-provided explanation strings |

Empty state: rendered when `location === null` with "AWAITING TARGET SELECTION" placeholder.

---

## Rainfall Chart (`RainfallChart.tsx`)

- Fetches `GET /api/v1/rainfall/recent?latitude=&longitude=&days=15`.
- Re-fetches automatically when `latitude` or `longitude` props change.
- Uses an `isMounted` flag to prevent state updates on unmounted components.
- States: **Loading** (spinner), **Error** (message), **Empty** ("NO TRACE DATA"), **Data** (Recharts BarChart).
- Trigger state badge: displayed above chart using `getRiskStyle(triggerState)`.

---

## Map Controls

| Control | Type | Behavior |
|---|---|---|
| Zoom / Compass | MapLibre Native | Top-right |
| Fullscreen | MapLibre Native | Top-right |
| Geolocate | MapLibre Native | Top-right |
| Reset View | Custom React Button | `flyTo(defaultCenter, defaultZoom)` |
| Fit to Data | Custom React Button | `fitBounds(allFeatureCoords, padding: 50)` |
| Layer Toggle | Custom React UI | `setLayoutProperty('visibility', ...)` for Polygons / Points |
| Opacity Slider | Custom React UI | `setPaintProperty('fill-opacity', value)` |
| Risk Legend | Custom React UI | Bottom-left, reads from `RISK_LEVELS` |

---

## Stale Data Handling

Stale detection logic (client-side evaluation of backend-provided fields):
```ts
const isStale = location.is_stale === true || location.data_age_hours > 24;
```

Renders in two places:
1. **Sidebar card**: amber `STALE` badge top-right of location name.
2. **DetailsPanel**: full-width red `WARNING: STALE DATA DETECTED` bar.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | FastAPI backend root URL |

Create a `.env` file in `frontend/` to override:
```
VITE_API_BASE_URL=http://your-server:8000
```

---

## Local Development

### Prerequisites
- Node.js 18+
- Python 3.10+
- Phase 1–6 backend working

### Step 1 — Start the FastAPI Backend

```bash
# From project root, with virtual environment active:
uvicorn src.api.main:app --reload
# Backend available at: http://localhost:8000
```

### Step 2 — Start the Frontend Dev Server

```bash
cd frontend
npm install       # first time only
npm run dev
# Dashboard available at: http://localhost:5173
```

---

## Production Build

```bash
cd frontend
npm run build
# Output in frontend/dist/
```

Serve the `dist/` directory with any static file server (Nginx, `serve`, Vite preview):
```bash
npx serve dist
```

---

## Known Limitations & Future Work

1. **Risk History endpoint** (`/risk/history`) is defined in `api.ts` but not yet wired to a UI chart — planned for Phase 8.
2. **Rainfall Summary endpoint** (`/rainfall/summary`) is defined but not used — planned for Phase 8.
3. **Bundle size**: ~484KB gzip. Dynamic `import()` code-splitting for MapLibre/Recharts would reduce initial load.
4. **No authentication**: The frontend assumes the FastAPI backend is accessible on the local network. Auth/CORS hardening is a backend concern (Phase 1–6).
5. **Map filter timing**: `searchQuery`/`riskFilter` effects guard with `isStyleLoaded()`. If style loads after filter state changes, the first filter pass is skipped until next interaction. Acceptable for current use.
