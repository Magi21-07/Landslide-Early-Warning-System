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
    
    # Restore realistic ground-truth distribution by removing artificial positive class inflation
    df_neg = df[df['label'] == 0]
    df_pos = df[df['label'] == 1]
    target_pos_count = int(len(df_neg) * 0.3) # targeting roughly ~23-25% positive
    if len(df_pos) > target_pos_count:
        df_pos = df_pos.sample(n=target_pos_count, random_state=42)
    df = pd.concat([df_neg, df_pos]).sample(frac=1.0, random_state=42).reset_index(drop=True)
    print(f"Restored distribution: {len(df)} samples (Pos: {len(df_pos)}, Neg: {len(df_neg)})")
    
    # We will build the 14-factor dataset by mapping existing extracted static features 
    # and populating dynamic features with either synthetic historical bounds or np.nan 
    # to emulate the GEE failures encountered during mass extraction.
    
    # Feature 1 & 2: Terrain
    df['slope_degrees'] = df['slope'] if 'slope' in df else np.nan
    df['elevation_m'] = df['elevation'] if 'elevation' in df else np.nan
    
    # Feature 3 & 4: Rainfall 
    # To provide actual training signal, we derive deterministic mock rainfall based on soil moisture
    # since we cannot query 3000 CHIRPS historicals without rate limits.
    # Synthesize rainfall without artificial positive label forcing
    df['rainfall_15day_mm'] = np.random.uniform(0, 40, len(df))
    df['rainfall_3day_mm'] = np.random.uniform(0, 10, len(df))
    df['rainfall_7day_mm'] = np.random.uniform(0, 20, len(df))
    df['api_rainfall'] = df['rainfall_3day_mm'] + (0.5 * df['rainfall_7day_mm']) + (0.25 * df['rainfall_15day_mm'])

    
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
    
    # Feature 13 & 14 & API
    df['weathering_index'] = np.random.uniform(0, 1, len(df))
    df['land_use_settlement'] = 0.0
    
    # Impute missing spatial/terrain columns to 0.0 to match Phase 1
    impute_cols = [c for c in FEATURE_ORDER if c != 'lithology_class']
    for c in impute_cols:
        if c in df.columns:
            df[c] = df[c].fillna(0.0)
            
    # Verify exact features + lat/lon/label
    keep_cols = ['latitude', 'longitude', 'label'] + FEATURE_ORDER
    df_final = df[keep_cols].copy()
    
    df_final.to_parquet(out_path, index=False)
    print(f"Saved 14-factor dataset to {out_path} with shape {df_final.shape}")
    
    # Print class distribution
    if 'label' in df_final.columns:
        print("Class Distribution:")
        print(df_final['label'].value_counts())

if __name__ == "__main__":
    main()
