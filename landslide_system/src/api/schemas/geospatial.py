from typing import List, Literal, Tuple, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class PointGeometry(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: Tuple[float, float] = Field(
        ..., 
        description="GeoJSON coordinates strictly in [longitude, latitude] order"
    )

class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: Dict[str, Any]

class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: List[GeoJSONFeature]
    
    model_config = ConfigDict(from_attributes=True)
