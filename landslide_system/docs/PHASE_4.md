# Phase 4: ML Susceptibility Model — Technical Governance Document

---

## 1. Purpose

Phase 4 implements a complete, reproducible Machine Learning pipeline to estimate
**landslide susceptibility probability** (0–1) for any geographic point within the
region of interest. The pipeline covers:

- Dataset preparation and schema locking (Phase 4.1)
- Leakage detection and spatial dataset splitting (Phase 4.2)
- Baseline Logistic Regression model (Phase 4.3)
- Random Forest ensemble model (Phase 4.4)
- XGBoost gradient-boosted model with early stopping (Phase 4.5)
- Unified model evaluation on the untouched test set (Phase 4.6)
- Reusable prediction pipeline and batch inference CLI (Phase 4.7)
- Champion model packaging and governance sign-off (Phase 4.8)

---

## 2. Input Dataset & Physical Features

**Dataset path:** `data/processed/ml_dataset.csv`
**Prepared dataset:** `data/processed/ml_dataset_prepared.csv`
**Shape (after cleaning):** 3,008 rows x 7 columns

| Feature | Description | Source |
|---|---|---|
| `slope` | Terrain slope in degrees | NASADEM via GEE (30 m) |
| `root_cohesion` | Root cohesion proxy from tree-cover fraction | Copernicus LC 2019 via GEE |
| `elevation` | Elevation above sea level (m) | NASADEM via GEE (30 m) |
| `soil_moisture` | 0-10 cm volumetric soil moisture (kg/m2) | NASA GLDAS V021 NOAH 2020-01-01 via GEE |
| `label` | Binary landslide indicator | NASA Global Landslide Catalog |
| `latitude` | WGS84 latitude (geographic identifier only) | Derived from inventory |
| `longitude` | WGS84 longitude (geographic identifier only) | Derived from inventory |

> **Note:** `latitude` and `longitude` are strictly excluded from all predictive
> feature matrices to prevent spatial data leakage.

---

## 3. Spatial Grid Splitting Strategy

Standard random splits allow the same geographic location to appear in both
training and test sets, producing optimistic accuracy estimates that fail on
unseen terrain.

**Strategy applied:**

1. Coordinates are rounded to 1 decimal place (~11 km x 11 km grid cells):
   `grid_id = round(lat, 1)_round(lon, 1)`
2. `GroupShuffleSplit` from scikit-learn is used with `groups=grid_id` to
   guarantee that every grid cell appears in **exactly one** split.
3. Final assertion verifies the intersection of grid IDs across train, val,
   and test is completely empty.

| Split | Samples | Unique Grids | Positive % |
|---|---|---|---|
| Train | 2,131 | 1,675 | 50.4% |
| Validation | 442 | 359 | 48.9% |
| Test | 435 | 360 | 48.1% |

---

## 4. Model Architecture Benchmarks (Untouched Test Set)

| Model | Accuracy | Precision | Recall | F1 Score | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| Logistic Regression (Baseline) | 0.7218 | 0.7268 | 0.6746 | 0.6998 | 0.7974 | 0.7489 |
| Random Forest | 0.7839 | 0.7602 | 0.8038 | 0.7814 | 0.8791 | 0.8590 |
| **XGBoost (Champion)** | **0.7931** | **0.7644** | **0.8230** | **0.7926** | **0.8775** | **0.8595** |

All models were tuned exclusively on the validation set.
The test set was never used for hyperparameter selection.

---

## 5. Selected Downstream Model & Criterion

**Champion Model:** XGBoost Classifier (`models/landslide_susceptibility_model.joblib`)

**Hyperparameters:**

```
n_estimators=300, learning_rate=0.05, max_depth=6,
subsample=0.8, colsample_bytree=0.8, early_stopping_rounds=20,
objective='binary:logistic', random_seed=42
```

**Selection Rationale:**

In life-safety early-warning systems, the asymmetric cost of a **False Negative**
(missed landslide = potential loss of life) vastly exceeds the cost of a
**False Positive** (unnecessary alert = temporary disruption).

XGBoost was selected because it achieves:
- Highest **Validation ROC-AUC: 0.9001** (best discriminative power)
- Highest **Test Recall: 0.8230** (fewest missed landslide events)
- Highest **Test F1-Score: 0.7926** (best precision-recall balance)

**Operational Threshold Recommendation:**
Lower the decision threshold from 0.50 to approximately 0.38 during deployment
to further maximise recall at the cost of a controlled increase in false alarms.

---

## 6. Data-Quality & Operational Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Pseudo-absence sampling for negatives | Non-landslide points are randomly generated, not field-verified | Applied 500 m buffer exclusion zone around positive events |
| Single-year soil moisture composite (2020-01-01) | Does not capture seasonal variability | Extend to multi-year seasonal average in future iterations |
| Spatial grid resolution (~11 km) | Coarse cells may include terrain with heterogeneous risk | Reduce to 1 km cells with larger dataset |
| Static feature stack | Features are time-invariant; no real-time rainfall integration | Phase 5 will integrate live rainfall triggers |
| GEE GLDAS resolution (0.25 deg ~27 km) | Coarser than terrain data (30 m) | Bilinear resampling applied by GEE during sampleRegions |

---

## 7. Execution Guide

### 7.1 Re-run Full ML Pipeline (Phases 4.1 -> 4.5)

```bash
python src/ml/prepare_dataset.py
python src/ml/split_dataset.py
python src/ml/train_baseline.py
python src/ml/train_random_forest.py
python src/ml/train_xgboost.py
```

### 7.2 Unified Evaluation

```bash
python src/ml/evaluate_models.py
```

### 7.3 Unit Tests

```bash
python -m pytest tests/test_predict.py -v
```

### 7.4 Single-Point Inference (Python API)

```python
from src.ml.predict import LandslidePredictor

predictor = LandslidePredictor()
result = predictor.predict({
    "slope": 35.0,
    "root_cohesion": 0.6,
    "elevation": 1800.0,
    "soil_moisture": 55.0
})
print(result)
# {"probability": 0.8305, "susceptibility": "Very High"}
```

### 7.5 Batch Inference CLI

```bash
python src/ml/predict_batch.py --input path/to/input.csv --output path/to/output.csv
```

### 7.6 Package Champion Model

```bash
python src/ml/package_model.py
```

---

*Document generated automatically by `src/ml/package_model.py`. All metrics are
sourced from the live evaluation runs stored in `results/ml/`.*
