import logging
import sys
import os

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import EE_PROJECT_ID, ROI_BOUNDS
from src.etl.gee_extractor import initialize_gee, extract_dem, extract_vegetation
from src.features.physics_engine import calculate_slope, calculate_root_cohesion
import ee

logger = logging.getLogger(__name__)

def main():
    logger.info("Starting Phase 2: GIS Data Processing")
    
    if not EE_PROJECT_ID:
        logger.warning("EE_PROJECT_ID not set. Please update .env")
    
    # Initialize GEE
    success = initialize_gee(EE_PROJECT_ID)
    if not success:
        logger.error("Failed to initialize Earth Engine. Exiting.")
        return

    # Define a test region (e.g., a small bounding box)
    try:
        min_lon, min_lat, max_lon, max_lat = ROI_BOUNDS
        region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])
    except Exception as e:
        logger.error(f"Failed to create region geometry: {e}")
        return
        
    logger.info("Extracting DEM...")
    dem = extract_dem(region)
    if dem:
        logger.info("Calculating slope...")
        slope = calculate_slope(dem)
        
    logger.info("Extracting vegetation data...")
    veg = extract_vegetation(region)
    if veg:
        logger.info("Calculating root cohesion...")
        root_cohesion = calculate_root_cohesion(veg)
        
    logger.info("Phase 2 processing pipeline executed successfully.")

if __name__ == "__main__":
    main()
