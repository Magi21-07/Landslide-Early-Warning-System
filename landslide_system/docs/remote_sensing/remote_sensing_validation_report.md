# Remote Sensing Validation Report

Generated: 2026-10-02

---

## 1. Sentinel-2: Optical Vegetation & Condition Proxy

| Parameter | Configuration / Behavior |
|-----------|--------------------------|
| **Source** | `COPERNICUS/S2_SR_HARMONIZED` |
| **Collection** | Sentinel-2 MultiSpectral Instrument (MSI), Level-2A (Surface Reflectance) |
| **Cloud Filtering (Scene)** | Filter scenes where `CLOUDY_PIXEL_PERCENTAGE < 10` |
| **Masking (Pixel)** | Joined with `COPERNICUS/S2_CLOUD_PROBABILITY` (`probability <= 30`), `SCL != 3` |
| **NDVI Calculation** | `(B8 - B4) / (B8 + B4)`, where `B4, B8` are divided by `10000.0`. Denominator near zero (`< 1e-6`) is clamped to `1e-6`. |
| **Vegetation Features** | `NDVI`, `NDWI`, `NBR` |
| **Observation Timing** | Latest valid cloud-filtered scene within a configurable lookback window (default 30 days) |
| **Quality/Status** | Returns `VALID` & `LATEST_AVAILABLE` when successful. `UNAVAILABLE` when GEE init fails or no scene is found. |
| **REAL/MOCK Mode** | `REAL` mode explicitly fetches data. NO synthetic fake data is produced when GEE fails. |

## 2. Sentinel-1: SAR Surface Condition Proxy

| Parameter | Configuration / Behavior |
|-----------|--------------------------|
| **Source** | `COPERNICUS/S1_GRD` |
| **Polarization** | Filter for dual-pol scenes containing `VV` and `VH` |
| **Instrument Mode** | `IW` (Interferometric Wide swath) |
| **Backscatter Units** | Processed as Native Earth Engine representation (dB) |
| **SAR Proxies** | `sar_soil_moisture_proxy` derived from `VV`. `surface_condition_proxy` derived from `VH`. `vv_vh_metric` = `VV_dB - VH_dB` |
| **Deformation Limitation** | Not supported. Single GRD backscatter cannot measure ground deformation reliably. |
| **Quality/Status** | Returns `VALID` & `LATEST_AVAILABLE` when successful. `UNAVAILABLE` when GEE init fails or no scene is found. |
| **REAL/MOCK Mode** | NO synthetic fake data is produced when GEE fails. |

## 3. Remote Sensing Caching Layer

| Parameter | Configuration / Behavior |
|-----------|--------------------------|
| **Mechanism** | SQLite Database |
| **Key** | Composite key combining satellite factor, version, and coordinates rounded to 3 decimals (`rs_v1_{lat}_{lon}`) |
| **TTL** | 7 Days (168 hours) |
| **Hit/Miss Behavior** | On Hit (`HIT`), returns stored payload along with provenance flag. On Miss (`MISS`), triggers GEE extraction asynchronously and caches output. |

## 4. Metadata and Provenance Contract
Every remote sensing request records:
- **`cache_status`**: `HIT` or `MISS`
- **`sentinel2.status`**, **`sentinel1.status`**: `LATEST_AVAILABLE`, `NO_VALID_SCENE`, `GEE_UNAVAILABLE`, `ERROR`
- **`scene_id`**: For exact tracing back to Sentinel orbit/tile.
- **`orbit`**: Included for Sentinel-1.
- **`processing_method`**: Documented as `gee_mean_reducer_point`.
- **`native_resolution`**: 10m
- **`target_resolution`**: 30m
