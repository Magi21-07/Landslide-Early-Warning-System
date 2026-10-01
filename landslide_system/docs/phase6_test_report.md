# Phase 6 Test Report
## Landslide Early Warning System — FastAPI Backend

**Report Date:** 2026-10-01  
**Test Executor:** Lead Systems Architect  
**Environment:** Python 3.14.0 · pytest 9.1.1 · FastAPI 0.135.1 · Pydantic v2.12.5

---

## 1. Full Test Run Results

```
$ python -m pytest tests/api/ -v
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.1.1, pluggy-1.6.0
collected 66 items

66 passed, 26 warnings in 1.04s
```

### Result: **66 / 66 PASSED — 0 FAILED — 0 ERRORS**

---

## 2. Test Suite Breakdown

| Test File | Tests | Pass | Fail | Coverage Area |
|-----------|------:|-----:|-----:|---------------|
| `test_geospatial.py` | 4 | 4 | 0 | GeoJSON FeatureCollection, bbox filter, invalid bbox, empty result |
| `test_hardening.py` | 5 | 5 | 0 | X-Request-ID middleware, CORS, readiness probe, 500 sanitization |
| `test_main.py` | 4 | 4 | 0 | Root, health, landslide status, OpenAPI schema |
| `test_phase6_integration.py` | 24 | 24 | 0 | End-to-end all endpoints, auth flow, error handling |
| `test_rainfall_router.py` | 5 | 5 | 0 | Recent rainfall, summary, 503 failure, bounds validation |
| `test_risk_router.py` | 7 | 7 | 0 | Evaluate (auth), latest, history, 404, OpenAPI |
| `test_schemas.py` | 7 | 7 | 0 | CoordinateRequest validation, RiskResponse parsing, alias, date fields |
| `test_security.py` | 5 | 5 | 0 | Public endpoints, 401 missing/wrong key, valid key, OpenAPI security |
| `test_services.py` | 5 | 5 | 0 | Mock success, invalid coords, failure propagation, get/history |
| **TOTAL** | **66** | **66** | **0** | |

---

## 3. Endpoints Verified

| Method | Path | Auth | Status |
|--------|------|------|--------|
| `GET` | `/` | Public | ✅ 200 |
| `GET` | `/health` | Public | ✅ 200 |
| `GET` | `/health/ready` | Public | ✅ 200 (DB probe) |
| `POST` | `/api/v1/risk/evaluate` | **Protected** | ✅ 200 / 401 / 422 |
| `GET` | `/api/v1/risk/latest` | Public | ✅ 200 / 404 |
| `GET` | `/api/v1/risk/history` | Public | ✅ 200 / 404 |
| `GET` | `/api/v1/rainfall/recent` | Public | ✅ 200 / 503 / 422 |
| `GET` | `/api/v1/rainfall/summary` | Public | ✅ 200 / 503 |
| `GET` | `/api/v1/geospatial/risk-map` | Public | ✅ 200 / 400 |
| `GET` | `/docs` | Public | ✅ 200 HTML |
| `GET` | `/openapi.json` | Public | ✅ OpenAPI 3.x JSON |

---

## 4. External Services Mocked

| External Service | Phase | Mock Strategy |
|-----------------|-------|---------------|
| GEE / CHIRPS CHIRPS satellite client | 5.2–5.3 | `MockRainfallService` — returns 10mm/day deterministic synthetic records |
| `RiskScheduler._get_rainfall_service()` | 5.8 | `MockSchedulerWithRainfall` subclass returning `MockRainfallService` |
| `SQLiteRiskStore` | 5.9 | `:memory:` in-memory SQLite across all tests |
| `LandslidePredictor` (ML model) | 4 | `_build_mock_predictor()` from `run_risk_engine.py` returns fixed `{"probability": 0.68, "susceptibility": "HIGH"}` |

---

## 5. Security Boundary Verification

| Check | Result |
|-------|--------|
| `POST /api/v1/risk/evaluate` returns `HTTP 401` with missing `X-API-Key` | ✅ PASS |
| `POST /api/v1/risk/evaluate` returns `HTTP 401` with wrong key | ✅ PASS |
| `POST /api/v1/risk/evaluate` returns `HTTP 200` with valid key | ✅ PASS |
| `constant-time comparison` via `secrets.compare_digest` | ✅ Implemented |
| Public read endpoints (`/health`, `/risk/latest`, `/geospatial/risk-map`) succeed with no key | ✅ PASS |
| OpenAPI schema declares `APIKeyHeader` security scheme on protected routes | ✅ PASS |
| CORS `allow_origins` uses explicit list from `APISettings.CORS_ORIGINS` (not `"*"`) | ✅ PASS |

---

## 6. GeoJSON Specification Verification

| Check | Result |
|-------|--------|
| Response root type is `"FeatureCollection"` | ✅ PASS |
| Each item type is `"Feature"` with nested `"Point"` geometry | ✅ PASS |
| `coordinates` order is **`[longitude, latitude]`** (EPSG:4326 / GeoJSON spec) | ✅ PASS (verified LOC-A: `[85.5, 27.5]`) |
| Bounding box filter returns only records within `[min_lat, max_lat, min_lon, max_lon]` | ✅ PASS |
| Empty bbox returns `features: []` with HTTP 200 | ✅ PASS |
| Inverted bbox (`min_lat > max_lat`) returns HTTP 400 | ✅ PASS |

---

## 7. Error Handling & Stack Trace Suppression

| Scenario | Expected | Result |
|----------|----------|--------|
| Unhandled `Exception` in route handler | HTTP 500, `{"error": {"code": "INTERNAL_ERROR"}, "request_id": "..."}` | ✅ PASS |
| `ValueError` in route handler | HTTP 400, `{"error": {"code": "VALIDATION_ERROR"}, ...}` | ✅ PASS |
| `RequestValidationError` (Pydantic) | HTTP 422, `{"error": {"code": "UNPROCESSABLE_ENTITY"}, ...}` | ✅ PASS |
| Python traceback in 500 response body | **Absent** | ✅ PASS |
| Internal secret text in 500 response body | **Absent** | ✅ PASS |
| `X-Request-ID` present in all responses | Present | ✅ PASS |
| Custom `X-Request-ID` header echoed back | Propagated | ✅ PASS |
| CHIRPS failure returns HTTP 503 (not fabricated data) | 503 | ✅ PASS |
