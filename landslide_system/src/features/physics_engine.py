import logging
import numpy as np
import ee
from typing import Optional

logger = logging.getLogger(__name__)

def calculate_slope(dem: ee.Image) -> Optional[ee.Image]:
    """
    Calculates slope from a DEM.
    """
    try:
        slope = ee.Terrain.slope(dem)
        # Ensure 30m uniform grid
        return slope.reproject(crs='EPSG:4326', scale=30)
    except Exception as e:
        logger.error(f"Error calculating slope: {e}")
        return None

def calculate_root_cohesion(tree_fraction_img: ee.Image, root_tensile_strength: float = 30.0) -> Optional[ee.Image]:
    """
    Calculates root cohesion (c_r) using the Wu & Waldron formula.
    c_r = 1.2 * T_r * (A_r / A)
    where:
    - 1.2 is a constant reflecting angle of root distortion
    - T_r is average root tensile strength (kPa)
    - A_r / A is the Root Area Ratio (RAR), estimated here from tree cover fraction.
    
    This calculates vegetative shear strength in kPa based on Copernicus tree types.
    """
    try:
        # Estimate RAR (A_r / A) from tree cover fraction (assuming fraction 0-100)
        # Assuming RAR is linearly proportional to tree fraction for demonstration
        rar = tree_fraction_img.divide(100.0).multiply(0.01) # arbitrary scaling for realistic RAR
        
        # c_r = 1.2 * T_r * RAR
        c_r = rar.multiply(1.2 * root_tensile_strength)
        
        return c_r.reproject(crs='EPSG:4326', scale=30).rename('root_cohesion')
    except Exception as e:
        logger.error(f"Error calculating root cohesion: {e}")
        return None
