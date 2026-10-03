# FC-3 Static Factor Validation Report

Generated: 2026-10-02

---

## Factor Inventory

### 1. Soil Clay Content

| Field | Value |
|-------|-------|
| **Factor Name** | `clay_percent` |
| **Source API/Dataset** | SoilGrids v2 REST API |
| **Exact Endpoint** | `https://rest.isric.org/soilgrids/v2.0/properties/query` |
| **Query Parameters** | `lat=<lat>&lon=<lon>&property=clay&depth=0-5cm&value=mean` |
| **Native Resolution** | 250 m (SoilGrids v2) |
| **CRS** | EPSG:4326 |
| **Unit (Native)** | decig/kg |
| **Unit (Stored)** | % (divided by 10) |
| **Extraction Method** | HTTP GET REST API — `properties.layers[name=clay].depths[label=0-5cm].values.mean` |
| **Transformation** | `clay_pct = raw_value / 10.0` |
| **Range Validation** | `0.0 ≤ clay_percent ≤ 100.0`; out-of-range values discarded → FALLBACK |
| **Missing-value Behavior** | Property absent → use FALLBACK default (25.0%), mark `status=FALLBACK` |
| **Fallback Value** | `25.0` (%)  |
| **REAL Mode** | Live SoilGrids call, `status=REAL` |
| **DEGRADED Mode** | API failure → `status=FALLBACK`, `fallback_used=True` |
| **MOCK/TEST Mode** | Unit test fixtures only — never in production |
| **Current Model Usage** | ❌ NOT INCLUDED IN ACTIVE INFERENCE VECTOR |
| **Future Model Usage** | Candidate feature for Phase retraining (clay correlates with shear strength & permeability) |
| **API Exposure Key** | `spatial_metrics.clay_percent` |
| **Validation Status** | ✅ Implemented, unit tests pass |

---

### 2. Hydraulic Capacity (Field Capacity, wv0033)

| Field | Value |
|-------|-------|
| **Factor Name** | `hydraulic_capacity` |
| **Definition** | Volumetric water content at 33 kPa (field capacity); proxy for water-holding ability |
| **Source API/Dataset** | SoilGrids v2 REST API |
| **Exact Endpoint** | `https://rest.isric.org/soilgrids/v2.0/properties/query` |
| **Query Parameters** | `property=wv0033&depth=0-5cm&value=mean` |
| **Native Resolution** | 250 m |
| **CRS** | EPSG:4326 |
| **Unit (Native)** | cm³/dm³ |
| **Unit (Stored)** | % vol (divided by 10) |
| **Extraction Method** | HTTP GET REST API — `properties.layers[name=wv0033].depths[0-5cm].values.mean` |
| **Transformation** | `hyd_cap = raw_value / 10.0` |
| **Range Validation** | `0.0 ≤ hydraulic_capacity ≤ 100.0` |
| **Missing-value Behavior** | → FALLBACK default (15.0%) |
| **Fallback Value** | `15.0` (%) |
| **REAL Mode** | Live SoilGrids call |
| **DEGRADED Mode** | → FALLBACK |
| **Current Model Usage** | ❌ NOT INCLUDED IN ACTIVE INFERENCE VECTOR |
| **Future Model Usage** | Candidate for pore pressure / antecedent moisture modelling |
| **API Exposure Key** | `spatial_metrics.hydraulic_capacity` |
| **Validation Status** | ✅ Implemented |

---

### 3. Soil Depth (Absolute Depth to Bedrock)

| Field | Value |
|-------|-------|
| **Factor Name** | `soil_depth` |
| **Source API/Dataset** | SoilGrids v2 REST API — property `bdricm` |
| **Exact Endpoint** | `https://rest.isric.org/soilgrids/v2.0/properties/query` |
| **Query Parameters** | `property=bdricm&depth=0-5cm&value=mean` |
| **Native Resolution** | 250 m |
| **CRS** | EPSG:4326 |
| **Unit** | cm |
| **Extraction Method** | HTTP GET REST API |
| **Transformation** | None (cm as-is) |
| **Missing-value Behavior** | Not present in Phase-2 data; queried live via SoilGrids. If absent → `None` (no arbitrary default) |
| **Fallback Value** | `None` — no safe arbitrary soil depth default |
| **REAL Mode** | Live SoilGrids call |
| **DEGRADED Mode** | `soil_depth = None`, `status=FALLBACK` |
| **Current Model Usage** | ❌ NOT INCLUDED IN ACTIVE INFERENCE VECTOR |
| **Future Model Usage** | Candidate for infinite-slope stability analysis |
| **API Exposure Key** | `spatial_metrics.soil_depth` |
| **Validation Status** | ✅ Implemented; correctly returns None on failure |

---

### 4. Lithology Class

| Field | Value |
|-------|-------|
| **Factor Name** | `lithology_class` |
| **Intended Source** | Global Lithological Map (GLiM v1) GeoPackage |
| **Actual Status** | ⚠️ **MISSING** — No GLiM raster or vector in `data/raw/` or `data/processed/` |
| **Lookup Method** | NONE (dataset not ingested) |
| **Current Behavior** | Returns FALLBACK = `"Sedimentary"` with `status=FALLBACK` |
| **Coordinate Heuristics** | ❌ PROHIBITED — fallback class is NOT derived from lat/lon |
| **Fallback Value** | `"Sedimentary"` (configured constant) |
| **REAL Mode** | Requires GLiM GeoPackage ingestion (recommended action below) |
| **DEGRADED Mode** | Current state — FALLBACK, clearly marked |
| **Current Model Usage** | ❌ NOT INCLUDED IN ACTIVE INFERENCE VECTOR |
| **Future Model Usage** | Rock type → erodibility, shear strength class |
| **API Exposure Key** | `spatial_metrics.lithology_class` |
| **Validation Status** | ✅ Implemented as FALLBACK; test confirms no coordinate heuristic used |
| **Action Required** | Download GLiM v1 from https://www.geo.uni-hamburg.de/en/geologie/forschung/aquifer/glim.html and integrate via `vector_utils.align_vectors_to_grid()` |

---

### 5. Weathering Index

| Field | Value |
|-------|-------|
| **Factor Name** | `weathering_index` |
| **Intended Source** | Chemical weathering proxy (e.g. NDVI ratio, CRB model, or Granger map) |
| **Actual Status** | ❌ **UNAVAILABLE** — No validated dataset in repository |
| **Current Behavior** | Returns `None` — not a numeric zero, not a fallback constant |
| **Coordinate Heuristics** | ❌ PROHIBITED |
| **Fallback Value** | `None` |
| **REAL Mode** | Requires validated weathering proxy dataset |
| **Current Model Usage** | ❌ NOT INCLUDED IN ACTIVE INFERENCE VECTOR |
| **Future Model Usage** | Weathering state → rock mass quality index |
| **API Exposure Key** | `spatial_metrics.weathering_index` |
| **Validation Status** | ✅ Correctly returns None; test verifies no heuristic substitution |
| **Action Required** | Identify and ingest appropriate regional weathering dataset |

---

### 6. Distance to Nearest River

| Field | Value |
|-------|-------|
| **Factor Name** | `distance_to_river_m` |
| **Source API/Dataset** | OpenStreetMap via Overpass API |
| **Exact Endpoint** | `https://overpass-api.de/api/interpreter` |
| **Query** | `way["waterway"~"river|stream"]` within ±0.03° bounding box |
| **Native Resolution** | OSM contributor resolution (varies) |
| **CRS** | EPSG:4326 (query) → metres (result) |
| **Unit** | Metres |
| **Extraction Method** | Overpass QL POST, iterate all Way geometry nodes, compute min perpendicular segment distance using planar Haversine approximation |
| **Distance Algorithm** | `_min_distance_to_way_m()` — per-segment not centroid |
| **Transformation** | Geodesic metres; no degree-Euclidean approximation |
| **Missing-value Behavior** | No feature in bbox → bbox-threshold distance (~3330m), `status=REAL`, note=`NO_FEATURE_FOUND` |
| **API Failure Behavior** | → FALLBACK (1200.0m), `status=FALLBACK` |
| **Range Validation** | `distance ≥ 0.0` enforced |
| **Fallback Value** | `1200.0` m |
| **REAL Mode** | Live Overpass call |
| **DEGRADED Mode** | → FALLBACK |
| **Current Model Usage** | ❌ NOT INCLUDED IN ACTIVE INFERENCE VECTOR |
| **Future Model Usage** | Hydrological triggering proxy |
| **API Exposure Key** | `spatial_metrics.distance_to_river_m` |
| **Validation Status** | ✅ Implemented; geometry tests pass |

---

### 7. Distance to Nearest Road/Infrastructure

| Field | Value |
|-------|-------|
| **Factor Name** | `distance_to_road_m` |
| **Source API/Dataset** | OpenStreetMap via Overpass API |
| **Exact Endpoint** | `https://overpass-api.de/api/interpreter` |
| **Query** | `way["highway"]` within ±0.03° bounding box |
| **Unit** | Metres |
| **Extraction Method** | Same geometry algorithm as distance_to_river_m |
| **Transformation** | Geodesic metres |
| **Fallback Value** | `450.0` m |
| **REAL Mode** | Live Overpass call |
| **DEGRADED Mode** | → FALLBACK |
| **Current Model Usage** | ❌ NOT INCLUDED IN ACTIVE INFERENCE VECTOR |
| **Future Model Usage** | Slope disturbance / cut-slope stability indicator |
| **API Exposure Key** | `spatial_metrics.distance_to_road_m` |
| **Validation Status** | ✅ Implemented |

---

## Factor Completeness Summary

| Factor | Source | Status | Notes |
|--------|--------|--------|-------|
| Elevation | Open-Meteo REST | ✅ ACTIVE (Phase-2) | In ML inference vector |
| Slope | Derived from elevation | ✅ ACTIVE (Phase-2) | In ML inference vector |
| Soil Clay % | SoilGrids v2 | ✅ IMPLEMENTED | FC-3, not in active ML |
| Hydraulic Capacity | SoilGrids v2 | ✅ IMPLEMENTED | FC-3, not in active ML |
| Soil Depth | SoilGrids v2 BDRICM | ✅ IMPLEMENTED | FC-3, None on failure |
| Lithology | GLiM v1 | ⚠️ FALLBACK ONLY | Dataset not ingested |
| Weathering | No dataset | ❌ UNAVAILABLE | Returns None |
| Distance to River | Overpass OSM | ✅ IMPLEMENTED | FC-3, Haversine geometry |
| Distance to Road | Overpass OSM | ✅ IMPLEMENTED | FC-3, Haversine geometry |
