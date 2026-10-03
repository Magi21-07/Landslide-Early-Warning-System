"""
src/etl/spatial_models.py
--------------------------
FC-3: Canonical data contract for static spatial factors.

This module defines the authoritative Python representation for all static
environmental factors produced by the FC-3 spatial ETL pipeline.

IMPORTANT: These factors are for data completeness and future ML retraining.
They are NOT passed into the active Phase-4 RandomForest model (which uses
exactly 4 features: slope_degrees, elevation_m, rainfall_3day, rainfall_15day).
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
import datetime


# ---------------------------------------------------------------------------
# Source / Quality Constants
# ---------------------------------------------------------------------------

class SourceStatus:
    REAL      = "REAL"       # Successfully retrieved from live source
    FALLBACK  = "FALLBACK"   # Live source failed; explicit fallback value used
    UNAVAILABLE = "UNAVAILABLE"  # No source exists for this factor
    MOCK      = "MOCK"       # Controlled test fixture (never activates in REAL mode)
    TEST      = "TEST"       # Deterministic test fixture


# ---------------------------------------------------------------------------
# Per-factor Provenance
# ---------------------------------------------------------------------------

@dataclass
class FactorProvenance:
    """Metadata tracking the origin and quality of a single static factor."""
    source:       str          # e.g. "SoilGrids_v2", "Overpass_OSM", "GLiM_v1"
    status:       str          # SourceStatus constant
    fallback_used: bool
    lookup_method: str         # e.g. "REST_API", "LOCAL_RASTER", "NONE"
    retrieved_at: Optional[str] = None   # ISO-8601 UTC
    notes:        Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Canonical Static Spatial Metrics
# ---------------------------------------------------------------------------

@dataclass
class StaticSpatialMetrics:
    """
    Canonical representation of all static environmental factors for a
    geographic point (lat, lon).

    All factor values follow strict provenance rules:
    - Never synthesize physical values from coordinate ranges.
    - Missing factors → None (not numeric 0).
    - Fallback values are always explicitly marked in _provenance.

    Units:
        clay_percent         : % (0–100)  — SoilGrids clay, decig/kg ÷ 10
        hydraulic_capacity   : % volumetric water content at field capacity (33 kPa)
                               "hydraulic_capacity" in this project = wv0033 (SoilGrids)
                               Unit: cm³/cm³ × 100 to express as % vol
        soil_depth           : cm  — SoilGrids BDRICM absolute depth to bedrock
        lithology_class      : categorical string (e.g. "Sedimentary", "Metamorphic")
        weathering_index     : float [0.0–1.0] proxy, or None if UNAVAILABLE
        distance_to_river_m  : metres ≥ 0  — nearest waterway line segment
        distance_to_road_m   : metres ≥ 0  — nearest highway line segment
    """
    # Core factors
    clay_percent:        Optional[float] = None
    hydraulic_capacity:  Optional[float] = None
    soil_depth:          Optional[float] = None
    lithology_class:     Optional[str]   = None
    weathering_index:    Optional[float] = None
    distance_to_river_m: Optional[float] = None
    distance_to_road_m:  Optional[float] = None

    # Quality summary
    data_quality: str = SourceStatus.UNAVAILABLE

    # ISO-8601 UTC timestamp
    retrieved_at: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    # Per-factor provenance — keyed by factor group
    _provenance: Dict[str, Dict] = field(default_factory=dict)

    # Coordinate echo (for consistency checks)
    latitude:  Optional[float] = None
    longitude: Optional[float] = None

    def set_provenance(self, key: str, prov: FactorProvenance) -> None:
        self._provenance[key] = prov.to_dict()

    def to_api_dict(self) -> Dict[str, Any]:
        """
        Serialise to the API response sub-object for 'spatial_metrics'.
        Includes _provenance so clients can audit data quality.
        """
        return {
            "clay_percent":        self.clay_percent,
            "hydraulic_capacity":  self.hydraulic_capacity,
            "soil_depth":          self.soil_depth,
            "lithology_class":     self.lithology_class,
            "weathering_index":    self.weathering_index,
            "distance_to_river_m": self.distance_to_river_m,
            "distance_to_road_m":  self.distance_to_road_m,
            "data_quality":        self.data_quality,
            "retrieved_at":        self.retrieved_at,
            "_provenance":         self._provenance,
        }

    def overall_quality(self) -> str:
        """
        Derive a summary quality label from individual provenance entries.
        REAL if all factors are REAL; PARTIAL if mixed; FALLBACK if all fallback.
        """
        statuses = {v.get("status") for v in self._provenance.values()}
        if not statuses:
            return SourceStatus.UNAVAILABLE
        if statuses == {SourceStatus.REAL}:
            return SourceStatus.REAL
        if SourceStatus.REAL in statuses:
            return "PARTIAL"
        if statuses <= {SourceStatus.FALLBACK, SourceStatus.UNAVAILABLE}:
            return SourceStatus.FALLBACK
        return SourceStatus.FALLBACK
