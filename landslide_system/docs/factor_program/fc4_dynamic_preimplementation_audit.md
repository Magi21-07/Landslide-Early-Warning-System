# FC4: Dynamic Pre-Implementation Audit

## Existing Sources
1. **Rainfall**: `chirps_client.py` and `RainfallService` exist and provide recent dynamic rainfall from CHIRPS.
2. **NDVI**: `src/etl/sentinel_service.py` extracts NDVI from `COPERNICUS/S2_SR_HARMONIZED`.
3. **Tree Cover**: `src/etl/gee_extractor.py` has `extract_vegetation()` which pulls tree cover fraction from `COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019`. We will formalize this.
4. **SAR Soil-Moisture Proxy**: `src/etl/sentinel_service.py` uses Sentinel-1 GRD and computes a proxy from VV backscatter.
5. **Static Features**: `src/etl/spatial_service.py` provides soil properties, lithology, weathering, distances to roads and rivers.
6. **Terrain**: `terrain_service.py` provides slope and elevation.

## Current ML Model
- Artifact: `src/models/landslide_model.pkl` (RandomForestClassifier).
- Trained using: `train.py`, which currently generates a synthetic 10,000 sample dataset inside the file.
- Input Features: `slope_degrees`, `elevation_m`, `rainfall_3day_mm`, `rainfall_15day_mm`.

## Datasets
- Phase-3 Labelled Dataset: Located at `data/processed/ml_dataset_raw.csv` and contains `latitude, longitude, slope, root_cohesion, elevation, soil_moisture, label`. We will use this as the seed for coordinates and labels to build our historical 14-factor dataset.

## Required Modifications
- `src/models/feature_contract.py`: Define the new 14-factor semantic contract.
- `src/features/feature_builder.py`: Implement the unified feature extractor combining static and dynamic pipelines.
- `src/models/prepare_training_data.py`: Read Phase-3 seed dataset, extract 14 factors for each coordinate safely, output a new dataset.
- `src/models/train.py`: Modify to train XGBoost on 14 factors, implement SHAP explainability, handle missing values (`np.nan`), and save model/SHAP/preprocessor artifacts.
- `src/api/routers/risk.py`: Modify the `/evaluate` endpoint to use the new 14 factors, run the preprocessor, compute probability, compute top SHAP risk factors, and return them seamlessly without altering existing keys.

## Unchanged Files
- `src/etl/spatial_service.py`, `src/etl/terrain_service.py`, `src/risk/chirps_client.py`.
- `frontend/*`

The audit confirms all prerequisites are available.
