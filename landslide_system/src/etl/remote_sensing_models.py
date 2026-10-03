from typing import Optional, Dict, Any
from dataclasses import dataclass, field, asdict

@dataclass
class Sentinel2Metrics:
    ndvi: Optional[float] = None
    vegetation_change: Optional[float] = None
    ndwi: Optional[float] = None
    nbr: Optional[float] = None
    observation_date: Optional[str] = None
    cloud_percentage: Optional[float] = None
    quality: Optional[str] = None
    source: Optional[str] = None

@dataclass
class Sentinel1Metrics:
    vv_db: Optional[float] = None
    vh_db: Optional[float] = None
    vv_vh_metric: Optional[float] = None
    sar_soil_moisture_proxy: Optional[float] = None
    surface_condition_proxy: Optional[float] = None
    observation_date: Optional[str] = None
    quality: Optional[str] = None
    source: Optional[str] = None

@dataclass
class RemoteSensingMetrics:
    sentinel2: Sentinel2Metrics = field(default_factory=Sentinel2Metrics)
    sentinel1: Sentinel1Metrics = field(default_factory=Sentinel1Metrics)
    _provenance: Dict[str, Any] = field(default_factory=dict)
    
    def to_api_dict(self) -> Dict[str, Any]:
        return {
            "sentinel2": asdict(self.sentinel2),
            "sentinel1": asdict(self.sentinel1),
            "_provenance": self._provenance
        }
