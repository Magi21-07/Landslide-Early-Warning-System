# FC-3 Pre-Implementation Audit

Generated: 2026-10-02

---

## 1. Repository Structure

```
landslide_system/
├── src/
│   ├── api/
│   │   ├── routers/risk.py        ← ACTIVE ENDPOINT (modify: append spatial_metrics)
│   │   ├── schemas/risk.py        ← SCHEMA (modify: add spatial_metrics field)
│   │   ├── dependencies.py        ← REUSE (singleton injection)
│   │   └── services/
│   ├── etl/
│   │   ├── gee_extractor.py       ← REUSE (_GEE_INIT_FAILED latch, EPSG:4326 30m)
│   │   ├── terrain_service.py     ← REUSE (open-meteo GET pattern)
│   │   ├── vector_utils.py        ← REUSE (align_vectors_to_grid, rasterio/geopandas)
│   │   └── inventory_builder.py   ← REUSE (CSV landslide catalog)
│   ├── features/
│   │   ├── feature_sampler.py     ← REUSE (GEE sampling pattern)
│   │   └── physics_engine.py      ← REUSE (slope calculation EPSG:4326 30m)
│   ├── models/
│   │   ├── landslide_model.pkl    ← DO NOT TOUCH (4-feature RF model)
│   │   └── train.py
│   └── risk/
│       ├── rainfall_service.py    ← REUSE (get_recent_rainfall interface)
│       └── chirps_client.py       ← REUSE (synthetic fallback pattern)
├── data/
│   ├── processed/
│   │   ├── elevation.tif          ← REUSE (Phase-2 DEM, EPSG:4326 30m)
│   │   ├── slope.tif              ← REUSE (Phase-2 slope gradient)
│   │   └── ml_dataset.csv         ← REUSE (feature_columns.json)
│   └── raw/
│       └── Global_Landslide_Catalog_Export_rows.csv.xls
└── tests/
    ├── test_chirps.py             ← PATTERN to follow for new tests
    └── etl/                       ← CREATE new test module here
```

---

## 2. Files to CREATE

| File | Purpose |
|------|---------|
| `src/etl/spatial_models.py` | Canonical StaticSpatialMetrics dataclass & provenance |
| `src/etl/spatial_service.py` | All 4 factor fetchers + orchestrator |
| `tests/etl/test_spatial_service.py` | Full test suite |
| `docs/factor_program/fc3_static_factor_report.md` | Data source report |
| `docs/factor_program/fc3_implementation_report.md` | Final implementation report |

## 3. Files to MODIFY

| File | Change |
|------|--------|
| `src/api/schemas/risk.py` | Append `spatial_metrics: Optional[dict] = None` |
| `src/api/routers/risk.py` | Import spatial_service, call get_static_spatial_metrics, append to response |

## 4. Files to REUSE (unchanged)

- `src/etl/terrain_service.py` — Open-Meteo GET pattern
- `src/etl/gee_extractor.py` — GEE latch pattern
- `src/etl/vector_utils.py` — rasterio alignment
- `data/processed/elevation.tif` — Phase-2 DEM reference
- `data/processed/slope.tif` — Phase-2 slope reference
- All existing ML model files

---

## 5. Static Factor Data Sources

| Factor | Source | Status in Phase-2 |
|--------|--------|-------------------|
| Elevation | Open-Meteo REST (terrain_service.py) | ACTIVE |
| Slope | Derived from elevation gradients | ACTIVE |
| Soil clay % | SoilGrids v2 REST `clay/0-5cm/mean` | NOT PRESENT |
| Hydraulic capacity | SoilGrids v2 REST `wv0033/0-5cm/mean` | NOT PRESENT |
| Soil depth | SoilGrids v2 REST `bdricm/0-5cm/mean` | NOT PRESENT |
| Lithology class | No GLiM raster in data/raw/ or data/processed/ | MISSING — FALLBACK only |
| Weathering index | No weathering proxy raster found | MISSING — UNAVAILABLE |
| Distance to river | Overpass API `waterway~river\|stream` | NOT PRESENT |
| Distance to road | Overpass API `highway` | NOT PRESENT |

**Key finding**: No GLiM, lithology, or weathering raster exists in the repository. Soil depth will use SoilGrids `bdricm`. Lithology will use FALLBACK (clearly marked). Weathering will be UNAVAILABLE.

---

## 6. Existing CRS and Grid Definition

- Phase-2 DEM: `data/processed/elevation.tif` — EPSG:4326, 30m scale
- Phase-2 Slope: `data/processed/slope.tif` — EPSG:4326, 30m scale  
- GEE: All reprojects to `EPSG:4326, scale=30`

---

## 7. Existing Spatial Utilities Available for Reuse

- `vector_utils.align_vectors_to_grid()` — rasterize vector to 30m grid
- `gee_extractor.initialize_gee()` — safe GEE init with latch
- `terrain_service.get_terrain_features()` — Open-Meteo REST + fallback pattern
- `rainfall_service.get_recent_rainfall()` — standard service interface

---

## 8. HTTP Client Strategy

- `httpx` 0.28.1 is installed → use for async concurrent calls
- `requests` also available → used by existing terrain_service.py
- Strategy: Use `httpx.Client` (sync) with `concurrent.futures.ThreadPoolExecutor` for sub-3s parallel execution

---

## 9. Existing Mock/Fallback Behavior

- `gee_extractor._GEE_INIT_FAILED` latch — silent fallback after first failure  
- `terrain_service` — explicit `[200.0]*5` fallback on API failure  
- `chirps_client` — synthetic rainfall generator on GEE failure

Pattern to follow: catch all exceptions, return explicit fallback dict, log warning, mark `quality="FALLBACK"`.

---

## 10. Existing API Response Structure

```json
{
  "probability": 0.123,
  "risk_level": "LOW",
  "susceptibility_class": "LOW",
  "terrain_metrics": {"elevation_m": 430.1, "slope_degrees": 2.1},
  "rainfall_metrics": {"rainfall_1day": 0.0, ...}
}
```

Addition: `"spatial_metrics": { ... }` — strictly additive.

---

## AUDIT CONCLUSION

All required infrastructure is available. Proceeding with implementation.
- `httpx` available for concurrent requests
- rasterio/geopandas available for spatial queries  
- SoilGrids REST v2 is the soil source (no existing implementation)  
- Overpass API for proximity (no existing implementation)
- GLiM: NOT in repo — lithology will return FALLBACK (clearly labelled)
- Weathering: NOT in repo — will return None/UNAVAILABLE
