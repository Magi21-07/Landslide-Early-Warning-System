# Phase 4 Audit Report - Landslide Early Warning System

## 1. Existing Relevant Files
Based on the current project structure, the files can be categorized into the previous phases as follows:

- **Phase 1 (Inventory/Data Compilation):**
  - `src/etl/inventory_builder.py`
  - `src/etl/vector_utils.py`
  - `data/raw/` (where inventory likely comes from)

- **Phase 2 (GIS Data Processing):**
  - `scripts/run_phase2.py`
  - `src/etl/gee_extractor.py`
  - `src/features/physics_engine.py`

- **Phase 3 (Cloud-Side Feature Extraction & Dataset Balancing):**
  - `scripts/run_phase3.py`
  - `src/features/feature_sampler.py`

## 2. Phase-3 Dataset
- **Dataset Path:** `data/processed/ml_dataset.csv`
- **Dataset Shape:** 3164 rows, 6 columns

## 3. Columns & Features
- **Column Names:** `latitude`, `longitude`, `slope`, `root_cohesion`, `elevation`, `label`
- **Target Column:** `label`
- **Geographic Identifiers:** `latitude`, `longitude`
- **Feature Columns:** `slope`, `root_cohesion`, `elevation`

## 4. Dataset Quality
- **Missing-Value Summary:** 0 missing values across all columns. (Data was cleaned during Phase 3).
- **Class Distribution:** Perfectly balanced. (1582 instances of label 1, 1582 instances of label 0).
- **Potential Data Leakage Columns:** `latitude` and `longitude`. These columns specify exact coordinates and shouldn't be used as direct features for a generalizable Machine Learning model to avoid spatial overfitting.

## 5. Existing Dependencies & Preprocessing
- **Existing Preprocessing Scripts:** The script `scripts/run_phase3.py` handles the sampling, merging, null-dropping, and balancing. We will need to create standard ML preprocessing (e.g. Train/Test split, Standard Scaling) in a new file for Phase 4.
- **Current `requirements.txt` Check:** It currently contains `earthengine-api, geopandas, rasterio, rioxarray, numpy, pandas, python-dotenv`. 
- **Missing Dependencies for Phase 4:** It does **NOT** contain Machine Learning libraries like `scikit-learn`, `xgboost`, `joblib`, `matplotlib`, or `seaborn`.

## 6. Recommendations for Phase 4 Implementation
To cleanly implement Phase 4 without modifying Phase 1-3 files, the following structure should be created:

1. **`scripts/run_phase4.py`**: The main execution script for training the ML model.
2. **`src/models/__init__.py`**: Module initializer.
3. **`src/models/train.py`**: Script for train/test splitting, scaling, and training algorithms (e.g., Random Forest or XGBoost).
4. **`src/models/evaluate.py`**: Script for generating metrics (accuracy, F1, ROC-AUC) and charts.
5. **Update `requirements.txt`**: Add `scikit-learn`, `xgboost`, `joblib`, `matplotlib`, `seaborn`.
6. **`models/` directory**: A folder to save the serialized models (e.g., `model.pkl`, `scaler.pkl`).
