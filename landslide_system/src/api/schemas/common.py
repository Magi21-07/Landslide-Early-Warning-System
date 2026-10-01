from typing import Optional, Union, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

class CoordinateRequest(BaseModel):
    """Base request for any operation requiring a geographic point."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="WGS84 latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="WGS84 longitude")
    
    model_config = ConfigDict(from_attributes=True)

class ErrorResponse(BaseModel):
    """Standardized error response format."""
    error_code: Union[str, int]
    message: str
    details: Optional[Union[Dict[str, Any], str]] = None
    request_id: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)
