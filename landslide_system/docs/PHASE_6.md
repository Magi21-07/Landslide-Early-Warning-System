# Phase 6: Production FastAPI REST Backend
## Landslide Early Warning System (LEWS)

---

## Phase Objective

Phase 6 delivers the production-grade REST API layer for the Himachal Pradesh Landslide Early Warning System. It exposes the fully-verified Phase 1–5 ML and risk pipeline as a secure, geospatial-aware FastAPI web service — enabling real-time integration with dashboards, GIS clients, and mobile alerts.

---

## Architecture Overview

```
Internet / Dashboard / GIS Client
            │
            ▼
┌─────────────────────────────────┐
│        FastAPI (ASGI)           │
│  CorrelationIDMiddleware        │
│  StructuredLoggingMiddleware    │
│  CORSMiddleware                 │
│  Global Exception Handlers      │
│─────────────────────────────────│
│  Routers                        │
│   /health      (public)        │
│   /api/v1/risk (protected POST) │
│   /api/v1/rainfall  (public)   │
│   /api/v1/geospatial (public)  │
└────────────────┬────────────────┘
                 │  Depends()
                 ▼
┌────────────────────────────────┐
│      Service Layer             │
│  RiskService                   │
│  GeospatialService             │
│  (RainfallService via Sched.)  │
└────────────────┬───────────────┘
                 │  calls
                 ▼
┌────────────────────────────────┐
│  Phase 4 & 5 Core Engine       │
│  LandslidePredictor (XGBoost)  │
│  RainfallService + Features    │
│  RainfallTriggerEngine         │
│  DynamicRiskEngine (5×4 matrix)│
│  classify_risk() (canonical)   │
│  RiskScheduler                 │
└────────────────┬───────────────┘
                 │
                 ▼
┌────────────────────────────────┐
│  Storage (Repository Pattern)  │
│  RiskStore ABC                 │
│  SQLiteRiskStore               │
│  (PostgresRiskStore — Phase 7) │
└────────────────────────────────┘
```

### Design Principles
- **Repository Pattern**: `RiskStore` ABC decouples storage from the risk engine. Swap SQLite → PostGIS with zero upstream changes.
- **Service Layer**: `RiskService` and `GeospatialService` bridge FastAPI routes to Phase 5 logic without any code duplication.
- **Singleton LRU Caching**: All expensive resources (ML model, DB connection, scheduler) are instantiated once via `@lru_cache()` in `dependencies.py`.

---

## Router & Endpoint Matrix

| Method | Path | Auth | Response | Description |
|--------|------|------|----------|-------------|
| `GET` | `/` | Public | JSON | Root service info |
| `GET` | `/health` | Public | JSON | Liveness probe |
| `GET` | `/health/ready` | Public | JSON | Readiness — DB connection check |
| `POST` | `/api/v1/risk/evaluate` | **X-API-Key** | `RiskResponse` | Full ML+Rainfall pipeline |
| `GET` | `/api/v1/risk/latest` | Public | `RiskResponse` | Latest risk for location |
| `GET` | `/api/v1/risk/history` | Public | `List[RiskResponse]` | Historical records |
| `GET` | `/api/v1/rainfall/recent` | Public | `RainfallResponse` | CHIRPS daily observations |
| `GET` | `/api/v1/rainfall/summary` | Public | `RainfallSummaryResponse` | Cumulative features + trigger |
| `GET` | `/api/v1/geospatial/risk-map` | Public | `GeoJSONFeatureCollection` | Risk map with bbox filter |
| `GET` | `/docs` | Public | HTML | Swagger UI |
| `GET` | `/openapi.json` | Public | JSON | OpenAPI 3.x spec |

---

## Schemas & Data Contracts

| Schema | File | Maps To |
|--------|------|---------|
| `CoordinateRequest` | `schemas/common.py` | Input lat/lon with bounds validation |
| `ErrorResponse` | `schemas/common.py` | Standardized error body |
| `RiskResponse` | `schemas/risk.py` | `DynamicRiskAssessment` + `LocationRiskState` |
| `RainfallResponse` | `schemas/rainfall.py` | `DailyRainfallRecord` list |
| `RainfallSummaryResponse` | `schemas/rainfall.py` | `RainfallFeatureSet` + `TriggerResult` |
| `PointGeometry` | `schemas/geospatial.py` | GeoJSON Point `[lon, lat]` |
| `GeoJSONFeature` | `schemas/geospatial.py` | GeoJSON Feature |
| `GeoJSONFeatureCollection` | `schemas/geospatial.py` | GeoJSON FeatureCollection |

---

## Phase 1–5 Integration Summary

| Phase | Component | How Used in Phase 6 |
|-------|-----------|---------------------|
| Phase 4 | `LandslidePredictor` (`src/ml/predict.py`) | Called by `RiskService.evaluate_location_risk()` via `RiskScheduler._get_predictor()` |
| Phase 5.2 | `ChirpsClient` | Wrapped by `RainfallService`, injected via `get_rainfall_service()` |
| Phase 5.3 | `RainfallService.get_recent_rainfall()` | Called by `/rainfall/recent` and `/rainfall/summary` routers |
| Phase 5.4 | `RainfallFeatureCalculator` | Called inside `/rainfall/summary` to compute window totals |
| Phase 5.5 | `RainfallTriggerEngine` | Called by `/rainfall/summary` for NORMAL/WATCH/WARNING/CRITICAL state |
| Phase 5.6 | `DynamicRiskEngine` | Called via `RiskScheduler._evaluate_location()` in `RiskService` |
| Phase 5.7 | `classify_risk()` | Canonicalizes MINIMAL/LOW/MODERATE/HIGH/SEVERE → `RiskLevel` enum |
| Phase 5.8 | `RiskScheduler` | Singleton, injected via `get_scheduler()` |
| Phase 5.9 | `SQLiteRiskStore` | Singleton, injected via `get_risk_store()` |
| Phase 5.10 | `run_assessment()` | Called by `RiskService.evaluate_location_risk()` in mock mode |

---

## Geospatial Capabilities

- **Coordinate Standard**: EPSG:4326 (WGS84), GeoJSON mandated `[longitude, latitude]` order
- **Bounding Box Filtering**: `min_lat`, `max_lat`, `min_lon`, `max_lon` query params via SQL `WHERE` on `risk_history`
- **Result Deduplication**: Only the most recent record per `location_id` is returned via `ROW_NUMBER() OVER(PARTITION BY location_id)`
- **Properties Exposed**: `location_id`, `susceptibility_probability`, `susceptibility_class`, `rainfall_7d`, `rainfall_trigger_state`, `dynamic_risk`, `risk_level`, `timestamp`, `stale`
- **PostGIS Readiness**: `GeospatialService` checks `isinstance(store, SQLiteRiskStore)` and falls back gracefully; PostGIS path ready for Phase 7

---

## Security & Governance

| Control | Implementation |
|---------|----------------|
| **API Key Authentication** | `X-API-Key` header via `fastapi.security.APIKeyHeader` |
| **Constant-Time Comparison** | `secrets.compare_digest(incoming, settings.API_KEY)` |
| **Key Source** | `APISettings.API_KEY` loaded from `.env` via `pydantic-settings` |
| **Protected Routes** | `POST /api/v1/risk/evaluate` (+ any future write operations) |
| **Public Routes** | All GET read endpoints, docs |
| **CORS Allowlist** | Explicit origins list from `settings.CORS_ORIGINS` — no wildcard `"*"` in production |
| **Error Sanitization** | `global_exception_handler` catches all `Exception`s — returns `{"error": {"code": "INTERNAL_ERROR", "message": "..."}}`, never raw tracebacks |
| **Correlation ID** | `X-Request-ID` header auto-generated (UUID4) or propagated from client |
| **Structured Logging** | `StructuredLoggingMiddleware` logs method, path, status, duration_ms, request_id |

---

## Testing Strategy

| Layer | Tool | Isolation |
|-------|------|-----------|
| Schema contracts | `pytest` + Pydantic `model_validate()` | Fully in-memory, no server |
| Service layer | `pytest` + `SQLiteRiskStore(":memory:")` | In-memory DB, mock scheduler |
| Router integration | `fastapi.testclient.TestClient` | `app.dependency_overrides` per test |
| Security | `TestClient` + valid/invalid keys | Uses `settings.API_KEY` from config |
| Hardening | `TestClient(raise_server_exceptions=False)` | Injects forced exceptions |
| Phase 6 E2E | `test_phase6_integration.py` | All mocks injected, 24 tests |

**Total API tests: 66 / 66 PASSED**

---

## Local Run & Configuration

### Start the server
```bash
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Required `.env` Variables
```env
# Phase 5 (existing)
EE_PROJECT_ID=Keys/landslide-1-510217-4a30e7c0db5c.json

# Phase 6 additions
API_KEY=your-secret-api-key-here
API_ENV=production
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:3000","https://your-dashboard.com"]
DB_PATH=data/processed/risk_store.db
```

### Interactive API Docs
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## Known Limitations & Next Steps

| Limitation | Next Step |
|-----------|-----------|
| SQLite is not async-safe for high concurrency | Phase 7: Replace with `asyncpg` + PostgreSQL/PostGIS |
| No rate limiting | Add `slowapi` or NGINX rate limiter |
| No JWT / multi-user auth | Add OAuth2 scoped tokens for multi-team access |
| `GeospatialService` PostGIS path is a stub | Implement `ST_Within`, `ST_MakeEnvelope` queries |
| No response caching | Add Redis TTL cache for `/rainfall/recent` and `/geospatial/risk-map` |
| GEE auth in API | Load service account key from env secret, not filesystem in production |
| No API versioning middleware | Add `Accept-Version` header negotiation |
