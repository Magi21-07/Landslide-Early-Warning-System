import logging
import sys
import os
import pandas as pd
import ee

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.etl.inventory_builder import generate_inventory
from src.features.feature_sampler import sample_cloud_features, extract_soil_moisture
from src.config import ROI_BOUNDS, EE_PROJECT_ID
from src.etl.gee_extractor import initialize_gee, extract_dem, extract_vegetation
from src.features.physics_engine import calculate_slope, calculate_root_cohesion

logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger.info("Starting Phase 3: Cloud-Side Feature Extraction")
    
    success = initialize_gee(EE_PROJECT_ID)
    if not success:
        logger.error("Failed to initialize Earth Engine. Exiting.")
        return
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    raw_dir = os.path.join(base_dir, 'data', 'raw')
    processed_dir = os.path.join(base_dir, 'data', 'processed')
    
    roi_bounds = ROI_BOUNDS
    
    logger.info("Parsing inventory and generating negative samples...")
    df = generate_inventory(raw_dir, roi_bounds)
    
    if df.empty:
        logger.warning("No data returned from inventory generator.")
        return
        
    logger.info("Preparing Earth Engine Image Stack...")
    min_lon, min_lat, max_lon, max_lat = roi_bounds
    region = ee.Geometry.Rectangle([min_lon, min_lat, max_lon, max_lat])
    
    dem = extract_dem(region)
    slope = calculate_slope(dem)
    veg = extract_vegetation(region)
    root_cohesion = calculate_root_cohesion(veg)
    soil_moisture = extract_soil_moisture(region)
        
    if not all([dem, slope, veg, root_cohesion, soil_moisture]):
        logger.error("Failed to generate one or more GEE layers.")
        return
        
    image_stack = ee.Image([dem, slope, root_cohesion, soil_moisture])
    
    logger.info("Sampling raster features via GEE Cloud...")
    df = sample_cloud_features(df, image_stack)
    
    expected_cols = ['latitude', 'longitude', 'slope', 'root_cohesion', 'elevation', 'soil_moisture', 'label']
    for col in expected_cols:
        if col not in df.columns:
            df[col] = pd.Series(dtype=float)
            
    df = df[expected_cols]
    
    initial_len = len(df)
    df = df.dropna()
    final_len = len(df)
    logger.info(f"Dropped {initial_len - final_len} rows with NaN values. {final_len} rows remaining.")
    
    if not df.empty:
        pos_df = df[df['label'] == 1]
        neg_df = df[df['label'] == 0]
        min_len = min(len(pos_df), len(neg_df))
        if len(pos_df) > min_len:
            pos_df = pos_df.sample(n=min_len, random_state=42)
        if len(neg_df) > min_len:
            neg_df = neg_df.sample(n=min_len, random_state=42)
        df = pd.concat([pos_df, neg_df]).sample(frac=1, random_state=42).reset_index(drop=True)
        logger.info(f"Dataset balanced: {len(df)} total rows.")
        
    out_path = os.path.join(processed_dir, 'ml_dataset.csv')
    df.to_csv(out_path, index=False)
    logger.info(f"Exported final tabular dataset to {out_path}")
    
    print(f"\n--- DATASET GENERATION SUMMARY ---")
    print(f"Total rows in dataset: {len(df)}")
    if not df.empty:
        print(f"Label balance:\n{df['label'].value_counts().to_string()}")
    print(f"----------------------------------\n")

if __name__ == "__main__":
    main()
