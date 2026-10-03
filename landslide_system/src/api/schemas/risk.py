from typing import Optional, List, Any, Dict
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict, Field

class RiskResponse(BaseModel):
    """
    Complete Phase 5 risk result representation.
    Maps to the DynamicRiskAssessment, LocationRiskState, and RiskStore history records.
    Extended in FC-4 with 14-factor ML inference fields.
    """
    location_id: Optional[str] = None
    latitude: float
    longitude: float
    
    susceptibility_probability: Optional[float] = None
    susceptibility_class: Optional[str] = None
    
    rainfall_1d: Optional[float] = None
    rainfall_3d: Optional[float] = None
    rainfall_7d: Optional[float] = None
    rainfall_15d: Optional[float] = None
    
    rainfall_trigger_state: Optional[str] = None
    rainfall_trigger_score: Optional[int] = None
    
    terrain_metrics: Optional[dict] = None
    rainfall_metrics: Optional[dict] = None
    spatial_metrics: Optional[dict] = None
    remote_sensing_metrics: Optional[dict] = None
    daily_rainfall: Optional[list] = None
    probability: Optional[float] = None
    top_risk_factors: Optional[list] = None

    # FC-4: 14-factor provenance and mini-metrics
    factor_metadata: Optional[Dict[str, Any]] = None
    data_mode: Optional[str] = None          # REAL | MOCK | TEST
    model_info: Optional[str] = None
    ndvi: Optional[float] = None             # NDVI index for dashboard mini-metric
    sar_moisture_proxy: Optional[float] = None  # SAR VV dB proxy — NOT volumetric soil moisture
    distance_to_river_m: Optional[float] = None

    # In some models (like SQLite history), final_risk_level is mapped as dynamic_risk
    # We will alias if needed or provide both.
    dynamic_risk: Optional[str] = Field(None, validation_alias="final_risk_level")
    risk_level: Optional[str] = None
    
    reasons: Optional[List[str]] = None
    
    observation_date: Optional[date] = None
    timestamp: datetime
    data_source: Optional[str] = None
    
    stale: bool = False
    error_info: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
