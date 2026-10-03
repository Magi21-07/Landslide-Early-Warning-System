# Phase: Remote Sensing & Satellite Integration

## 1. Objective
Integrate real-time and historical remote sensing capabilities (Sentinel-2 Optical & Sentinel-1 SAR) into the Landslide Early Warning System to derive robust vegetation, soil moisture proxies, and surface conditions. The pipeline strictly emphasizes scientific correctness, documented fallback states, and non-blocking asynchronous execution.

## 2. Sentinel-2 Architecture
- **Source**: `COPERNICUS/S2_SR_HARMONIZED`
- **Methodology**: Cloud-filtered scenes (≤ 10%), pixel-masked using `S2_CLOUD_PROBABILITY` & SCL layer.
- **Indices Extracted**: NDVI, NDWI, NBR.
- **Vegetation Status**: Condition proxy derived successfully; NOT falsely attributed to direct deforestation.

## 3. Sentinel-1 Architecture
- **Source**: `COPERNICUS/S1_GRD`
- **Methodology**: Interferometric Wide Swath (IW), VV and VH polarizations.
- **SAR Proxy**: `VV` dB acts as a soil-moisture proxy. Cross-polarization log-ratio (`VV_dB - VH_dB`) is implemented. Deformation mapping is explicitly disallowed via single-GRD scenes.

## 4. Caching System
- **Cache**: 7-day TTL SQLite-based localized caching mechanism implemented (`rs_cache.db`).
- **Keys**: Resolution-limited keys preventing hyper-fragmentation (`rs_v1_lat.xxx_lon.yyy`).

## 5. Provenance & Quality States
- Extensive recording of satellite sources, retrieval methods, orbit status, cache hits/misses, and scene identifiers under the `_provenance` array.
- Missing credentials or failed fetches gracefully transition status to `GEE_UNAVAILABLE` or `NO_VALID_SCENE` without crashing the application.

## 6. REAL/MOCK/TEST Modes
- **REAL Mode**: Fetches actual data; strictly prohibits synthetic value substitution.
- **MOCK/TEST Mode**: Allowed for isolated testing logic, preventing contamination of real data records.

## 7. FastAPI Integration
- Implemented in `POST /api/v1/risk/evaluate`.
- **Concurrent execution**: Handled via `concurrent.futures.ThreadPoolExecutor(max_workers=2)` so GEE extraction does not block the FastAPI event loop nor the static factor fetcher.
- **Additive**: Added `remote_sensing_metrics` seamlessly to the output API payload without disrupting frontend state.

## 8. Current ML Compatibility
- Active Phase 4 Model Shape (`X.shape[1] == 4`) is completely protected. Sentinel metrics are additive purely as telemetry data appended to API responses. Historical alignment strategies for future training (pre-event observation matching) are prepared.

## 9. Known Limitations
- Heavy cloud cover in prolonged monsoon seasons will frequently yield `NO_VALID_SCENE` for Sentinel-2 optical data.
- S1 VV backscatter is purely a proxy and requires calibration curves before being treated as absolute volumetric soil moisture.

## 10. Future Model Integration Plan
- Accumulate historical Sentinel 1 & 2 metrics across landslide events.
- Retrain Phase 4 RF Model utilizing historical telemetry matching up to the exact day prior to the slide.

---

REMOTE SENSING + SATELLITE INTEGRATION COMPLETE

### Component Status Checklist
- **Files created**: 
    - `src/etl/remote_sensing_models.py`
    - `src/etl/sentinel_service.py`
    - `tests/etl/test_sentinel_service.py`
    - `scripts/rs_local_verify.py`
    - `docs/remote_sensing/remote_sensing_audit.md`
    - `docs/remote_sensing/remote_sensing_validation_report.md`
    - `docs/remote_sensing/PHASE_REMOTE_SENSING.md`
- **Files modified**: 
    - `src/api/schemas/risk.py`
    - `src/api/routers/risk.py`
- **Files reused**: `src/etl/gee_extractor.py` (GEE Auth logic)
- **Sentinel-2 status**: IMPLEMENTED
- **Sentinel-1 status**: IMPLEMENTED
- **NDVI status**: IMPLEMENTED
- **Vegetation-change status**: UNAVAILABLE (Baseline window logic deferred to explicit retraining phase)
- **SAR proxy status**: IMPLEMENTED (as proxy, not absolute moisture)
- **Cache status**: IMPLEMENTED (7-day SQLite cache)
- **REAL/MOCK/TEST status**: IMPLEMENTED (No synthetic fallbacks in REAL mode)
- **API integration status**: IMPLEMENTED (Concurrent, Additive)
- **Active ML input shape**: PRESERVED (X.shape[1] = 4)
- **Test results**: 7/7 TESTS PASSED. Cross-sensor verify PASSED.
- **Known limitations**: Cloud coverage during monsoon; uncalibrated VV soil moisture.
