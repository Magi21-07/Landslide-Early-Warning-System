# FC4: Dynamic Factors Pipeline

## 1. Dynamic Factors Implemented
The feature integration strategy securely processes exactly 14 factors through a unified `FeatureBuilder` layer, utilizing robust fallback behaviors if external services fail. 

1. **`rainfall_3day_mm`**: Extracted via `RainfallService` (CHIRPS pipeline). Defaults to `np.nan` if unavailable.
2. **`rainfall_15day_mm`**: Same source, strictly ensuring $3D \leq 15D$ monotonicity natively.
3. **`ndvi_index`**: Optical vegetation index fetched dynamically via Sentinel-2 (`sentinel_service`).
4. **`tree_cover_density`**: Current baseline fetched from Copernicus Landcover datasets via `gee_extractor`.
5. **`sar_soil_moisture`**: Remote sensing proxy derived from Sentinel-1 VV backscatter, correctly denoted as a "Proxy" rather than direct volumetric measurement.

## 2. Static Factors (Reused)
All static factors strictly utilize the existing `spatial_service` and `terrain_service` pipelines, enforcing geo-spatial integrity without rewriting logic.
- `slope_degrees`
- `elevation_m`
- `distance_to_river_m`
- `distance_to_road_m`
- `soil_clay_content`
- `soil_hydraulic_cond`
- `lithology_class`
- `weathering_index`
- `land_use_settlement` (Missing implementation routed natively to `np.nan` for safe XGBoost consumption)

## 3. Data Freshness and Traceability
All dynamic features export provenance objects containing:
- `source`: Platform identity (e.g., `COPERNICUS/S2_SR_HARMONIZED`).
- `status`: Identifies `LATEST_AVAILABLE`, `GEE_UNAVAILABLE`, or `STATIC`.
FastAPI endpoints bubble these metrics into the final API payload seamlessly to ensure full transparency of real-world freshness.

## 4. Historical Event Safety
The dataset builder (`prepare_training_data.py`) fetches features purely up to the pre-event window to ensure zero temporal leakage. Static spatial sets were preserved strictly through merging back onto the Phase-3 labeled origin seed (`ml_dataset_raw.csv`).

## 5. Model Loading Strategy
`FastAPI` securely attempts to load:
1. `landslide_model.pkl`
2. `preprocessor.pkl`
3. `shap_explainer.pkl`

If `shap_explainer.pkl` fails, `risk.py` ignores it or attempts an on-the-fly rebuild, avoiding 500 endpoint failures while still providing risk evaluation logic.
