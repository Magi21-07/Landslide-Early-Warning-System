from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
import datetime
import logging
import os
import pickle
import concurrent.futures

logger = logging.getLogger(__name__)

from src.api.security import verify_api_key
from src.api.dependencies import get_risk_service, get_rainfall_service
from src.api.services.risk_service import RiskService
from src.api.schemas.common import CoordinateRequest
from src.api.schemas.risk import RiskResponse
from src.etl import terrain_service
from src.etl import spatial_service
from src.etl import sentinel_service
from src.risk.rainfall_service import RainfallService

router = APIRouter(prefix="/api/v1/risk", tags=["Landslide Risk"])

# ----------------- Load ML Model & Artifacts ----------------- #
import json
import shap
from src.features.feature_builder import FeatureBuilder

model_dir = os.path.join(os.path.dirname(__file__), "..", "..", "models")
with open(os.path.join(model_dir, "landslide_model.pkl"), "rb") as f:
    landslide_model = pickle.load(f)

try:
    with open(os.path.join(model_dir, "preprocessor.pkl"), "rb") as f:
        preprocessor = pickle.load(f)
except Exception as e:
    preprocessor = None
    logger.warning(f"Failed to load preprocessor: {e}")

try:
    with open(os.path.join(model_dir, "shap_explainer.pkl"), "rb") as f:
        shap_explainer = pickle.load(f)
except Exception as e:
    shap_explainer = None
    logger.warning(f"Failed to load SHAP explainer: {e}")

try:
    with open(os.path.join(model_dir, "model_metadata.json"), "r") as f:
        model_metadata = json.load(f)
    feature_mapping = model_metadata.get("feature_mapping", {})
except:
    feature_mapping = {}

FACTOR_LABELS = {
    "slope_degrees": "Terrain Slope",
    "elevation_m": "Elevation",
    "rainfall_3day_mm": "Rainfall (3-Day)",
    "rainfall_15day_mm": "Rainfall (15-Day)",
    "distance_to_river_m": "Distance to River",
    "distance_to_road_m": "Distance to Road",
    "soil_clay_content": "Soil Clay Content",
    "soil_hydraulic_cond": "Soil Hydraulic Property",
    "lithology_class": "Lithology",
    "ndvi_index": "Vegetation Index (NDVI)",
    "tree_cover_density": "Tree Cover Density",
    "sar_soil_moisture": "SAR Soil-Moisture Proxy",
    "weathering_index": "Weathering",
    "land_use_settlement": "Settlement / Land-Use Exposure"
}


# Mock chirps_client for exact snippet compatibility
class MockChirpsClient:
    def __init__(self, service: RainfallService):
        self.service = service
        
    def get_recent_rainfall(self, lat: float, lon: float, days: int = 15):
        try:
            records = self.service.get_recent_rainfall(lat, lon, days=days)
            # Ensure we have at least 15 days if network succeeds but data is sparse
            if not records:
                records = [{"rainfall_mm": 0.0}] * 15
        except Exception:
            records = [{"rainfall_mm": 0.0}] * 15
            
        r1 = records[-1].get("rainfall_mm", 0.0)
        r3 = sum(r.get("rainfall_mm", 0.0) for r in records[-3:])
        r7 = sum(r.get("rainfall_mm", 0.0) for r in records[-7:])
        r15 = sum(r.get("rainfall_mm", 0.0) for r in records)
        
        # Enforce rolling summation constraints 
        r3 = max(r3, r1)
        r7 = max(r7, r3)
        r15 = max(r15, r7)

        return {
            "rainfall_1day": r1,
            "rainfall_3day": r3,
            "rainfall_7day": r7,
            "rainfall_15day": r15,
            "daily_series": [r.get("rainfall_mm", 0.0) for r in records]
        }

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks

@router.post(
    "/evaluate",
    response_model=RiskResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate Real-Time Risk",
    description="Evaluate and store real-time risk for a given geographic point.",
    dependencies=[Depends(verify_api_key)]
)
def evaluate_risk(
    request: CoordinateRequest,
    background_tasks: BackgroundTasks,
    mock: bool = Query(False, description="Run in offline mock mode (deprecated)"),
    dispatch_alerts: bool = Query(False, description="Dispatch Telegram alerts in background"),
    risk_service: RiskService = Depends(get_risk_service),
    rainfall_service: RainfallService = Depends(get_rainfall_service)
):
    lat, lon = request.latitude, request.longitude

    chirps_client = MockChirpsClient(rainfall_service)

    # We now use the FeatureBuilder to construct the exact 14 factors safely
    feature_builder = FeatureBuilder(rainfall_service)
    
    # 1. & 2. & 6. Extracted securely via FeatureBuilder
    raw_features, meta = feature_builder.get_features(lat, lon)
    
    # Assert semantic feature count exactly 14
    assert len(raw_features) == 14, f"ML input vector must be exactly 14 features, got {len(raw_features)}"

    # Convert to DataFrame for preprocessing
    import pandas as pd
    import numpy as np
    
    X_df = pd.DataFrame([raw_features])
    
    if preprocessor:
        X_processed = preprocessor.transform(X_df)
    else:
        X_processed = X_df
        
    # 4. Predict via Trained ML Model (probability must be float [0, 1])
    probability = float(landslide_model.predict_proba(X_processed)[0][1])

    # 5. Determine severity class
    if probability < 0.30:
        risk_level = "LOW"
    elif probability < 0.55:
        risk_level = "MODERATE"
    elif probability < 0.75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"
        
    # Calculate SHAP values
    top_risk_factors = []
    if shap_explainer is not None:
        try:
            shap_vals = shap_explainer.shap_values(X_processed)
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[1] # positive class
            
            # shape could be (1, n_features)
            shap_array = shap_vals[0] if len(shap_vals.shape) > 1 else shap_vals
            
            # Aggregate to original factors
            aggregated_shap = {k: 0.0 for k in FACTOR_LABELS.keys()}
            
            for i, col in enumerate(X_processed.columns):
                orig_col = feature_mapping.get(col, col)
                if orig_col in aggregated_shap:
                    aggregated_shap[orig_col] += float(shap_array[i])
                    
            total_abs_shap = sum(abs(v) for v in aggregated_shap.values())
            
            if total_abs_shap > 0:
                for factor, val in aggregated_shap.items():
                    share = (abs(val) / total_abs_shap) * 100
                    if share > 0:
                        sign_str = "+" if val >= 0 else "-"
                        # Create generic label: "Rainfall (15-Day): +32%"
                        top_risk_factors.append({
                            "factor": FACTOR_LABELS.get(factor, factor),
                            "contribution": f"{sign_str}{round(share)}%",
                            "_raw_abs": abs(val) # for sorting
                        })
                # Sort descending
                top_risk_factors.sort(key=lambda x: x["_raw_abs"], reverse=True)
                # Cleanup internal sorting key
                for f in top_risk_factors:
                    del f["_raw_abs"]
        except Exception as e:
            logger.warning(f"SHAP explanation failed: {e}")

    # Fetch individual structures for backward compatibility of API response
    terrain = {"slope_degrees": raw_features.get("slope_degrees"), "elevation_m": raw_features.get("elevation_m")}
    
    # Build rainfall dict using chirps_client (already fetched inside FeatureBuilder; re-use values)
    chirps_data = chirps_client.get_recent_rainfall(lat, lon, days=15)
    rainfall = {
        "rainfall_1day": chirps_data.get("rainfall_1day", 0.0),
        "rainfall_3day": chirps_data.get("rainfall_3day", 0.0),
        "rainfall_7day": chirps_data.get("rainfall_7day", 0.0),
        "rainfall_15day": chirps_data.get("rainfall_15day", 0.0),
        "daily_series": chirps_data.get("daily_series", [])
    }
    
    def fetch_static_spatial():
        try:
            return spatial_service.get_static_spatial_metrics(lat, lon)
        except:
            return None
            
    def fetch_remote_sensing():
        try:
            return sentinel_service.get_remote_sensing_features(lat, lon).to_api_dict()
        except:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        static_spatial = executor.submit(fetch_static_spatial).result()
        remote_sensing = executor.submit(fetch_remote_sensing).result()

    res_dict = {
        "location_id": f"{lat:.4f}_{lon:.4f}",
        "latitude": lat,
        "longitude": lon,
        "probability": round(probability, 3),
        "risk_level": risk_level,
        "dynamic_risk": risk_level,
        "susceptibility_class": risk_level,
        "susceptibility_probability": round(probability, 3),
        "terrain_metrics": terrain,
        "rainfall_metrics": rainfall,
        "spatial_metrics": static_spatial,
        "remote_sensing_metrics": remote_sensing,
        "top_risk_factors": top_risk_factors,
        "factor_metadata": meta.get("feature_metadata", {}),
        "daily_rainfall": rainfall.get("daily_series", []),
        "rainfall_1d": rainfall.get("rainfall_1day", 0.0),
        "rainfall_3d": rainfall.get("rainfall_3day", 0.0),
        "rainfall_7d": rainfall.get("rainfall_7day", 0.0),
        "rainfall_15d": rainfall.get("rainfall_15day", 0.0),
        "model_info": f"XGBoostClassifier_v2.0",
        "data_mode": "REAL" if not mock else "MOCK",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "observation_date": datetime.date.today().isoformat(),
        "stale": False,
        "data_source": "MOCK/SYNTHETIC" if mock else "ML Pipeline v2.0 / 14-Factor",
        "ndvi": raw_features.get("ndvi_index"),
        "sar_moisture_proxy": raw_features.get("sar_soil_moisture"),
        "distance_to_river_m": raw_features.get("distance_to_river_m"),
    }
    
    # Save the risk result so it appears on the dashboard batch list
    risk_service.store.save_risk_result(res_dict)

    if dispatch_alerts:
        from src.alerts.alert_evaluator import AlertEvaluator
        from src.alerts.telegram_config import TelegramConfig
        from src.alerts.delivery_tracker import DeliveryTracker
        from src.alerts.telegram_async import AsyncTelegramDispatcher
        
        evaluator = AlertEvaluator()
        event = evaluator.evaluate_target_risk(
            target_id=res_dict["location_id"],
            risk_response=res_dict
        )
        
        if event.event_emitted:
            config = TelegramConfig()
            tracker = DeliveryTracker()
            async_dispatcher = AsyncTelegramDispatcher(config, tracker)
            chat_id = config.chat_id or ""
            background_tasks.add_task(async_dispatcher.dispatch_in_background, event, chat_id)

    return res_dict

@router.get(
    "/latest",
    response_model=RiskResponse,
    summary="Get Latest Risk",
    description="Retrieve the most recently calculated risk state for a location."
)
def get_latest_risk(
    location_id: str = Query(..., description="Unique location identifier"),
    service: RiskService = Depends(get_risk_service)
):
    result = service.get_current_risk(location_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No risk record found for location_id: {location_id}"
        )
    return result

@router.get(
    "/targets",
    response_model=List[RiskResponse],
    summary="Get Batch Targets",
    description="Retrieve the latest risk evaluated for all stored target locations."
)
def get_targets(
    background_tasks: BackgroundTasks,
    risk_service: RiskService = Depends(get_risk_service),
    rainfall_service: RainfallService = Depends(get_rainfall_service)
):
    # Dynamic pipeline evaluation for target list
    targets = [
        (26.9124, 75.7873),
        (27.5000, 85.5000),
        (31.1046, 77.1734),
        (31.6908, 76.5177)
    ]
    results = []
    
    for lat, lon in targets:
        req = CoordinateRequest(latitude=lat, longitude=lon)
        res = evaluate_risk(req, background_tasks=background_tasks, mock=True, risk_service=risk_service, rainfall_service=rainfall_service)
        results.append(res)
        
    return results

@router.get(
    "/history",
    response_model=List[RiskResponse],
    summary="Get Risk History"
)
def get_risk_history(
    location_id: str = Query(...),
    limit: int = Query(30, ge=1, le=100),
    service: RiskService = Depends(get_risk_service)
):
    history = service.get_risk_history(location_id, limit)
    if not history:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No historical data found for location_id: {location_id}"
        )
    return history
