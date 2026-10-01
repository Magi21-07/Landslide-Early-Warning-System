# Phase 5 — Master Test Report
## Landslide Early Warning System: Real-Time Risk Engine

**Report Date:** 2026-10-01  
**Environment:** Python 3.14.0 · pytest 9.1.1 · Windows 10  
**Suite Status:** ✅ **316 / 316 PASSED — 0 FAILURES**

---

## 1. Executive Summary

Phase 5 implements a complete, modular Real-Time Dynamic Risk Engine on top of the
Phase 4 static ML susceptibility model. The engine:

- Fetches live daily precipitation from CHIRPS via Google Earth Engine (Phase 5.2)
- Normalises raw rainfall into domain records (Phase 5.3)
- Engineers cumulative and intensity features (Phase 5.4)
- Evaluates deterministic trigger thresholds from YAML (Phase 5.5)
- Combines static ML susceptibility with dynamic rainfall via a 2-D matrix (Phase 5.6)
- Maps matrix output to a canonical 4-tier risk level with full UI metadata (Phase 5.7)
- Orchestrates the full pipeline with cache, staleness, and JSON persistence (Phase 5.8)
- Stores append-only historical records in SQLite with a future-swap-ready ABC (Phase 5.9)
- Exposes a CLI runner with `--mock` offline mode and formatted human-readable output (Phase 5.10)

**All 316 tests run fully offline.** No GEE credentials, no network calls, no live
CHIRPS queries are required to run the test suite.

---

## 2. Architecture Overview

```
INPUTS
  latitude, longitude
  ┌─────────────────────────────────────────────────────┐
  │  Phase 4 (Static ML)          Phase 5 (Dynamic)     │
  │  LandslidePredictor           ChirpsClient           │
  │    ↓ probability                 ↓ daily records     │
  │    ↓ susceptibility_class     RainfallService        │
  │                                  ↓ normalized records│
  │                               RainfallFeatureCalc    │
  │                                  ↓ 1d/3d/7d/15d feat │
  │                               RainfallTriggerEngine  │
  │                                  ↓ trigger_state     │
  │               ┌─────────────────────────────────┐    │
  │               │     DynamicRiskEngine (5.6)      │    │
  │               │  2D Matrix: class × trigger      │    │
  │               │     → final_risk_level           │    │
  │               └─────────────────────────────────┘    │
  │                               classify_risk (5.7)     │
  │                                  ↓ RiskLevel + UI     │
  │               RiskScheduler (5.8) — orchestrator      │
  │               SQLiteRiskStore (5.9) — persistence     │
  │               run_risk_engine CLI (5.10) — entry pt   │
  └─────────────────────────────────────────────────────┘
```

**Design Principles:**
- **Separation of Concerns** — each phase is a single-responsibility module
- **Repository Pattern** — `RiskStore` ABC decouples storage from logic
- **YAML-Driven Configuration** — thresholds, matrices, and UI metadata never hardcoded
- **Offline-First Testing** — all tests use mocks/in-memory backends; zero network I/O
- **Append-Only Audit Log** — SQLite stores history; `mark_stale` inserts not mutates

---

## 3. Module Test Breakdown

| # | Test File | Phase | Test Classes | Tests | Passed | Failed | Time (s) |
|---|-----------|-------|:---:|:---:|:---:|:---:|:---:|
| 1 | `test_chirps.py` | 5.2 | 5 | 27 | 27 | 0 | 0.89 |
| 2 | `test_rainfall_service.py` | 5.3 | 5 | 25 | 25 | 0 | 0.89 |
| 3 | `test_rainfall_features.py` | 5.4 | 6 | 35 | 35 | 0 | 0.18 |
| 4 | `test_rainfall_trigger.py` | 5.5 | 6 | 34 | 34 | 0 | 0.15 |
| 5 | `test_risk_engine.py` | 5.6 | 7 | 31 | 31 | 0 | 0.20 |
| 6 | `test_risk_levels.py` | 5.7 | 6 | 45 | 45 | 0 | 0.24 |
| 7 | `test_risk_scheduler.py` | 5.8 | 6 | 30 | 30 | 0 | 0.54 |
| 8 | `test_risk_store.py` | 5.9 | 6 | 37 | 37 | 0 | 0.12 |
| 9 | `test_run_risk_engine.py` | 5.10 | 5 | 52 | 52 | 0 | 4.17 |
| | **TOTAL** | | **52** | **316** | **316** | **0** | **~7.38** |

> Note: Full suite execution time when run together is **3.69s** due to shared imports.
> Per-module times above are when each file runs in isolation.

---

## 4. Per-Module Test Class Details

### 4.1 `test_chirps.py` — Phase 5.2: CHIRPS Client (27 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestCoordinateValidation` | 8 | Lat/lon bounds, boundary values, fetch raises |
| `TestDateValidation` | 7 | Date ordering, ISO string, date object, inverted range |
| `TestMockedExtraction` | 8 | Full GEE mock chain, DataFrame schema, metadata keys |
| `TestEmptyResultHandling` | 3 | Empty collection → empty DataFrame, both-fail → RuntimeError |
| `TestDataGapHandling` | 1 | None value → NaN, not 0.0 |

**Mock Strategy:** `sys.modules['ee']` replaced with a fresh `MagicMock` before
each test via autouse fixture + `importlib.reload(chirps_client)` to guarantee
the module-level `import ee` resolves to the mock regardless of import order
across the full test suite.

---

### 4.2 `test_rainfall_service.py` — Phase 5.3: Rainfall Service (25 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestRainfallServiceInstantiation` | 3 | Constructor, ChirpsClient reuse, no duplicate ee.Initialize |
| `TestGetDailyRainfall` | 7 | Date range, inclusive bounds, NaN preservation, empty range |
| `TestGetRecentRainfall` | 7 | Days parameter, today's date, missing-data handling |
| `TestOutputSchema` | 5 | DailyRainfallRecord fields, types, source string |
| `TestEdgeCases` | 3 | Invalid dates, coordinate validation delegates to ChirpsClient |

**Mock Strategy:** `ChirpsClient.__new__` injection so the service can be
instantiated and tested without triggering GEE imports.

---

### 4.3 `test_rainfall_features.py` — Phase 5.4: Feature Engineering (35 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestCumulativeWindowFeatures` | 7 | 1d/3d/7d/15d windows, edge alignment |
| `TestMaxDailyFeature` | 4 | max_daily_3d computation, NaN gap handling |
| `TestAntecedentPrecipitationIndex` | 5 | API-15 exponential decay formula |
| `TestPartialDayFlag` | 4 | Incomplete day detection |
| `TestNaNPropagation` | 6 | NaN records not coerced to 0.0 |
| `TestOutputSchema` | 9 | RainfallFeatureSet fields, types, to_dict() |

---

### 4.4 `test_rainfall_trigger.py` — Phase 5.5: Trigger Engine (34 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestTriggerStates` | 8 | NORMAL/WATCH/WARNING/CRITICAL states per feature |
| `TestHighestSeverityWins` | 5 | Cross-feature severity resolution |
| `TestBreachReasons` | 6 | Reason string generation, partial-day note |
| `TestTriggerScore` | 4 | Score 0–3 mapping |
| `TestConfigLoading` | 7 | YAML loading, missing key, invalid threshold |
| `TestEdgeCases` | 4 | Empty features, None values, all thresholds equal |

---

### 4.5 `test_risk_engine.py` — Phase 5.6: Combined Risk Engine (31 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestFullMatrix` | 1 | All 20 susceptibility × trigger combinations |
| `TestExtremeCases` | 4 | VERY_HIGH+CRITICAL→SEVERE, VERY_LOW+CRITICAL→LOW |
| `TestSafeCases` | 3 | VERY_LOW+NORMAL→MINIMAL |
| `TestInputValidation` | 6 | Probability range, class name, trigger state, score |
| `TestMatrixKeyHandling` | 2 | Missing susceptibility key, missing trigger state → `RiskMatrixLookupError` |
| `TestOutputSchema` | 10 | All fields, to_dict, UTC timestamp, reasons merge |
| `TestConfigLoading` | 5 | FileNotFoundError, missing keys, invalid level |

---

### 4.6 `test_risk_levels.py` — Phase 5.7: Canonical Classification (45 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestNumericInterior` | 5 | Interior values for all 4 tiers, int input |
| `TestBoundaryConditions` | 7 | 0.0, 0.25, 0.50, 0.75, 1.0 — higher tier wins at shared edges |
| `TestInvalidFloatInputs` | 5 | Out-of-range, `bool` rejected with `TypeError` |
| `TestStringMappings` | 11 | All 6 mappings, lowercase, mixed-case, whitespace, unknown |
| `TestRiskLevelSchema` | 14 | All fields, types, to_dict, enum as str, custom YAML proves no hardcoding |
| `TestConfigEdgeCases` | 4 | FileNotFoundError, missing keys, pathlib.Path accepted |

---

### 4.7 `test_risk_scheduler.py` — Phase 5.8: Orchestrator (30 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestSuccessfulOrchestration` | 9 | Full pipeline, result schema, multi-location, file persist |
| `TestCachingLogic` | 5 | Cache hit → no fetch, force bypass, stale → refetch |
| `TestFailureHandling` | 5 | Previous state retained, stale flag, batch continuity |
| `TestDryRun` | 4 | No file write, in-memory cache unchanged |
| `TestStatePersistence` | 4 | Load from file, corrupt JSON, get_state/get_all_states |
| `TestLocationRiskState` | 3 | to_dict fields, stale/error_reason defaults |

**Mock Strategy:** `RiskScheduler.__new__` with all lazy engine slots pre-filled
with MagicMocks. `classify_risk` and `RainfallFeatureCalculator` patched via
`unittest.mock.patch(..., create=True)`.

---

### 4.8 `test_risk_store.py` — Phase 5.9: Repository (37 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestAbstractInterface` | 3 | ABC uninstantiable, isinstance check, all 5 methods |
| `TestSaveAndGetLatest` | 11 | Newest-by-timestamp, append-only, schema fields |
| `TestGetRiskHistory` | 6 | Newest-first sort, limit, empty, location isolation |
| `TestMarkStale` | 5 | New stale row, error_info stored, sentinel for new loc |
| `TestGetLastSuccessfulUpdate` | 6 | Returns datetime, timezone-aware, filters stale |
| `TestDataIntegrity` | 6 | Auto-ID, unique IDs, None round-trip, dict not Row |

**Backend:** All tests use `SQLiteRiskStore(db_path=":memory:")` — no disk I/O.

---

### 4.9 `test_run_risk_engine.py` — Phase 5.10: CLI Runner (52 tests)

| Class | Tests | Coverage |
|-------|:---:|---------|
| `TestRunAssessmentMock` | 14 | Result dict schema, coordinates, SQLite persistence |
| `TestFormatReport` | 22 | All required section headers, rainfall fields, hex, action |
| `TestParseArgs` | 8 | Required args, mock flag, location-id, db-path |
| `TestMain` | 4 | Return code 0, stdout banner, separator, SQLite record |
| `TestSubprocessCLI` | 4 | subprocess exit code, all headers, `mm` unit, SQLite persist |

---

## 5. Total Verification Status

```
============================================================
PHASE 5 TEST SUITE — FINAL RESULT
============================================================
Total Tests Collected : 316
Passed                : 316  (100.0%)
Failed                : 0
Errors                : 0
Warnings              : 0

Suite Execution Time  : 3.69 seconds (full suite, parallel imports)
Python Version        : 3.14.0
pytest Version        : 9.1.1
Platform              : Windows 10 (win32)
============================================================
```

---

## 6. Offline / Mocking Strategy

All 316 tests run **100% offline** — zero network calls, zero GEE credentials required.

| Module | Mock Technique |
|--------|---------------|
| `chirps_client` | `sys.modules['ee'] = MagicMock()` + `importlib.reload()` per test |
| `rainfall_service` | `ChirpsClient.__new__` injection; pre-filled return values |
| `rainfall_features` | Pure Python — synthetic `DailyRecord` lists |
| `rainfall_trigger` | Inline YAML written to `tmp_path`; no disk reads |
| `risk_engine` | Inline YAML written to `tmp_path`; no disk reads |
| `risk_levels` | Inline YAML written to `tmp_path`; `lru_cache` per path |
| `risk_scheduler` | `RiskScheduler.__new__` + MagicMock engine slots + `autouse` leaf patches |
| `risk_store` | `SQLiteRiskStore(":memory:")` — pure in-memory SQLite |
| `run_risk_engine` | `_build_mock_predictor()` + `_build_mock_rainfall_service()` injected |

**Import-order isolation fix (test_chirps.py):** When the full suite runs,
earlier test files (`test_rainfall_service.py`) import `chirps_client` before
`test_chirps.py` sets up its `ee_mock`. The autouse `_ensure_ee_mock` fixture
solves this by replacing `sys.modules['ee']` with a **fresh** `MagicMock`
and calling `importlib.reload(chirps_client)` before every test, guaranteeing
a clean binding regardless of collection order.

---

## 7. Sample CLI Output — `run_risk_engine.py --mock`

```
$ python src/risk/run_risk_engine.py \
    --lat 27.5 --lon 85.5 \
    --location-id KULLU-VALLEY \
    --mock \
    --db-path data/processed/risk_store_demo.db

============================================================
LANDSLIDE EARLY WARNING SYSTEM — LOCATION RISK ASSESSMENT
============================================================
*** TEST / MOCK DATA MODE ***
[MODE: MOCK]
Location ID: KULLU-VALLEY (27.5, 85.5)
Timestamp: 2026-10-01T17:59:55.170369+00:00

--- STATIC SUSCEPTIBILITY ---
Probability: 0.68
Class: HIGH

--- DYNAMIC RAINFALL ---
Observation Date: 2026-10-01 (Data Age: 0.0 days, Stale: False)
Rainfall 1D:  12.00 mm
Rainfall 3D:  66.00 mm
Rainfall 7D:  114.00 mm
Rainfall 15D: 210.00 mm
API (15-Day): 86.5117 mm
Rainfall Trigger State: WATCH (Score: 1)
Trigger Reasons:
  - Terrain exhibits HIGH susceptibility (ML probability: 0.6800).
  - Rainfall trigger state is WATCH.
  - 15-day cumulative rainfall (210.0 mm) exceeded watch threshold (180.0 mm)
  - Combined risk matrix lookup [HIGH x WATCH] -> Final Risk Level: MODERATE.

--- COMPOSITE OPERATIONAL RISK ---
Dynamic Risk Level: MODERATE (Code: 2, Hex: #ffc107)
Action: Increase monitoring frequency. Alert field teams.
Storage: Persisted to SQLite (data/processed/risk_store_demo.db)
============================================================
```

> **Interpretation:** Synthetic CHIRPS data (12 mm/day baseline + 30 mm spike on day 1)
> triggers WATCH state via the 15-day cumulative threshold (210 mm > 180 mm watch).
> Combined with HIGH terrain susceptibility, the 2-D matrix yields MODERATE operational
> risk — the canonical risk level maps to numeric code 2 with UI hex `#ffc107` (amber).

---

## 8. Configuration Files (YAML)

| File | Purpose | Controlled By |
|------|---------|--------------|
| `config/rainfall_thresholds.yaml` | 1d/3d/7d/15d trigger thresholds | Phase 5.5 |
| `config/risk_rules.yaml` | 5×4 susceptibility × trigger matrix | Phase 5.6 |
| `config/risk_definitions.yaml` | Canonical 4-tier levels + UI metadata | Phase 5.7 |

All thresholds are **configurable without code changes**. Tests use inline YAML
written to `tmp_path` to guarantee determinism independent of production config.

---

## 9. Phase 5 Completion Sign-Off

| Phase | Module | Status |
|-------|--------|--------|
| 5.1 | Infrastructure Audit | ✅ Complete |
| 5.2 | CHIRPS Client (`chirps_client.py`) | ✅ Verified — 27/27 tests |
| 5.3 | Rainfall Service (`rainfall_service.py`) | ✅ Verified — 25/25 tests |
| 5.4 | Feature Engineering (`rainfall_features.py`) | ✅ Verified — 35/35 tests |
| 5.5 | Trigger Engine (`rainfall_trigger.py`) | ✅ Verified — 34/34 tests |
| 5.6 | Risk Engine (`risk_engine.py`) | ✅ Verified — 31/31 tests |
| 5.7 | Canonical Classification (`risk_levels.py`) | ✅ Verified — 45/45 tests |
| 5.8 | Orchestrator (`risk_scheduler.py`) | ✅ Verified — 30/30 tests |
| 5.9 | Repository (`risk_store.py`) | ✅ Verified — 37/37 tests |
| 5.10 | CLI Runner (`run_risk_engine.py`) | ✅ Verified — 52/52 tests |
| **ALL** | **Phase 5 Real-Time Risk Engine** | ✅ **316/316 PASSING** |

**Ready for Phase 6: FastAPI REST Endpoints & Dashboard.**
