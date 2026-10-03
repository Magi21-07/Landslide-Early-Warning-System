import logging
import datetime
import math
import os
import sqlite3
import json
from typing import Dict, Any, Optional

import ee
from src.etl.remote_sensing_models import RemoteSensingMetrics, Sentinel2Metrics, Sentinel1Metrics
from src.etl.gee_extractor import initialize_gee

logger = logging.getLogger(__name__)

# Cache setup
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rs_cache.db")
CACHE_TTL_DAYS = 7

def _init_cache():
    os.makedirs(os.path.dirname(CACHE_DB_PATH), exist_ok=True)
    with sqlite3.connect(CACHE_DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rs_cache (
                cache_key TEXT PRIMARY KEY,
                data TEXT,
                expires_at TEXT
            )
        """)

def _get_from_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    try:
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data, expires_at FROM rs_cache WHERE cache_key = ?", (cache_key,))
            row = cursor.fetchone()
            if row:
                data, expires_at = row
                if datetime.datetime.fromisoformat(expires_at) > datetime.datetime.now(datetime.timezone.utc):
                    return json.loads(data)
                else:
                    cursor.execute("DELETE FROM rs_cache WHERE cache_key = ?", (cache_key,))
                    conn.commit()
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
    return None

def _set_in_cache(cache_key: str, data: Dict[str, Any]):
    try:
        expires_at = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=CACHE_TTL_DAYS)).isoformat()
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO rs_cache (cache_key, data, expires_at) VALUES (?, ?, ?)",
                (cache_key, json.dumps(data), expires_at)
            )
    except Exception as e:
        logger.warning(f"Cache write error: {e}")

_init_cache()

def get_sentinel2_features(lat: float, lon: float, lookback_days: int = 30) -> Dict[str, Any]:
    """Extracts Sentinel-2 NDVI and other optical metrics using the COPERNICUS/S2_SR_HARMONIZED collection."""
    if not initialize_gee("credentials.json"): # Try with standard fallback
        return {"quality": "UNAVAILABLE", "status": "GEE_UNAVAILABLE"}

    try:
        point = ee.Geometry.Point([lon, lat])
        end_date = datetime.datetime.now(datetime.timezone.utc)
        start_date = end_date - datetime.timedelta(days=lookback_days)

        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(point) \
            .filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

        # Cloud filtering and masking
        # Join with S2_CLOUD_PROBABILITY
        s2_cloudless = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY") \
            .filterBounds(point) \
            .filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))

        filter_join = ee.Filter.equals(leftField='system:index', rightField='system:index')
        inner_join = ee.Join.inner()
        joined = ee.ImageCollection(inner_join.apply(s2, s2_cloudless, filter_join))

        def add_cloud_bands(image):
            img1 = ee.Image(image.get('primary'))
            img2 = ee.Image(image.get('secondary'))
            return img1.addBands(img2)

        s2_with_clouds = joined.map(add_cloud_bands)
        
        # Filter scene-level cloud percentage < 10%
        s2_with_clouds = s2_with_clouds.filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 10))

        if s2_with_clouds.size().getInfo() == 0:
            return {"quality": "UNAVAILABLE", "status": "NO_VALID_SCENE"}

        # Sort by most recent
        latest = s2_with_clouds.sort('system:time_start', False).first()

        # Cloud probability threshold (<= 30%)
        cloud_prob = latest.select('probability')
        is_clear = cloud_prob.lte(30)
        
        # SCL masking for cloud shadow (SCL == 3)
        scl = latest.select('SCL')
        not_shadow = scl.neq(3)
        mask = is_clear.And(not_shadow)

        latest_masked = latest.updateMask(mask)

        # Reflectance Scaling: DN to Reflectance
        b4 = latest_masked.select('B4').divide(10000.0)
        b8 = latest_masked.select('B8').divide(10000.0)

        # Calculate NDVI
        ndvi_img = b8.subtract(b4).divide(b8.add(b4).where(b8.add(b4).abs().lt(1e-6), 1e-6))
        
        # Calculate NDWI (B3 - B8) / (B3 + B8)
        b3 = latest_masked.select('B3').divide(10000.0)
        ndwi_img = b3.subtract(b8).divide(b3.add(b8).where(b3.add(b8).abs().lt(1e-6), 1e-6))
        
        # Calculate NBR (B8 - B12) / (B8 + B12)
        b12 = latest_masked.select('B12').divide(10000.0)
        nbr_img = b8.subtract(b12).divide(b8.add(b12).where(b8.add(b12).abs().lt(1e-6), 1e-6))

        # Reducers
        ndvi_val = ndvi_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=10).get('B8').getInfo()
        ndwi_val = ndwi_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=10).get('B3').getInfo()
        nbr_val = nbr_img.reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=10).get('B8').getInfo()

        date_millis = latest.get('system:time_start').getInfo()
        obs_date = datetime.datetime.fromtimestamp(date_millis / 1000.0, tz=datetime.timezone.utc).isoformat()
        cloud_pct = latest.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
        scene_id = latest.get('system:index').getInfo()

        return {
            "ndvi": float(ndvi_val) if ndvi_val is not None else None,
            "ndwi": float(ndwi_val) if ndwi_val is not None else None,
            "nbr": float(nbr_val) if nbr_val is not None else None,
            "observation_date": obs_date,
            "cloud_percentage": float(cloud_pct),
            "quality": "VALID",
            "status": "LATEST_AVAILABLE",
            "source": "COPERNICUS/S2_SR_HARMONIZED",
            "scene_id": scene_id
        }

    except Exception as e:
        logger.error(f"Error fetching Sentinel-2 features: {e}")
        return {"quality": "UNAVAILABLE", "status": "ERROR"}

def get_sentinel1_features(lat: float, lon: float, lookback_days: int = 30) -> Dict[str, Any]:
    """Extracts Sentinel-1 VV, VH backscatter using COPERNICUS/S1_GRD."""
    if not initialize_gee("credentials.json"):
        return {"quality": "UNAVAILABLE", "status": "GEE_UNAVAILABLE"}

    try:
        point = ee.Geometry.Point([lon, lat])
        end_date = datetime.datetime.now(datetime.timezone.utc)
        start_date = end_date - datetime.timedelta(days=lookback_days)

        s1 = ee.ImageCollection("COPERNICUS/S1_GRD") \
            .filterBounds(point) \
            .filterDate(start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH')) \
            .filter(ee.Filter.eq('instrumentMode', 'IW'))

        if s1.size().getInfo() == 0:
            return {"quality": "UNAVAILABLE", "status": "NO_VALID_SCENE"}

        # Sort by most recent
        latest = s1.sort('system:time_start', False).first()

        vv_val = latest.select('VV').reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=10).get('VV').getInfo()
        vh_val = latest.select('VH').reduceRegion(reducer=ee.Reducer.mean(), geometry=point, scale=10).get('VH').getInfo()

        vv_val = float(vv_val) if vv_val is not None else None
        vh_val = float(vh_val) if vh_val is not None else None

        vv_vh_metric = None
        if vv_val is not None and vh_val is not None:
            # Polarization relationship: VV_dB - VH_dB (log-difference representing backscatter cross-ratio)
            vv_vh_metric = vv_val - vh_val

        date_millis = latest.get('system:time_start').getInfo()
        obs_date = datetime.datetime.fromtimestamp(date_millis / 1000.0, tz=datetime.timezone.utc).isoformat()
        scene_id = latest.get('system:index').getInfo()
        orbit = latest.get('orbitProperties_pass').getInfo()

        return {
            "vv_db": vv_val,
            "vh_db": vh_val,
            "vv_vh_metric": vv_vh_metric,
            "sar_soil_moisture_proxy": vv_val, # Simple proxy
            "surface_condition_proxy": vh_val,
            "observation_date": obs_date,
            "quality": "VALID",
            "status": "LATEST_AVAILABLE",
            "source": "COPERNICUS/S1_GRD",
            "scene_id": scene_id,
            "orbit": orbit
        }
    except Exception as e:
        logger.error(f"Error fetching Sentinel-1 features: {e}")
        return {"quality": "UNAVAILABLE", "status": "ERROR"}

def get_remote_sensing_features(lat: float, lon: float) -> RemoteSensingMetrics:
    """Gets both Sentinel-1 and Sentinel-2 features, utilizing a 7-day cache."""
    cache_key = f"rs_v1_{round(lat, 3)}_{round(lon, 3)}"
    cached_data = _get_from_cache(cache_key)
    
    if cached_data:
        metrics = RemoteSensingMetrics(
            sentinel2=Sentinel2Metrics(**cached_data.get("sentinel2", {})),
            sentinel1=Sentinel1Metrics(**cached_data.get("sentinel1", {})),
            _provenance=cached_data.get("_provenance", {})
        )
        metrics._provenance["cache_status"] = "HIT"
        return metrics
    
    s2_data = get_sentinel2_features(lat, lon)
    s1_data = get_sentinel1_features(lat, lon)
    
    # We drop 'status' from kwargs for dataclass initialization
    s2_status = s2_data.pop("status", "UNAVAILABLE")
    s2_scene_id = s2_data.pop("scene_id", None)
    
    s1_status = s1_data.pop("status", "UNAVAILABLE")
    s1_scene_id = s1_data.pop("scene_id", None)
    s1_orbit = s1_data.pop("orbit", None)
    
    s2_metrics = Sentinel2Metrics(**s2_data)
    s1_metrics = Sentinel1Metrics(**s1_data)
    
    prov = {
        "cache_status": "MISS",
        "retrieval_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "sentinel2": {
            "status": s2_status,
            "scene_id": s2_scene_id,
            "native_resolution": "10m",
            "target_resolution": "30m",
            "processing_method": "gee_mean_reducer_point",
        },
        "sentinel1": {
            "status": s1_status,
            "scene_id": s1_scene_id,
            "orbit": s1_orbit,
            "native_resolution": "10m",
            "target_resolution": "30m",
            "processing_method": "gee_mean_reducer_point",
        }
    }
    
    metrics = RemoteSensingMetrics(sentinel2=s2_metrics, sentinel1=s1_metrics, _provenance=prov)
    _set_in_cache(cache_key, metrics.to_api_dict())
    
    return metrics
