# Phase 5 Model Contract
## Real-Time Risk Engine — Integration Specification

> **Status:** Governance-Approved  
> **Champion Model:** XGBoost Classifier  
> **Canonical Artifact:** `models/landslide_susceptibility_model.joblib`  
> **Authored by:** Phase 5 Audit (src/audit/phase5_audit.py)

---

## 1. Final Model Path & Artifacts

| Artifact | Path | Size |
|---|---|---|
| Production model (canonical) | `models/landslide_susceptibility_model.joblib` | ~370 KB |
| Source XGBoost model | `models/xgboost_landslide.joblib` | ~370 KB |
| Model metadata | `models/model_metadata.json` | ~1.4 KB |
| Feature schema lock | `data/processed/feature_columns.json` | ~342 B |
| Threshold configuration | `config/susceptibility_config.json` | ~217 B |
| Prediction class | `src/ml/predict.py` | ~4.7 KB |
| Batch inference CLI | `src/ml/predict_batch.py` | ~2 KB |
| Unit tests (29/29 passing) | `tests/test_predict.py` | ~6 KB |

> **Important:** Phase 5 MUST use `models/landslide_susceptibility_model.joblib`
> as the canonical production model path by overriding the `model_path` argument
> in `LandslidePredictor`.

---

## 2. Required Input Feature Schema & Order

The model was trained on **exactly 4 physical features** in the following fixed order:

```python
feature_columns = ["slope", "root_cohesion", "elevation", "soil_moisture"]
```

| # | Feature | Type | Unit | Source |
|---|---|---|---|---|
| 1 | `slope` | float | degrees | NASADEM 30m via GEE |
| 2 | `root_cohesion` | float | fraction (0-100) | Copernicus tree-cover % via GEE |
| 3 | `elevation` | float | metres ASL | NASADEM 30m via GEE |
| 4 | `soil_moisture` | float | kg/m2 | NASA GLDAS 0-10cm via GEE |

**Column order is enforced by `LandslidePredictor._validate_and_prepare()`.**
Any reordering or omission will raise a `ValueError`.

---

## 3. Preprocessing & Input Validation Rules

### 3.1 Preprocessing

| Rule | Detail |
|---|---|
| StandardScaler | **NOT required.** XGBoost is a tree-based model and is scale-invariant. |
| Missing values | Rejected with `ValueError`. All 4 features must be non-null. |
| Non-numeric values | Rejected with `ValueError` via `pd.to_numeric()` coercion check. |
| Extra columns | Silently ignored. `latitude`, `longitude`, `id` etc. are stripped internally. |
| Column reordering | Applied automatically by `_validate_and_prepare()`. |

### 3.2 Valid Input Ranges (Approximate Physical Bounds)

| Feature | Min | Max | Notes |
|---|---|---|---|
| `slope` | 0.0 | 90.0 | Degrees; >60 deg is physically extreme |
| `root_cohesion` | 0.0 | 100.0 | Tree-cover fraction % |
| `elevation` | -500.0 | 8849.0 | Sea level to Everest (m) |
| `soil_moisture` | 0.0 | 500.0 | kg/m2, GLDAS 0-10 cm layer |

---

## 4. Static vs. Dynamic Feature Breakdown

The Phase 4 ML model uses **static terrain + quasi-static soil features**.
Phase 5 introduces **dynamic rainfall as an overlay trigger**, NOT as an additional
ML predictor.

| Feature | Type | Frequency | Used in ML Model |
|---|---|---|---|
| `slope` | Static terrain | One-time extraction | YES (ML input) |
| `root_cohesion` | Quasi-static | Annual land-cover | YES (ML input) |
| `elevation` | Static terrain | One-time extraction | YES (ML input) |
| `soil_moisture` | Quasi-static | 2020 snapshot (GLDAS) | YES (ML input) |
| `rainfall` (Phase 5) | Dynamic | Real-time / sub-hourly | **NO — Overlay trigger only** |

### Phase 5 Two-Layer Risk Architecture

```
LAYER 1 (Static Base)                     LAYER 2 (Dynamic Overlay)
---------------------------------         ---------------------------------
XGBoost ML Susceptibility Score           Real-Time Rainfall Threshold
P_base = LandslidePredictor.predict()     R_current from OpenWeatherMap/GEE

              COMBINED RISK DECISION ENGINE
              if P_base >= 0.60 AND R_current >= threshold:
                  => Issue ALERT
              elif P_base >= 0.40:
                  => Monitor (elevated watch)
              else:
                  => Normal
```

**Rationale:** Keeping rainfall as an overlay preserves model reproducibility.
The ML model's ground truth (historical landslide inventory) does not include
matched rainfall time-series, preventing reliable rainfall coefficient training.

---

## 5. Geographic Fields Handling

| Field | Role | Used as ML predictor |
|---|---|---|
| `latitude` | Geographic identifier — spatial split key, map rendering | **NO** |
| `longitude` | Geographic identifier — spatial split key, map rendering | **NO** |

- `latitude` and `longitude` are explicitly listed under `latitude_column` /
  `longitude_column` in `feature_columns.json`, separated from `feature_columns`.
- `LandslidePredictor._validate_and_prepare()` only selects `feature_columns`
  — coordinate columns are automatically excluded even if present in input.
- Phase 5 MUST pass coordinates separately to the mapping/visualization layer.
  They must NEVER be injected into the `LandslidePredictor.predict()` payload as features.

---

## 6. Model Output Definition

`LandslidePredictor.predict()` returns:

### Single dict input:
```python
{"probability": 0.7312, "susceptibility": "High"}
```

### DataFrame input:
```python
[
  {"probability": 0.1204, "susceptibility": "Very Low"},
  {"probability": 0.7312, "susceptibility": "High"},
  ...
]
```

### 5-Tier Susceptibility Mapping

| Probability Range | Label | Operational Meaning |
|---|---|---|
| 0.00 – 0.20 | Very Low | No action required |
| 0.21 – 0.40 | Low | Passive monitoring |
| 0.41 – 0.60 | Moderate | Elevated watch; rainfall monitoring activated |
| 0.61 – 0.80 | High | Active alert readiness; notify local authorities |
| 0.81 – 1.00 | Very High | Issue public WARNING; evacuation consideration |

**Probability is rounded to 4 decimal places.**
**Threshold boundaries are loaded from `config/susceptibility_config.json`**
and are reconfigurable without retraining the model.

---

## 7. Recommended Phase 5 Integration Strategy

### 7.1 Import Pattern (MANDATORY)

Phase 5 MUST import and reuse `LandslidePredictor`. **No duplicate inference
code is permitted.**

```python
# Correct Phase 5 import pattern
from src.ml.predict import LandslidePredictor

predictor = LandslidePredictor(
    model_path='models/landslide_susceptibility_model.joblib'
)
```

### 7.2 Suggested Phase 5 Module Structure

```
src/
  risk_engine/
    __init__.py
    rainfall_fetcher.py    # Fetches real-time rainfall (OpenWeatherMap / GEE)
    risk_calculator.py     # Combines P_base + rainfall overlay -> alert level
    alert_dispatcher.py    # Sends alerts (SMS, webhook, dashboard)
    gee_realtime.py        # Cloud-side feature extraction for new points
scripts/
  run_phase5.py            # Entry point: fetches data, runs engine, dispatches alerts
```

### 7.3 Risk Engine Interface Contract

```python
# risk_engine/risk_calculator.py (Phase 5 skeleton)
from src.ml.predict import LandslidePredictor

class RiskCalculator:
    def __init__(self):
        self.predictor = LandslidePredictor(
            model_path='models/landslide_susceptibility_model.joblib'
        )

    def compute_risk(self, point: dict, rainfall_mm: float) -> dict:
        # Step 1: Static ML base score
        base = self.predictor.predict({
            "slope":          point["slope"],
            "root_cohesion":  point["root_cohesion"],
            "elevation":      point["elevation"],
            "soil_moisture":  point["soil_moisture"]
        })

        # Step 2: Dynamic rainfall overlay
        alert = self._overlay_rainfall(base["probability"], rainfall_mm)

        return {
            "latitude":        point["latitude"],
            "longitude":       point["longitude"],
            "base_probability": base["probability"],
            "susceptibility":   base["susceptibility"],
            "rainfall_mm":      rainfall_mm,
            "alert_level":      alert
        }

    def _overlay_rainfall(self, p_base: float, rainfall_mm: float) -> str:
        # Configurable thresholds — to be refined in Phase 5.1
        if p_base >= 0.60 and rainfall_mm >= 50.0:
            return "RED"
        elif p_base >= 0.40 and rainfall_mm >= 25.0:
            return "ORANGE"
        elif p_base >= 0.40:
            return "YELLOW"
        return "GREEN"
```

### 7.4 Existing GEE Utilities Available for Phase 5

| Utility | Location | Purpose |
|---|---|---|
| `initialize_gee()` | `src/etl/gee_extractor.py` | Authenticate GEE via service account |
| `extract_dem()` | `src/etl/gee_extractor.py` | Extract NASADEM elevation + slope |
| `extract_vegetation()` | `src/etl/gee_extractor.py` | Extract Copernicus tree-cover fraction |
| `extract_soil_moisture()` | `src/features/feature_sampler.py` | Extract NASA GLDAS soil moisture |
| `sample_cloud_features()` | `src/features/feature_sampler.py` | Cloud-side point sampling via GEE |

Phase 5 can call `sample_cloud_features()` with new alert points to dynamically
extract static terrain features for new geographic coordinates not in the training set.

---

## 8. Governance Sign-off

| Checkpoint | Status |
|---|---|
| Phase 4 ML pipeline complete | APPROVED |
| Champion model selected (XGBoost) | APPROVED |
| Feature schema locked | APPROVED |
| No spatial leakage in training splits | APPROVED |
| Unit tests 29/29 passing | APPROVED |
| Batch inference CLI validated | APPROVED |
| Model metadata & governance doc generated | APPROVED |
| Phase 5 model contract signed | APPROVED |

---

*This document is generated automatically by `src/audit/phase5_audit.py`.*  
*Do not manually edit. Re-run the audit script to refresh.*
