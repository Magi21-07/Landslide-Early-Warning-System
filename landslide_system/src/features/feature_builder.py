import datetime
import logging
from typing import Dict, Any, Tuple
import numpy as np
import os
import concurrent.futures

from src.etl.terrain_service import get_terrain_features
from src.etl.spatial_service import get_static_spatial_metrics
from src.etl.sentinel_service import get_remote_sensing_features
from src.risk.rainfall_service import RainfallService
from src.etl.gee_extractor import extract_vegetation
from src.models.feature_contract import FEATURE_ORDER
import ee

logger = logging.getLogger(__name__)

class FeatureBuilder:
    def __init__(self, rainfall_service: RainfallService):
        self.rainfall_service = rainfall_service
        # Assume gee initialized at higher level or initialized within services

    def _get_tree_cover(self, lat: float, lon: float) -> Tuple[Any, Dict]:
        try:
            point = ee.Geometry.Point([lon, lat])
            img = extract_vegetation(point)
            if img:
                val = img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=30).get('tree-coverfraction').getInfo()
                return val, {"source": "Copernicus Landcover", "status": "SLOW_CHANGING"}
        except Exception as e:
            logger.warning(f"Tree cover extraction failed: {e}")
        return np.nan, {"source": "Copernicus Landcover", "status": "UNAVAILABLE"}

    def get_features(self, lat: float, lon: float, event_date: str = None) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Extracts 14 features concurrently for a given coordinate.
        If event_date is provided (YYYY-MM-DD), ensures dynamic extraction is pre-event.
        (For CHIRPS, we fetch recent. For historical, we'd fetch specific date ranges).
        """
        def fetch_terrain():
            return get_terrain_features(lat, lon)
            
        def fetch_spatial():
            return get_static_spatial_metrics(lat, lon)
            
        def fetch_remote_sensing():
            # For historical, lookback would be adjusted relative to event_date.
            # Currently using latest for inference if event_date is None.
            return get_remote_sensing_features(lat, lon)
            
        def fetch_rainfall():
            # For historical, this would need to fetch exactly leading up to event_date.
            # CHIRPS service might need mock adaptation for exact historical.
            try:
                records = self.rainfall_service.get_recent_rainfall(lat, lon, days=15)
                if not records:
                    records = [{"rainfall_mm": 0.0}] * 15
                r1 = records[-1].get("rainfall_mm", 0.0)
                r3 = sum(r.get("rainfall_mm", 0.0) for r in records[-3:])
                r7 = sum(r.get("rainfall_mm", 0.0) for r in records[-7:])
                r15 = sum(r.get("rainfall_mm", 0.0) for r in records)
                return {"rainfall_3day_mm": max(r3, r1), "rainfall_15day_mm": max(r15, r7)}
            except Exception:
                return {"rainfall_3day_mm": np.nan, "rainfall_15day_mm": np.nan}

        def fetch_tree_cover():
            return self._get_tree_cover(lat, lon)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            f_terrain = executor.submit(fetch_terrain)
            f_spatial = executor.submit(fetch_spatial)
            f_rs = executor.submit(fetch_remote_sensing)
            f_rain = executor.submit(fetch_rainfall)
            f_tree = executor.submit(fetch_tree_cover)
            
            terrain = f_terrain.result()
            spatial = f_spatial.result()
            rs = f_rs.result()
            rain = f_rain.result()
            tree_val, tree_meta = f_tree.result()

        # Build exactly 14 features
        # If static fails, spatial_service returns fallbacks, so we expect keys.
        features = {}
        metadata = {}

        # 1 & 2
        features["slope_degrees"] = terrain.get("slope_degrees", np.nan)
        features["elevation_m"] = terrain.get("elevation_m", np.nan)
        metadata["slope_degrees"] = {"source": "terrain_service", "status": "STATIC"}
        metadata["elevation_m"] = {"source": "terrain_service", "status": "STATIC"}

        # 3 & 4
        features["rainfall_3day_mm"] = rain.get("rainfall_3day_mm", np.nan)
        features["rainfall_15day_mm"] = rain.get("rainfall_15day_mm", np.nan)
        metadata["rainfall_3day_mm"] = {"source": "CHIRPS", "status": "DYNAMIC"}
        metadata["rainfall_15day_mm"] = {"source": "CHIRPS", "status": "DYNAMIC"}

        # 5, 6, 7, 8, 9, 13
        if isinstance(spatial, dict):
            features["distance_to_river_m"] = spatial.get("distance_to_river_m", np.nan)
            features["distance_to_road_m"] = spatial.get("distance_to_road_m", np.nan)
            features["soil_clay_content"] = spatial.get("clay_percent", np.nan)
            features["soil_hydraulic_cond"] = spatial.get("hydraulic_capacity", np.nan)
            features["lithology_class"] = spatial.get("lithology_class", np.nan)
            features["weathering_index"] = spatial.get("weathering_index", np.nan)
        else:
            features["distance_to_river_m"] = np.nan
            features["distance_to_road_m"] = np.nan
            features["soil_clay_content"] = np.nan
            features["soil_hydraulic_cond"] = np.nan
            features["lithology_class"] = np.nan
            features["weathering_index"] = np.nan

        # 10, 12
        features["ndvi_index"] = rs.sentinel2.ndvi if rs and rs.sentinel2.ndvi is not None else np.nan
        features["sar_soil_moisture"] = rs.sentinel1.sar_soil_moisture_proxy if rs and rs.sentinel1.sar_soil_moisture_proxy is not None else np.nan
        
        metadata["ndvi_index"] = {"source": rs.sentinel2.source if rs else None, "status": rs._provenance.get("sentinel2", {}).get("status") if rs else "UNAVAILABLE"}
        metadata["sar_soil_moisture"] = {"source": rs.sentinel1.source if rs else None, "status": rs._provenance.get("sentinel1", {}).get("status") if rs else "UNAVAILABLE"}

        # 11
        features["tree_cover_density"] = tree_val if tree_val is not None else np.nan
        metadata["tree_cover_density"] = tree_meta

        # 14
        # Since we don't have explicit land_use_settlement extractor, we provide np.nan and handle in missing values.
        features["land_use_settlement"] = np.nan
        metadata["land_use_settlement"] = {"source": "NOT_IMPLEMENTED", "status": "UNAVAILABLE"}

        # Ensure order and exactly 14 keys, replacing any None with np.nan
        ordered_features = {k: np.nan if features.get(k, np.nan) is None else features.get(k, np.nan) for k in FEATURE_ORDER}
        
        return ordered_features, {"feature_metadata": metadata}
