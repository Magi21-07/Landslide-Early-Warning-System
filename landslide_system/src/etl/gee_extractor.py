import ee
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

_GEE_INIT_FAILED = False

def initialize_gee(config_val: str) -> bool:
    global _GEE_INIT_FAILED
    if _GEE_INIT_FAILED:
        return False
        
    try:
        import os
        if config_val.endswith('.json'):
            # Assuming it's a relative path from the project root
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
            key_path = os.path.join(base_dir, config_val)
            if not os.path.exists(key_path):
                # Try relative to cwd
                key_path = config_val
                
            if os.path.exists(key_path):
                import json
                from google.oauth2 import service_account
                with open(key_path, 'r') as f:
                    key_data = json.load(f)
                project_id = key_data.get('project_id')
                credentials = service_account.Credentials.from_service_account_file(key_path, scopes=['https://www.googleapis.com/auth/earthengine'])
                ee.Initialize(credentials=credentials, project=project_id)
            else:
                logger.error(f"Key file not found: {key_path}")
                return False
        else:
            ee.Initialize(project=config_val)
            
        logger.info("Earth Engine initialized successfully.")
        return True
    except Exception as e:
        logger.warning(f"Failed to initialize Earth Engine: {e}")
        _GEE_INIT_FAILED = True
        return False



def extract_dem(region: ee.Geometry) -> Optional[ee.Image]:
    """
    Extracts NASADEM, reprojects to EPSG:4326 and scales to 30m.
    """
    try:
        dem = ee.Image("NASA/NASADEM_HGT/001").select('elevation')
        # Grid Unification
        dem_30m = dem.reproject(crs='EPSG:4326', scale=30)
        return dem_30m.clip(region)
    except Exception as e:
        logger.error(f"Error extracting DEM: {e}")
        return None

def extract_vegetation(region: ee.Geometry) -> Optional[ee.Image]:
    """
    Extracts Copernicus forest types or Hansen vegetation data.
    Reprojects to EPSG:4326 and scales to 30m.
    """
    try:
        # Example using Copernicus Global Land Cover
        landcover = ee.Image("COPERNICUS/Landcover/100m/Proba-V-C3/Global/2019").select('tree-coverfraction')
        # Grid Unification
        lc_30m = landcover.reproject(crs='EPSG:4326', scale=30)
        return lc_30m.clip(region)
    except Exception as e:
        logger.error(f"Error extracting vegetation data: {e}")
        return None
