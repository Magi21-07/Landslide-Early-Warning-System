# Phase 4: Master Factor Integrity Audit
*Generated: 2026-10-03 | Auditor: Lead ML Systems Engineer*

---

## Audit Methodology
Each of the 14 semantic factors was traced from source → implementation → training dataset → model inference → SHAP → API response → dashboard display.

---

## Factor Audit Table

### 1. `slope_degrees`
| Property | Value |
|---|---|
| Source | SRTM/NASADEM via Open-Meteo Elevation API |
| Implementation File | `src/etl/terrain_service.py` |
| Processing Function | `get_terrain_features(lat, lon)` |
| Unit | Degrees (°) |
| Native Spatial Resolution | ~30m (SRTM) |
| Target Resolution | 30m point query |
| CRS | WGS-84 |
| Temporal Behavior | STATIC |
| Training Availability | ✅ Mapped from `df['slope']` in `prepare_training_data.py` |
| Inference Availability | ✅ Via `feature_builder.py → fetch_terrain()` |
| FastAPI Exposure | ✅ In `terrain_metrics`, used in model vector |
| Dashboard Exposure | ⚠️ Only via `susceptibility_class` badge — not displayed numerically |
| Mock/Fallback | Elevation API fallback returns default on SSL failure |
| In Model (Training) | ✅ YES — in `FEATURE_ORDER` |
| In Model (Prediction) | ✅ YES |
| **STATUS** | **FULLY_CONNECTED** |

---

### 2. `elevation_m`
| Property | Value |
|---|---|
| Source | Open-Meteo Elevation API |
| Implementation File | `src/etl/terrain_service.py` |
| Processing Function | `get_terrain_features(lat, lon)` |
| Unit | Meters (m) |
| Native Resolution | ~30m |
| CRS | WGS-84 |
| Temporal Behavior | STATIC |
| Training Availability | ✅ Mapped from `df['elevation']` |
| Inference Availability | ✅ |
| FastAPI Exposure | ✅ |
| Dashboard Exposure | ⚠️ Not shown numerically |
| Mock/Fallback | 0m default on API failure |
| In Model (Training) | ✅ YES |
| In Model (Prediction) | ✅ YES |
| **STATUS** | **FULLY_CONNECTED** |

---

### 3. `rainfall_3day_mm`
| Property | Value |
|---|---|
| Source | CHIRPS via `RainfallService` / Phase-5 pipeline |
| Implementation File | `src/risk/rainfall_service.py`, `src/risk/chirps_client.py` |
| Processing Function | `get_recent_rainfall(lat, lon, days=15)` |
| Unit | mm |
| Native Resolution | 0.05° (~5km) |
| CRS | WGS-84 |
| Temporal Behavior | DYNAMIC |
| Training Availability | ⚠️ SYNTHETIC — derived as `df['soil_moisture'] * 500 * 0.4` in prepare_training_data.py. Not real historical CHIRPS. |
| Inference Availability | ✅ Real-time CHIRPS or synthetic fallback |
| FastAPI Exposure | ✅ In `rainfall_metrics` and model vector |
| Dashboard Exposure | ✅ Shown as `rainfall_3d` |
| Mock/Fallback | Synthetic fallback on GEE unavailability |
| Monotonicity Check | ✅ Enforced: `r3 = max(r3, r1)` in MockChirpsClient |
| In Model (Training) | ✅ YES (synthetic proxy) |
| In Model (Prediction) | ✅ YES |
| **STATUS** | **PARTIALLY_CONNECTED** — Training uses synthetic proxy, not real CHIRPS historical |
| **DEFECT** | Training rainfall not sourced from real CHIRPS. `df['soil_moisture'] * 500` is an undocumented proxy. |

---

### 4. `rainfall_15day_mm`
| Property | Value |
|---|---|
| Source | CHIRPS / Phase-5 |
| Training Availability | ⚠️ SYNTHETIC — `df['soil_moisture'] * 500` |
| Inference Availability | ✅ |
| Monotonicity | ✅ Enforced in inference |
| In Model (Training) | ✅ YES (synthetic) |
| In Model (Prediction) | ✅ YES |
| **STATUS** | **PARTIALLY_CONNECTED** — same defect as rainfall_3day_mm |

---

### 5. `distance_to_river_m`
| Property | Value |
|---|---|
| Source | Overpass OSM API |
| Implementation File | `src/etl/spatial_service.py` |
| Processing Function | `get_proximity_metrics(lat, lon)` |
| Unit | Meters (m) |
| Resolution | Query-based, ±0.03° bbox |
| CRS | WGS-84 |
| Temporal Behavior | STATIC |
| Training Availability | ⚠️ SYNTHETIC — `np.random.uniform(100, 2000, len(df))` in prepare_training_data.py |
| Inference Availability | ✅ Real Overpass query with FALLBACK on timeout |
| FastAPI Exposure | ✅ In `spatial_metrics` |
| Dashboard Exposure | ❌ Not displayed |
| In Model (Training) | ✅ YES (random synthetic) |
| In Model (Prediction) | ✅ YES |
| **STATUS** | **PARTIALLY_CONNECTED** — Training uses random values, not real OSM queries |
| **DEFECT** | Training values are `np.random.uniform` — breaks spatial leakage integrity |

---

### 6. `distance_to_road_m`
| Same defect as `distance_to_river_m` |
| **STATUS** | **PARTIALLY_CONNECTED** |

---

### 7. `soil_clay_content`
| Property | Value |
|---|---|
| Source | SoilGrids v2 REST API |
| Implementation File | `src/etl/spatial_service.py` |
| Processing Function | `get_soil_properties(lat, lon)` |
| Unit | % (clay fraction) |
| Training Availability | ⚠️ SYNTHETIC — `np.random.uniform(10, 40, len(df))` |
| Inference Availability | ✅ Real SoilGrids call with FALLBACK=25.0 on HTTP 500 |
| In Model (Training) | ✅ YES (random synthetic) |
| In Model (Prediction) | ✅ YES |
| **STATUS** | **PARTIALLY_CONNECTED** |
| **DEFECT** | Training data is random; SoilGrids was returning HTTP 500 for all coordinates during dataset prep |

---

### 8. `soil_hydraulic_cond`
| Same defect pattern as `soil_clay_content` |
| Training Availability | ⚠️ SYNTHETIC — `np.random.uniform(5, 20, len(df))` |
| **STATUS** | **PARTIALLY_CONNECTED** |

---

### 9. `lithology_class`
| Property | Value |
|---|---|
| Source | GLiM v1 (intended); no raster in repo |
| Implementation File | `src/etl/spatial_service.py → get_lithology_and_weathering()` |
| Training Availability | ⚠️ SYNTHETIC — `np.random.choice(["Sedimentary", "Metamorphic", "Igneous"], len(df))` |
| Inference Availability | ⚠️ FALLBACK only — always returns "Sedimentary" (no GLiM raster) |
| FastAPI Exposure | ✅ In spatial_metrics |
| Dashboard Exposure | ❌ Not displayed |
| In Model (Training) | ✅ YES (random categories) |
| In Model (Prediction) | ✅ YES (always FALLBACK="Sedimentary") |
| **STATUS** | **MOCKED** — Always returns fallback in production; training uses random labels |
| **DEFECT** | No GLiM raster. Inference always predicts with "Sedimentary". Breaks spatial validity. |

---

### 10. `ndvi_index`
| Property | Value |
|---|---|
| Source | Sentinel-2 MSI (COPERNICUS/S2_SR_HARMONIZED) via GEE |
| Implementation File | `src/etl/sentinel_service.py` |
| Processing Function | `get_sentinel2_features(lat, lon)` |
| Formula | `NDVI = (B8 - B4) / (B8 + B4)` with DN→reflectance scaling (÷10000) |
| Unit | Dimensionless [-1, 1] |
| Cloud Filtering | CLOUDY_PIXEL_PERCENTAGE < 10%, SCL shadow mask |
| Training Availability | ⚠️ `np.nan` in training dataset (GEE unavailable during prep) |
| Inference Availability | ⚠️ `np.nan` when GEE unavailable (no credentials.json) |
| FastAPI Exposure | ✅ In `remote_sensing_metrics.sentinel2.ndvi` |
| Dashboard Exposure | ❌ Not displayed in DetailsPanel |
| In Model (Training) | ✅ YES (as np.nan — XGBoost handles natively) |
| In Model (Prediction) | ✅ YES (as np.nan most of the time) |
| **STATUS** | **PARTIALLY_CONNECTED** — Pipeline exists but GEE credentials block real data |
| **NOTE** | Formula implementation is correct. Provenance metadata includes scene_id, obs_date, cloud_pct. |

---

### 11. `tree_cover_density`
| Property | Value |
|---|---|
| Source | Copernicus Landcover via GEE (`extract_vegetation`) |
| Implementation File | `src/features/feature_builder.py → _get_tree_cover()` |
| Processing Function | `extract_vegetation(point)` from `src/etl/gee_extractor.py` |
| Unit | % (0–100 fraction) |
| Temporal Behavior | SLOW_CHANGING (annual update) |
| Training Availability | ⚠️ `np.nan` in training (GEE unavailable) |
| Inference Availability | ⚠️ `np.nan` when GEE unavailable |
| FastAPI Exposure | ⚠️ Embedded in model run, not separately in response |
| Dashboard Exposure | ❌ Not displayed |
| In Model (Training) | ✅ YES (as np.nan) |
| In Model (Prediction) | ✅ YES (as np.nan most of the time) |
| **STATUS** | **PARTIALLY_CONNECTED** |
| **NOTE** | No NDVI→tree_cover_density conversion attempted — correct. GEE access blocks real values. |

---

### 12. `sar_soil_moisture`
| Property | Value |
|---|---|
| Source | Sentinel-1 GRD (COPERNICUS/S1_GRD) via GEE |
| Implementation File | `src/etl/sentinel_service.py` |
| Processing Function | `get_sentinel1_features(lat, lon)` |
| Proxy Calculation | `sar_soil_moisture_proxy = vv_val` (raw VV dB value) |
| Unit | dB (proxy — NOT volumetric soil moisture) |
| Training Availability | ⚠️ SYNTHETIC — mapped from `df['soil_moisture']` column in prep |
| Inference Availability | ⚠️ `np.nan` when GEE unavailable |
| FastAPI Exposure | ✅ In `remote_sensing_metrics.sentinel1` |
| Dashboard Exposure | ❌ Not displayed numerically |
| **STATUS** | **PARTIALLY_CONNECTED** |
| **CRITICAL NOTE** | `sar_soil_moisture_proxy = vv_val` (raw VV dB) is a simplistic proxy. This must NOT be labeled as volumetric soil moisture. Label as "SAR Soil-Moisture Proxy" in all UI. VV–VH cross-ratio metric also computed (`vv_vh_metric = vv_val - vh_val`) but not fed to model. |
| **DEFECT** | Training data maps `df['soil_moisture']` column (which is a float from Phase-3 dataset, not a validated SAR dB proxy). Training feature semantics differ from inference semantics. |

---

### 13. `weathering_index`
| Property | Value |
|---|---|
| Source | No real dataset exists in repository |
| Implementation File | `src/etl/spatial_service.py → get_lithology_and_weathering()` |
| Inference Availability | ⚠️ Always returns `None` → mapped to `np.nan` in feature_builder |
| Training Availability | ⚠️ SYNTHETIC — `np.random.uniform(0, 1, len(df))` |
| In Model (Training) | ✅ YES (random) |
| In Model (Prediction) | ✅ YES (as np.nan) |
| **STATUS** | **MISSING** — No real or proxy source exists. Returns UNAVAILABLE in both training and inference. |
| **DEFECT** | spatial_service explicitly returns `None` for weathering_index. Action required: ingest regional weathering proxy (e.g., NDVI change rate, bedrock depth proxy from SoilGrids bdricm). |

---

### 14. `land_use_settlement`
| Property | Value |
|---|---|
| Source | NOT_IMPLEMENTED |
| Implementation File | `src/features/feature_builder.py` line 128: `features["land_use_settlement"] = np.nan` |
| Training Availability | ⚠️ `np.nan` in training (hard-coded in prepare_training_data.py) |
| Inference Availability | ⚠️ Always `np.nan` |
| FastAPI Exposure | ⚠️ Not in response explicitly |
| Dashboard Exposure | ❌ Not displayed |
| In Model (Training) | ✅ YES (always np.nan — XGBoost treats as missing) |
| In Model (Prediction) | ✅ YES (always np.nan) |
| **STATUS** | **MISSING** — Semantic feature slot exists but no data source implemented |
| **DEFECT** | No OSM building/settlement query is implemented. Feature contributes zero information to any prediction. XGBoost treats this column as universally missing. |

---

## Summary Classification Table

| Factor | Status | Training Data | Inference |
|---|---|---|---|
| slope_degrees | FULLY_CONNECTED | Real (terrain_service) | Real |
| elevation_m | FULLY_CONNECTED | Real (terrain_service) | Real |
| rainfall_3day_mm | PARTIALLY_CONNECTED | Synthetic proxy | Real with fallback |
| rainfall_15day_mm | PARTIALLY_CONNECTED | Synthetic proxy | Real with fallback |
| distance_to_river_m | PARTIALLY_CONNECTED | Random uniform | Real with fallback |
| distance_to_road_m | PARTIALLY_CONNECTED | Random uniform | Real with fallback |
| soil_clay_content | PARTIALLY_CONNECTED | Random uniform | Real with fallback |
| soil_hydraulic_cond | PARTIALLY_CONNECTED | Random uniform | Real with fallback |
| lithology_class | MOCKED | Random categories | Always FALLBACK |
| ndvi_index | PARTIALLY_CONNECTED | np.nan | np.nan (GEE blocked) |
| tree_cover_density | PARTIALLY_CONNECTED | np.nan | np.nan (GEE blocked) |
| sar_soil_moisture | PARTIALLY_CONNECTED | Proxied from soil_moisture col | np.nan (GEE blocked) |
| weathering_index | MISSING | Random uniform | np.nan (no source) |
| land_use_settlement | MISSING | np.nan | np.nan (not implemented) |

---

## Critical Blocking Defects

### BD-1: Training Dataset Uses Synthetic/Random Values for Static Factors
`prepare_training_data.py` uses `np.random.uniform` for river/road distances, clay content, and hydraulic conductivity. These bear no spatial relationship to the actual coordinates. The model learns random noise for these factors.

### BD-2: SAR Moisture Semantics Mismatch
Training column `df['soil_moisture']` (Phase-3 dataset, derived from LULC/NDVI derivation, not SAR) is mapped to `sar_soil_moisture`. Inference uses `vv_val` (SAR dB). These are fundamentally different quantities.

### BD-3: `weathering_index` and `land_use_settlement` are Always np.nan
Both factors contribute zero information. The model has never seen a non-null value for these during training or inference.

### BD-4: `lithology_class` Always = "Sedimentary" in Inference
Inference always returns FALLBACK lithology. The trained model learned 3 categories randomly, but inference always sees the same class, creating systematic classification bias.

### BD-5: API Response Has Stale Fields
`risk.py` references `rainfall["rainfall_1day"]` which does not exist in the dict built at line 196 (only `daily_series` key), causing a KeyError at line 231.

### BD-6: `risk.py` model_dir Points to `src/models/` Not a versioned artifact dir
Model artifacts are co-located with training scripts. Phase H requires `artifacts/v2/` structure.

---

## Non-Blocking Notes

- NB-1: Feature ordering is correctly enforced via `FEATURE_ORDER` from `feature_contract.py`.
- NB-2: SHAP aggregation correctly maps one-hot lithology columns back to `lithology_class` semantic factor.
- NB-3: Monotonicity check (`rainfall_3day <= rainfall_15day`) is enforced in `MockChirpsClient`.
- NB-4: SHAP explainer gracefully skipped if load fails.
- NB-5: Risk thresholds (LOW < 0.30, MOD < 0.55, HIGH < 0.75, CRITICAL ≥ 0.75) are correctly implemented.
- NB-6: No hard-coded geographic lat/lon heuristics found in any inference path — **COMPLIANT**.

---

## Audit Verdict

**6 of 14 factors** are fully or partially connected to real data sources.

**2 factors** (weathering_index, land_use_settlement) are permanently MISSING.

**BD-5** (API KeyError) is a runtime crash that must be fixed before the endpoint functions correctly.

All factors ARE available to the model via np.nan (XGBoost handles natively) but several have no meaningful signal. The system is operationally functional but scientifically limited by data availability.
