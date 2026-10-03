# Remote Sensing Repository Audit

## 1. Existing GEE Authentication
- GEE authentication and initialization logic exists in `src/etl/gee_extractor.py`.
- Thread-safe initialization state variable `_GEE_INIT_FAILED` prevents cascading repeated initialization attempts.
- Uses `ee.Initialize(credentials=credentials, project=project_id)`.

## 2. Existing Earth Engine Helper Utilities
- Found in `src/etl/gee_extractor.py`.
- Includes functions for extracting DEM and Vegetation. 
- The vegetation function uses `COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019`. This is a static vegetation mask, not Sentinel-2 NDVI.

## 3. Existing ETL Architecture
- `src/etl` directory contains distinct modules for extracting terrain (`terrain_service.py`), spatial factors (`spatial_service.py`), etc.
- Concurrent ThreadPoolExecutors pattern exists in `spatial_service.py`.

## 4. Existing Phase-2 30m grid
- Extractor routines scale outputs to 30m spatial resolution and reproject to EPSG:4326.

## 5. Existing CHIRPS/rainfall service
- `RainfallService` manages CHIRPS dataset retrieval and metrics calculation.

## 6. Existing static-factor service
- `spatial_service.py` provides non-ML spatial factors safely isolated from the inference pipeline.
- Uses HTTP requests to access APIs.

## 7. Existing cache implementation
- Currently, I haven't seen an explicit 7-day cache mechanism module, but there's a store mechanism in `risk_service.py` or potentially in local caches. We will need to create a simple in-memory or SQLite based 7-day TTL cache for the Sentinel service if none exists.

## 8. Existing database/storage layer
- `risk_service.store.save_risk_result` stores risk outputs.

## 9. Existing FastAPI risk endpoint
- `POST /api/v1/risk/evaluate` is available in `src/api/routers/risk.py`.
- Appends `spatial_metrics` and respects ML shape requirements.

## 10. Existing model inference interface
- Predicts via `predict_proba(X)`.
- Enforces `X.shape[1] == 4` strictly.

## 11. Existing frontend API contract
- The frontend expects `spatial_metrics`, `terrain_metrics`, `rainfall_metrics`, `probability`, `risk_level`, `susceptibility_class`.

## 12. Existing tests
- Exist in `tests/etl` for spatial factors. Need to create `tests/etl/test_sentinel_service.py`.

## 13. Existing configuration/environment system
- Reads configuration and API keys from OS environment variables.

## Summary of actions

- **Files to create**:
  - `src/etl/sentinel_service.py`: main service file for Sentinel-1 & 2 logic.
  - `src/etl/remote_sensing_models.py`: Unified remote sensing object schema (Pydantic or Dataclass).
  - `tests/etl/test_sentinel_service.py`: unit tests.
  - `docs/remote_sensing/remote_sensing_validation_report.md`
  - `docs/remote_sensing/PHASE_REMOTE_SENSING.md`

- **Files to modify**:
  - `src/api/schemas/risk.py`: Add `remote_sensing_metrics`.
  - `src/api/routers/risk.py`: Call `sentinel_service.get_remote_sensing_features` concurrently using `asyncio.to_thread` or standard executor, handle errors gracefully, and inject `remote_sensing_metrics` into response object.

- **Files to remain untouched**:
  - `src/api/services/risk_service.py`
  - `src/etl/spatial_service.py`
  - `src/etl/terrain_service.py`
  - `src/models/train.py`
  - `frontend/*`
