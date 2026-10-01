from typing import Optional, List, Union, Dict, Any
from datetime import datetime, date
from pydantic import BaseModel, ConfigDict

class RainfallObservation(BaseModel):
    """A single rainfall observation element."""
    date: date
    rainfall_mm: Optional[float] = None

class RainfallResponse(BaseModel):
    """
    Response schema for raw or processed rainfall data.
    """
    latitude: float
    longitude: float
    
    observation_date: Union[date, str]
    rainfall_observations: List[Union[float, Dict[str, Any], RainfallObservation]]
    
    units: str = "mm"
    source: str
    retrieval_timestamp: datetime
    
    
    model_config = ConfigDict(from_attributes=True)

class RainfallSummaryResponse(BaseModel):
    """
    Summary features calculated from rainfall.
    """
    latitude: float
    longitude: float
    rainfall_1d: Optional[float] = None
    rainfall_3d: Optional[float] = None
    rainfall_7d: Optional[float] = None
    rainfall_15d: Optional[float] = None
    api_15: Optional[float] = None
    rainfall_trigger_state: str
    rainfall_trigger_score: int
    
    model_config = ConfigDict(from_attributes=True)
