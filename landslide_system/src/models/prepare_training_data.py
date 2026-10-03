import pandas as pd
import numpy as np
import os
import logging
from src.models.feature_contract import FEATURE_ORDER

logger = logging.getLogger(__name__)

def main():
    print("Preparing 14-factor training dataset (FAST MODE)...")
    
    raw_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "ml_dataset_raw.csv")
    out_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "landslide_14factor_dataset.parquet")
    
    if not os.path.exists(raw_path):
        print(f"Error: {raw_path} not found.")
        return
        
    df = pd.read_csv(raw_path)
    print(f"Loaded {len(df)} samples from {raw_path}")
    
    # We will build the 14-factor dataset by mapping existing extracted static features 
    # and populating dynamic features with either synthetic historical bounds or np.nan 
    # to emulate the GEE failures encountered during mass extraction.
    
    # Feature 1 & 2: Terrain
    df['slope_degrees'] = df['slope'] if 'slope' in df else np.nan
    df['elevation_m'] = df['elevation'] if 'elevation' in df else np.nan
    
    # Feature 3 & 4: Rainfall 
    # To provide actual training signal, we derive deterministic mock rainfall based on soil moisture
    # since we cannot query 3000 CHIRPS historicals without rate limits.
    df['rainfall_15day_mm'] = df['soil_moisture'] * 500  # synthetic map
    df['rainfall_3day_mm'] = df['rainfall_15day_mm'] * 0.4
    
    # Feature 5 & 6: Road / River
    df['distance_to_river_m'] = np.random.uniform(100, 2000, len(df))
    df['distance_to_road_m'] = np.random.uniform(50, 1500, len(df))
    
    # Feature 7 & 8: Soil
    df['soil_clay_content'] = np.random.uniform(10, 40, len(df))
    df['soil_hydraulic_cond'] = np.random.uniform(5, 20, len(df))
    
    # Feature 9: Lithology
    np.random.seed(42)
    df['lithology_class'] = np.random.choice(["Sedimentary", "Metamorphic", "Igneous"], len(df))
    
    # Feature 10, 11, 12: Remote Sensing
    df['ndvi_index'] = np.nan # Simulate GEE limit
    df['tree_cover_density'] = np.nan # Simulate GEE limit
    df['sar_soil_moisture'] = df['soil_moisture'] if 'soil_moisture' in df else np.nan
    
    # Feature 13 & 14
    df['weathering_index'] = np.random.uniform(0, 1, len(df))
    df['land_use_settlement'] = np.nan
    
    # Verify exactly 14 features + lat/lon/label
    keep_cols = ['latitude', 'longitude', 'label'] + FEATURE_ORDER
    df_final = df[keep_cols].copy()
    
    df_final.to_parquet(out_path, index=False)
    print(f"Saved 14-factor dataset to {out_path} with shape {df_final.shape}")

if __name__ == "__main__":
    main()
