from fastapi import APIRouter, Depends, Query, HTTPException, status
from typing import Optional

from src.api.dependencies import get_geospatial_service
from src.api.services.geospatial_service import GeospatialService
from src.api.schemas.geospatial import GeoJSONFeatureCollection

router = APIRouter(prefix="/api/v1/geospatial", tags=["Geospatial & GIS"])

@router.get(
    "/risk-map",
    response_model=GeoJSONFeatureCollection,
    summary="Get Geospatial Risk Map",
    description="Retrieve latest risk assessments formatted as a standard GeoJSON FeatureCollection."
)
def get_risk_map(
    min_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    min_lon: Optional[float] = Query(None, ge=-180.0, le=180.0),
    max_lat: Optional[float] = Query(None, ge=-90.0, le=90.0),
    max_lon: Optional[float] = Query(None, ge=-180.0, le=180.0),
    risk_level: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    service: GeospatialService = Depends(get_geospatial_service)
):
    if (min_lat is not None and max_lat is not None and min_lat > max_lat) or \
       (min_lon is not None and max_lon is not None and min_lon > max_lon):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid bounding box parameters"
        )
        
    return service.get_risk_map(
        min_lat=min_lat,
        min_lon=min_lon,
        max_lat=max_lat,
        max_lon=max_lon,
        risk_level=risk_level,
        limit=limit
    )
