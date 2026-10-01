from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status, Security
from src.api.security import verify_api_key

from src.api.dependencies import get_risk_service
from src.api.services.risk_service import RiskService
from src.api.schemas.common import CoordinateRequest
from src.api.schemas.risk import RiskResponse

router = APIRouter(prefix="/api/v1/risk", tags=["Landslide Risk"])

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
    mock: bool = Query(False, description="Run in offline mock mode"),
    service: RiskService = Depends(get_risk_service)
):
    try:
        result = service.evaluate_location_risk(
            lat=request.latitude,
            lon=request.longitude,
            mock=mock
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

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
    "/history",
    response_model=List[RiskResponse],
    summary="Get Risk History",
    description="Retrieve historical risk assessments for a location."
)
def get_risk_history(
    location_id: str = Query(..., description="Unique location identifier"),
    limit: int = Query(30, ge=1, le=100, description="Maximum number of records to return"),
    service: RiskService = Depends(get_risk_service)
):
    results = service.get_risk_history(location_id, limit=limit)
    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No risk history found for location_id: {location_id}"
        )
    return results
