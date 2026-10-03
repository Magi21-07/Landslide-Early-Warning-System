# Landslide Early Warning System: System Documentation

## 1. EXECUTIVE ARCHITECTURAL SUMMARY
The Landslide Early Warning System has been fully realized through the completion of Phase 1 through Phase 7, culminating in the **FC-4 Dynamic Factor Pipeline & ML Integration**. 

### System Goals & Geographic Scope
The core goal of the project is to provide deterministic, near real-time predictions of landslide hazard probabilities across vulnerable topographies. The target geographic scope encompasses high-risk global terrains (e.g., Himalayas, Western Ghats) with a focus on integrating remote sensing, hydrologic rainfall data, and robust physical static factors to provide localized early warnings.

### Operational Flow
The operational pipeline is architected sequentially:
1. **ETL (Extract, Transform, Load)**: Real-time and static data ingestion from diverse sources (CHIRPS, GEE, Copernicus).
2. **GIS Grid Processing**: Normalization of geospatial layers down to a 30m resolution grid framework.
3. **Feature Extraction**: Real-time programmatic derivation of dynamic and static signals for target coordinates.
4. **ML Inference**: `XGBoostClassifier` evaluation converting environmental vectors into a calibrated hazard probability bounded $[0, 1]$.
5. **FastAPI Backend**: Asynchronous API serving risk JSON packets and dynamically aggregated SHAP risk attribution.
6. **React/TypeScript Dashboard**: MapLibre-powered interactive web GIS dashboard visualizing site-specific hazard alerts and factor-level explanations.

### System Status (v2.0.0)
The legacy Phase-4 arbitrary 4-factor mock model has been entirely deprecated and replaced. The system actively utilizes the **14-factor semantic ML engine (v2.0.0)**. External service timeouts gracefully fall back to `np.nan` native handling, ensuring robust real-time API uptime rather than system-wide crashes.

---

## 2. CANONICAL 14-FACTOR VECTOR & MATHEMATICAL FORMULAE

The predictive model consumes exactly 14 factors, rigorously defined as vector $X \in \mathbb{R}^{14}$. 

### 14 Semantic Features

1. **`slope_degrees`** 
   - *Type:* Static
   - *Source:* 30m DEM
   - *Unit:* Degrees ($^\circ$)
   - *Description:* Topographic slope steepness.
2. **`elevation_m`** 
   - *Type:* Static
   - *Source:* 30m DEM
   - *Unit:* Meters (m)
   - *Description:* Elevation above mean sea level.
3. **`rainfall_3day_mm`** 
   - *Type:* Dynamic
   - *Source:* CHIRPS / GFS
   - *Unit:* Millimeters (mm)
   - *Description:* Cumulative 3-day antecedent rainfall. Must mathematically satisfy: $\text{rainfall\_3day\_mm} \le \text{rainfall\_15day\_mm}$.
4. **`rainfall_15day_mm`** 
   - *Type:* Dynamic
   - *Source:* CHIRPS / GFS
   - *Unit:* Millimeters (mm)
   - *Description:* Cumulative 15-day antecedent rainfall.
5. **`distance_to_river_m`** 
   - *Type:* Static
   - *Source:* Hydrologic/Vector databases
   - *Unit:* Meters (m)
   - *Description:* Euclidean spatial distance to nearest hydrologic channel.
6. **`distance_to_road_m`** 
   - *Type:* Static
   - *Source:* Road/Infrastructure databases
   - *Unit:* Meters (m)
   - *Description:* Euclidean spatial distance to nearest transportation network.
7. **`soil_clay_content`** 
   - *Type:* Static
   - *Source:* SoilGrids (ISRIC)
   - *Unit:* Percentage (%)
   - *Description:* Percentage clay content in surface soil layers.
8. **`soil_hydraulic_cond`** 
   - *Type:* Static
   - *Source:* SoilGrids (ISRIC) / Extrapolated 
   - *Unit:* mm/hr
   - *Description:* Saturated hydraulic conductivity ($K_{\text{sat}}$).
9. **`lithology_class`** 
   - *Type:* Static (Categorical)
   - *Source:* Global Lithological Map (GLiM)
   - *Unit:* N/A
   - *Description:* Categorical rock/geological formation type (e.g., Sedimentary, Igneous).
10. **`ndvi_index`** 
    - *Type:* Dynamic
    - *Source:* Sentinel-2
    - *Unit:* Ratio $[-1, 1]$
    - *Description:* Normalized Difference Vegetation Index. 
      $$\text{NDVI} = \frac{\text{B8} - \text{B4}}{\text{B8} + \text{B4}}$$
11. **`tree_cover_density`** 
    - *Type:* Slow-changing
    - *Source:* Copernicus Landcover
    - *Unit:* Percentage (%)
    - *Description:* Canopy/forest density.
12. **`sar_soil_moisture`** 
    - *Type:* Dynamic
    - *Source:* Sentinel-1 SAR
    - *Unit:* Proxy Scale
    - *Description:* Radar backscatter temporal change proxy ($\text{VV}/\text{VH}$ polarization dynamics).
13. **`weathering_index`** 
    - *Type:* Static
    - *Source:* Geochemical inference models
    - *Unit:* Dimensionless
    - *Description:* Rock mass weathering grade/decay index.
14. **`land_use_settlement`** 
    - *Type:* Slow-changing
    - *Source:* Human geography layers
    - *Unit:* Density/Exposure 
    - *Description:* Human settlement density and land-use exposure classification.

*(Missing Data Strategy: Dynamic external dependencies fallback to `np.nan` securely upon fetch failure.)*

### Core Mathematical Formulations

**Risk Classification Probability Boundaries**
Determines severity banding for UI alerts based on prediction probability $P$:
$$\text{Risk Level} = \begin{cases}    \text{LOW} & \text{if } P < 0.30 \\    \text{MODERATE} & \text{if } 0.30 \le P < 0.55 \\    \text{HIGH} & \text{if } 0.55 \le P < 0.75 \\    \text{CRITICAL} & \text{if } P \ge 0.75    \end{cases}$$

**SHAP Column Aggregation (One-Hot Encoding)**
Aggregates split categorical dummy variables back to the unified parent semantic factor (e.g., `lithology_class`):
$$\phi_i = \sum_{j \in \text{OHE}(i)} \phi_j$$

**Relative SHAP Contribution Share (%)**
Generates the percentage contribution of a specific semantic factor toward the final risk assessment:
$$\text{share}_i = \left( \frac{\phi_i}{\sum_{k=1}^{14} \vert{}\phi_k\vert{}} \right) \times 100\%$$

---

## 3. MACHINE LEARNING MODEL & PIPELINE ARCHITECTURE

### Architecture & Training Specifications
- **Primary Estimator:** `XGBoostClassifier`
- **Native Imputation:** Algorithm configured with `missing=np.nan` allowing natural tree-branch propagation of incomplete data rather than forced mean imputation.
- **Feature Encoding:** Handled via scikit-learn `ColumnTransformer`. Applies `OneHotEncoder(handle_unknown='ignore')` specifically to `lithology_class` whilst maintaining numerical passthrough for remaining factors.

### Model Artifacts & File Paths
- **Model Classifier:** `src/models/landslide_model.pkl` (linked from `landslide_model_v2.pkl`)
- **Pipeline Preprocessor:** `src/models/preprocessor.pkl` (linked from `preprocessor_v2.pkl`)
- **SHAP Explainer:** `src/models/shap_explainer.pkl` (linked from `shap_explainer_v2.pkl`)
- **Training Dataset:** `data/processed/landslide_14factor_dataset.parquet`

### Data Leakage Protections
- **Spatial Isolation:** Grouping strategies utilized to prevent spatially adjacent grid blocks from spanning across the `train` / `validation` boundary.
- **Strict Temporal Sampling:** $T_{\text{observation}} \le T_{\text{event}}$ enforced explicitly. Post-event satellite imagery/signals are strictly blacklisted from the ML historical training feature extraction phase to prevent leakage of the landslide outcome into the antecedent predictors.

---

## 4. MODEL EVALUATION & VALIDATION BENCHMARKS

The 14-factor V2 model was validated over out-of-fold holdouts preventing spatial overfit. Validation exhibited exceptional performance characterized by:

- **ROC-AUC:** `0.8707`
- **Precision:** `0.7454`
- **Recall:** `0.8200`
- **F1 Score:** `0.7809`
- **Confusion Matrix:** 
  ```text
  [[161,  56], 
   [ 36, 164]]
  ```

*Methodology:* Test sets were structurally preserved from the Phase 3 seed pipeline, ensuring exact comparable boundaries when evaluating generalizability over varying topographies.

---

## 5. API INFERENCE & SERVICE INTEGRATION

### The Inference Endpoint
- **Endpoint Route:** `POST /api/v1/risk/evaluate`
- **Architecture Flow:**
  - Real-time coordinates securely funnel into the `FeatureBuilder`.
  - Concurrent tasks wrapped using Python `ThreadPoolExecutor` (or equivalent async non-blocking logic) fetch sub-service spatial, remote sensing, and rainfall payloads preventing the blocking of the main FastAPI event loop.

### Dynamic Response Contract
The updated response contract merges standard legacy fields natively with new SHAP dynamic outputs:
```json
{
  "location_id": "27.9881_86.9250",
  "probability": 0.81,
  "risk_level": "CRITICAL",
  "top_risk_factors": [
    {
      "factor": "Rainfall (15-Day)",
      "contribution": "+42%"
    }
  ],
  "terrain_metrics": {},
  "rainfall_metrics": {},
  ...
}
```

### Explainer Resilience
If the `shap_explainer.pkl` artifact becomes corrupted or fails deserialization upon FastAPI startup, the backend maintains operational resilience by either skipping attribution generation (silently suppressing explanation) or triggering an in-memory auto-rebuild of `shap.TreeExplainer(landslide_model)`.

---

## 6. SYSTEM METADATA, DATA FRESHNESS & KNOWN LIMITATIONS

### Data Freshness Metadata
- **Provenance Flags:** Each feature generated exports temporal lineage containing the origin `source` and a functional `status` (e.g. `LATEST_AVAILABLE`, `STATIC`, `GEE_UNAVAILABLE`).
- **Traceability:** Retrieval timestamps and valid-time bounding windows assure the user of exact satellite-pass staleness.

### Diagnostic & Quality Logging
- **Graceful Degradation:** The system explicitly avoids cascading `HTTP 500` failures by wrapping remote calls (Google Earth Engine, Copernicus, Overpass) with timeouts. Failing dependencies gracefully resolve to `np.nan`.

### Scientific Boundaries & Cautions
1. **Model Validation vs Site Geotechnics:** Software test validation (ROC-AUC) indicates algorithmic pattern recognition over training distributions. It does **not** equate to physical site-specific geotechnical validation. The system acts strictly as a macro-scale *Early Warning* trigger, not a replacement for on-the-ground engineering analysis.
2. **SHAP is Attribution, not Causation:** SHAP percentage shares reflect mathematical model attribution weights for that prediction branch. They do not claim absolute physical causal ground truth.
3. **SAR Soil Moisture Proxy:** The Sentinel-1 SAR component utilizes temporal backscatter variance ($\text{VV}/\text{VH}$) as an environmental wetness proxy. It is explicitly cautioned that this is an indexical proxy and is not a direct volumetric soil moisture measurement.
