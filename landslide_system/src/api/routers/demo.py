from fastapi import APIRouter, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
import datetime
import uuid
import pandas as pd

from src.api.schemas.risk import RiskResponse
from src.alerts.alert_evaluator import AlertEvaluator
from src.alerts.telegram_config import TelegramConfig
from src.alerts.delivery_tracker import DeliveryTracker
from src.alerts.telegram_async import AsyncTelegramDispatcher
from src.api.routers.risk import landslide_model, preprocessor, shap_explainer, feature_mapping, FACTOR_LABELS

router = APIRouter(prefix="", tags=["Demo & Simulation"])

class DemoSimulationRequest(BaseModel):
    target_id: str = Field(default="DEMO-001")
    rainfall_3d_mm: float = Field(default=25.0, ge=0.0, le=500.0)
    soil_moisture_pct: float = Field(default=35.0, ge=0.0, le=100.0)
    terrain_slope: float = Field(default=20.0, ge=0.0, le=90.0)
    trigger_telegram: bool = Field(default=False)

class DemoSimulationResponse(BaseModel):
    simulation_id: str
    target_id: str
    applied_overrides: Dict[str, float]
    risk_response: RiskResponse
    alert_summary: Optional[Dict[str, Any]] = None
    delivery_status: Optional[Dict[str, Any]] = None

SYNTHETIC_BASELINE = {
    "slope_degrees": 20.0,
    "elevation_m": 1200.0,
    "rainfall_3day_mm": 25.0,
    "rainfall_15day_mm": 50.0,
    "distance_to_river_m": 150.0,
    "distance_to_road_m": 200.0,
    "soil_clay_content": 30.0,
    "soil_hydraulic_cond": 1.5,
    "lithology_class": "Sedimentary",
    "ndvi_index": 0.45,
    "tree_cover_density": 60.0,
    "sar_soil_moisture": 35.0,
    "weathering_index": 3.0,
    "land_use_settlement": 1.0,
}

@router.post("/api/v1/demo/simulate", response_model=DemoSimulationResponse)
def simulate_risk(request: DemoSimulationRequest, background_tasks: BackgroundTasks):
    raw_features = SYNTHETIC_BASELINE.copy()
    
    overrides = {
        "rainfall_3day_mm": request.rainfall_3d_mm,
        "sar_soil_moisture": request.soil_moisture_pct,
        "slope_degrees": request.terrain_slope
    }
    raw_features.update(overrides)

    applied_overrides = {
        "rainfall_3d_mm": request.rainfall_3d_mm,
        "soil_moisture_pct": request.soil_moisture_pct,
        "terrain_slope": request.terrain_slope
    }

    X_df = pd.DataFrame([raw_features])
    
    if preprocessor:
        X_processed = preprocessor.transform(X_df)
    else:
        X_processed = X_df
        
    probability = float(landslide_model.predict_proba(X_processed)[0][1])
    
    if probability < 0.30:
        risk_level = "LOW"
    elif probability < 0.55:
        risk_level = "MODERATE"
    elif probability < 0.75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"
        
    top_risk_factors = []
    if shap_explainer is not None:
        try:
            shap_vals = shap_explainer.shap_values(X_processed)
            if isinstance(shap_vals, list):
                shap_vals = shap_vals[1]
            shap_array = shap_vals[0] if len(shap_vals.shape) > 1 else shap_vals
            
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
                        top_risk_factors.append({
                            "factor": FACTOR_LABELS.get(factor, factor),
                            "contribution": f"{sign_str}{round(share)}%",
                            "_raw_abs": abs(val)
                        })
                top_risk_factors.sort(key=lambda x: x["_raw_abs"], reverse=True)
                for f in top_risk_factors:
                    del f["_raw_abs"]
        except Exception:
            pass

    res_dict = {
        "location_id": request.target_id,
        "latitude": 0.0,
        "longitude": 0.0,
        "probability": round(probability, 3),
        "risk_level": risk_level,
        "dynamic_risk": risk_level,
        "susceptibility_class": risk_level,
        "susceptibility_probability": round(probability, 3),
        "terrain_metrics": {"slope_degrees": raw_features["slope_degrees"]},
        "rainfall_metrics": {"rainfall_3day": raw_features["rainfall_3day_mm"]},
        "top_risk_factors": top_risk_factors,
        "rainfall_3d": raw_features["rainfall_3day_mm"],
        "model_info": "XGBoostClassifier_v2.0",
        "data_mode": "TEST",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "observation_date": datetime.date.today().isoformat(),
        "stale": False,
        "data_source": "SIMULATION",
        "ndvi": raw_features["ndvi_index"],
        "sar_moisture_proxy": raw_features["sar_soil_moisture"],
        "status": "success"
    }

    risk_resp = RiskResponse(**res_dict)

    alert_summary = None
    delivery_status = None
    
    evaluator = AlertEvaluator()
    event = evaluator.evaluate_target_risk(
        target_id=request.target_id,
        risk_response=res_dict
    )

    alert_summary = {
        "event_emitted": event.event_emitted,
        "event_type": event.event_type,
        "trigger_reason": event.trigger_reason,
        "telegram_enabled": event.policy_decision.telegram_enabled
    }

    if request.trigger_telegram and event.event_emitted:
        config = TelegramConfig()
        tracker = DeliveryTracker()
        async_dispatcher = AsyncTelegramDispatcher(config, tracker)
        chat_id = config.chat_id or "DEMO_CHAT_ID"
        
        background_tasks.add_task(async_dispatcher.dispatch_in_background, event, chat_id)
        
        delivery_status = {
            "dispatched_async": True,
            "chat_id": chat_id
        }

    return DemoSimulationResponse(
        simulation_id=str(uuid.uuid4()),
        target_id=request.target_id,
        applied_overrides=applied_overrides,
        risk_response=risk_resp,
        alert_summary=alert_summary,
        delivery_status=delivery_status
    )
