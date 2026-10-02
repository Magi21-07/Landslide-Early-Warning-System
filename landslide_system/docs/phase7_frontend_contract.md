# Phase 7.1: Frontend Contract & Architecture

## 1. Stack & Dependencies
- **Location**: `/frontend`
- **Framework**: React 18+
- **Build Tool**: Vite (TypeScript template)
- **Routing**: `react-router-dom`
- **Styling**: Tailwind CSS, `lucide-react` for icons
- **State/Fetching**: `axios` (React Query planned for future phases)
- **GIS/Mapping**: `maplibre-gl`, `react-map-gl`

## 2. API Environment Mapping
The decoupled Vite SPA needs to connect to the FastAPI backend from Phase 1-6.
- **Base URL Variable**: `VITE_API_BASE_URL` (e.g., `http://localhost:8000`)
- **CORS Setup**: Ensure the backend's `CORS_ORIGINS` setting allows the Vite development server (usually `http://localhost:5173`).

## 3. Mapped Endpoints

### 3.1 Risk & Evaluation
- **POST** `/api/v1/risk/evaluate`: Evaluate real-time risk for a geographic point.
- **GET** `/api/v1/risk/latest`: Retrieve most recently calculated risk state for a `location_id`.
- **GET** `/api/v1/risk/history`: Retrieve historical risk assessments for a `location_id`.

### 3.2 Rainfall
- **GET** `/api/v1/rainfall/recent`: Retrieve recent daily CHIRPS rainfall observations.
- **GET** `/api/v1/rainfall/summary`: Calculate cumulative features and trigger states.

### 3.3 Geospatial
- **GET** `/api/v1/geospatial/risk-map`: Retrieve latest risk assessments formatted as a GeoJSON FeatureCollection.

## 4. Dashboard Architecture Planning
The dashboard will implement a 3-pane professional GIS monitoring layout:

### LEFT PANE: Controls & Navigation
- Location list / Saved monitoring points
- System-wide filter controls (Date ranges, Risk level thresholds)
- Navigation menu

### CENTER PANE: Analytics & Details
- Selected-location details (lat/lon, elevation, etc.)
- Susceptibility gauges
- Rainfall time-series charts (1D, 3D, 7D, 15D)
- Risk matrix visualization
- Recent history timeline

### RIGHT PANE: Interactive GIS Map
- Full MapLibre GL JS instance
- Risk zones and polygon overlays mapped via the `/geospatial/risk-map` GeoJSON endpoint
- Interactive location markers
- Map controls (Zoom, basemap toggle) and thematic legend
