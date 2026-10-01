import datetime
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.api.dependencies import get_rainfall_service, get_scheduler
from src.risk.rainfall_service import RainfallService
from src.api.schemas.rainfall import RainfallResponse, RainfallSummaryResponse

router = APIRouter(prefix="/api/v1/rainfall", tags=["Rainfall"])
logger = logging.getLogger(__name__)

@router.get(
    "/recent",
    response_model=RainfallResponse,
    summary="Get Recent Rainfall",
    description="Retrieve recent daily CHIRPS rainfall observations."
)
def get_recent_rainfall(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="WGS84 latitude"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="WGS84 longitude"),
    days: int = Query(15, ge=1, le=30, description="Lookback window in days"),
    service: RainfallService = Depends(get_rainfall_service)
):
    try:
        records_raw = service.get_recent_rainfall(latitude=latitude, longitude=longitude, days=days)
        
        if not records_raw:
             raise ValueError("No rainfall records returned.")
        
        obs = []
        for r in records_raw:
             obs.append({
                 "date": r["date"],
                 "rainfall_mm": r["rainfall_mm"]
             })
             
        today = datetime.date.today().isoformat()
        return RainfallResponse(
            latitude=latitude,
            longitude=longitude,
            observation_date=today,
            rainfall_observations=obs,
            source=records_raw[0].get("source", "CHIRPS/GEE") if records_raw else "CHIRPS/GEE",
            retrieval_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
    except Exception as e:
        logger.error(f"Failed to fetch rainfall: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Rainfall data service temporarily unavailable"
        )

@router.get(
    "/summary",
    response_model=RainfallSummaryResponse,
    summary="Get Rainfall Summary",
    description="Calculate cumulative features and trigger states."
)
def get_rainfall_summary(
    latitude: float = Query(..., ge=-90.0, le=90.0, description="WGS84 latitude"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="WGS84 longitude"),
    scheduler = Depends(get_scheduler)
):
    try:
        service = scheduler._get_rainfall_service()
        records_raw = service.get_recent_rainfall(latitude=latitude, longitude=longitude, days=15)
        
        if not records_raw:
            raise ValueError("No rainfall records returned.")
            
        from src.risk.rainfall_features import RainfallFeatureCalculator, DailyRecord
        feat_calc = RainfallFeatureCalculator()
        daily_records = [
            DailyRecord(
                date        = r['date'],
                rainfall_mm = r['rainfall_mm'],
                is_complete = r['rainfall_mm'] is not None,
            )
            for r in records_raw
        ]
        
        ref_date = datetime.date.today()
        feat_set = feat_calc.calculate(daily_records, ref_date)
        
        trigger_engine = scheduler._get_trigger_engine()
        trigger_result = trigger_engine.evaluate(feat_set)
        
        return RainfallSummaryResponse(
            latitude=latitude,
            longitude=longitude,
            rainfall_1d=feat_set.rainfall_1d,
            rainfall_3d=feat_set.rainfall_3d,
            rainfall_7d=feat_set.rainfall_7d,
            rainfall_15d=feat_set.rainfall_15d,
            api_15=feat_set.antecedent_precipitation_index,
            rainfall_trigger_state=trigger_result.trigger_state,
            rainfall_trigger_score=trigger_result.trigger_score
        )
    except Exception as e:
        logger.error(f"Failed to fetch or summarize rainfall: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Rainfall data service temporarily unavailable"
        )
