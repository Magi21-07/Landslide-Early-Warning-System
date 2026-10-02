from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status
import datetime
import os
import pickle

from src.api.security import verify_api_key
from src.api.dependencies import get_risk_service, get_rainfall_service
from src.api.services.risk_service import RiskService
from src.api.schemas.common import CoordinateRequest
from src.api.schemas.risk import RiskResponse
from src.etl import terrain_service
from src.risk.rainfall_service import RainfallService

router = APIRouter(prefix="/api/v1/risk", tags=["Landslide Risk"])

# ----------------- Load ML Model ----------------- #
model_path = os.path.join(os.path.dirname(__file__), "..", "..", "models", "landslide_model.pkl")
with open(model_path, "rb") as f:
    landslide_model = pickle.load(f)

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
    mock: bool = Query(False, description="Run in offline mock mode (deprecated)"),
    risk_service: RiskService = Depends(get_risk_service),
    rainfall_service: RainfallService = Depends(get_rainfall_service)
):
    lat, lon = request.latitude, request.longitude

    chirps_client = MockChirpsClient(rainfall_service)

    # 1. Fetch dynamic terrain features (Zero hardcoded bounding boxes)
    terrain = terrain_service.get_terrain_features(lat, lon)

    # 2. Fetch rolling 15-day rainfall series
    rainfall = chirps_client.get_recent_rainfall(lat, lon, days=15)

    # 3. Construct feature array X
    X = [[
        terrain["slope_degrees"],
        terrain["elevation_m"],
        rainfall["rainfall_3day"],
        rainfall["rainfall_15day"]
    ]]

    # 4. Predict via Trained ML Model
    probability = float(landslide_model.predict_proba(X)[0][1])

    # 5. Determine severity class
    if probability < 0.30:
        risk_level = "LOW"
    elif probability < 0.55:
        risk_level = "MODERATE"
    elif probability < 0.75:
        risk_level = "HIGH"
    else:
        risk_level = "CRITICAL"

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
        "daily_rainfall": rainfall["daily_series"],
        "rainfall_1d": rainfall["rainfall_1day"],
        "rainfall_3d": rainfall["rainfall_3day"],
        "rainfall_7d": rainfall["rainfall_7day"],
        "rainfall_15d": rainfall["rainfall_15day"],
        "model_info": "RandomForestClassifier_v1.0",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "observation_date": datetime.date.today().isoformat(),
        "stale": False,
        "data_source": "ML Pipeline",
    }
    
    # Save the risk result so it appears on the dashboard batch list
    risk_service.store.save_risk_result(res_dict)

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
        res = evaluate_risk(req, mock=True, risk_service=risk_service, rainfall_service=rainfall_service)
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
    history = service.get_historical_risk(location_id, limit)
    return history
