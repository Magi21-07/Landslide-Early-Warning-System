# Landslide Early Warning System - Technical Documentation

This document provides a comprehensive overview of the system architecture, mathematical models, and operational pipelines that power the Landslide Early Warning System.

## 1. System Overview & Built Components

### Frontend Architecture (`/frontend`)
The frontend is a robust, responsive React/TypeScript application designed for high data density and situational awareness. 
**Implemented UI Components:**
* **Target Selection Sidebar:** Displays a searchable, filterable list of tracking targets with dynamically rendered risk badges.
* **Dynamic Risk Panel & Static Susceptibility Panel:** Provides real-time metrics including probability scaling and terrain-aware susceptibility profiles.
* **15-Day Rainfall Bar Chart:** A deterministic Recharts-powered visualization of cumulative precipitation.
* **Trigger State Trace Panel:** Highlights critical threshold tracking relative to cumulative rainfall variables.
* **System Data Integrity Footer:** Displays the overarching data source mode (Live CHIRPS vs. Synthetic Mock) and health metrics.
* **MapLibre Canvas (`RiskMap.tsx`):** A high-performance WebGL map canvas rendering dynamic GeoJSON layers.

**Key Frontend Features:**
* **Target Switching:** Instant, reactive re-hydration of panels based on target selection.
* **`flyTo` Camera Pan:** Cinematic location-aware viewport bounding `map.flyTo({ center: [lon, lat], zoom: 11 })` upon target selection.
* **Interactive Layer Opacity Controls:** Fine-tuned transparency toggles for overlapping analysis layers.
* **Real-Time Risk Severity Badges:** Reactive rendering of `<span style={{ color: getRiskStyle(risk).color }}>` badges.

### Backend API (`/backend/src/api`)
The backend is powered by FastAPI, exposing strict Pydantic-validated RESTful endpoints.
**Operational Routes:**
* `POST /api/v1/risk/evaluate`: Calculates complete static and dynamic risk metrics for a specific coordinate. Accepts `{ "latitude": float, "longitude": float }` payload. Supports the `?mock=true` query parameter for deterministic offline data generation.
* `GET /api/v1/rainfall/recent`: Retrieves a 15-day CHIRPS time series or synthetic fallback trace. Parameters: `latitude`, `longitude`, `days`.
* `GET /api/v1/geospatial/risk-map`: Produces dynamic MapLibre-compatible GeoJSON `FeatureCollection` datasets detailing polygon centroids, geometries, target IDs, names, and computed risk bounds.
* `GET /api/v1/risk/targets`: Endpoint resolving stored targets for the Sidebar list.

**Error-Handling Fallbacks:** Graceful HTTP `502 Bad Gateway` and `400 Bad Request` catching for pipeline or coordinate out-of-bounds errors, supplemented by synthetic generators for offline capability.

### Data Pipelines & ETL (`/backend/src/etl`)
* **GEE Integration:** Google Earth Engine executes geospatial queries to extract NASADEM elevations and CHIRPS precipitation collections.
* **Fallback Mechanism:** A process-level latch (`_GEE_INIT_FAILED`) evaluates `ee.Initialize()` exactly once at startup. If initialization fails (due to absent credentials or network conditions), the flag is flipped, suppressing cascading `403 Forbidden` errors on subsequent API calls.
* **Coordinate-Driven Synthetic Rainfall:** In fallback mode, deterministic daily rainfall arrays are generated using `hashlib.md5(lat_lon)` seeds to provide location-unique metrics dynamically scaled by baseline factors like `base_rain = (abs(lat) * 1.5 + abs(lon) * 0.8) % 35.0`.

## 2. Risk Calculation Engine & Mathematical Logic

The risk calculation engine evaluates terrain hazards and live meteorological variables to output bounded hazard levels.

### Static Susceptibility ($S$)
Static susceptibility represents the absolute physical predisposition of a terrain surface to fail.
**Factors involved:** Terrain slope ($\theta$ in degrees), DEM elevation ($E$ in meters), and geographic spatial bounds.

**Formula / Logic:**
$$S = f(\text{Slope}, \text{Elevation}) \in [0, 1]$$

**Geographic profiling rules:**
* **Plain/Flat regions** (e.g., Jaipur: $26.0^\circ$N - $27.5^\circ$N, $75.0^\circ$E - $76.5^\circ$E): Flat/mild terrain defaults to near-zero slope hazard ($\theta \approx 2.1^\circ$), forcing $S \approx 0.08$. Risk remains locked to `LOW`.
* **Steep Mountainous regions** (e.g., Shimla/Hamirpur: $30.0^\circ$N - $33.0^\circ$N, $76.0^\circ$E - $78.5^\circ$E): High slope hazards ($\theta \approx 28.5^\circ$), pushing susceptibility to $S \approx 0.74$.

### Dynamic Rainfall Metrics ($R$)
Rainfall acts as the immediate triggering mechanism. It is analyzed via cumulative rolling calculations.
$$R_{1\text{D}} = \sum_{i=15}^{15} d_i, \quad R_{3\text{D}} = \sum_{i=13}^{15} d_i, \quad R_{7\text{D}} = \sum_{i=9}^{15} d_i, \quad R_{15\text{D}} = \sum_{i=1}^{15} d_i$$
**Strict Monotonic Accumulation Constraint:** $R_{1\text{D}} \le R_{3\text{D}} \le R_{7\text{D}} \le R_{15\text{D}}$ is enforced automatically by sequential summation logic.

### Combined Dynamic Risk Score ($P$)
The final combined risk probability interpolates the static terrain hazard against the acute dynamic rainfall load relative to standard regional capacity thresholds ($T_{\text{threshold}}$).

**Combined Risk Probability score calculation:**
$$P = \sigma\left( w_1 \cdot S + w_2 \cdot \frac{R_{15\text{D}}}{T_{\text{threshold}}} \right)$$
*(where $\sigma$ limits the output strictly to $[0, 1]$).*

**Risk Level Classification Mapping:**
* $P < 0.30 \implies \mathbf{LOW}$
* $0.30 \le P < 0.55 \implies \mathbf{MODERATE}$
* $0.55 \le P < 0.75 \implies \mathbf{HIGH}$
* $P \ge 0.75 \implies \mathbf{CRITICAL}$

### Trigger State Logic
Threshold condition comparisons operate on empirical intensity-duration curves where continuous cumulative rain ($R_{\text{cumulative}}$) is assessed against $I = a \cdot D^{-b}$. Trigger limits update dynamically per state (e.g., `NOMINAL` vs `WARNING`).

## 3. Machine Learning Model & Heuristic Architecture

### Model Specifications
* **Model Type:** RandomForest Classifier / Calibrated Heuristic Engine.
* **Input Feature Vector:** $X = [\text{Slope}, \text{Elevation}, R_{3\text{D}}, R_{15\text{D}}, \text{Soil Moisture}]$.
* **Target Variable:** The terminal prediction equates to a continuous landslide occurrence probability score mapping to the final discrete risk class (`LOW`, `MODERATE`, `HIGH`, `CRITICAL`).

### Inference Lifecycle
1. **Startup Execution:** FastAPI mounts singleton engine instances, instantiating model dependencies in memory via `_build_mock_predictor` or localized Joblib weights.
2. **Validation:** Pydantic validators cleanse the inference schema.
3. **Inference Pipeline:** Data ingested from the ETL tier scales against baseline weights to emit the deterministic, non-linear classification bounds.

## 4. Geospatial Map & Layer Pipeline

### GeoJSON Generation
The endpoint `/api/v1/geospatial/risk-map` serializes queried SQLite targets into a unified `GeoJSON FeatureCollection`. 
Target IDs act as relational keys. Points map natively to centroids (`PointGeometry(coordinates=[lon, lat])`) and carry embedded `properties` payloads containing explicit `{ "risk_level": "HIGH", "name": "Shimla Slope" }` schema values.

### MapLibre Layer Binding
MapLibre interprets the resulting FeatureCollections dynamically without unmounting the map instance.
* Source: `risk-targets` handles the streaming geometries.
* `risk-target-polygons`: Uses discrete mapbox-gl layer paint specifications to render visual hierarchies:

```json
"fill-color": [
  "match",
  ["get", "risk_level"],
  "LOW", "#10B981",
  "MODERATE", "#F59E0B",
  "HIGH", "#EF4444",
  "CRITICAL", "#7F1D1D",
  "#6B7280"
]
```
* `risk-target-labels`: A `symbol` layer anchors human-readable location references (e.g., `"text-field": ["get", "name"]`) cleanly over the active polygons, dynamically redrawing on style/filter transitions.
