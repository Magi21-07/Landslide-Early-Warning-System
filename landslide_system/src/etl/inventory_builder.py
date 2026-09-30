import os
import glob
import logging
import pandas as pd
import numpy as np
import geopandas as gpd
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

def find_inventory_file(raw_dir: str) -> Optional[str]:
    patterns = [
        "Global_Landslide_Catalog_Export_rows.csv.xls",
        "landslides.csv",
        "*.csv"
    ]
    for pattern in patterns:
        matches = glob.glob(os.path.join(raw_dir, pattern))
        if matches:
            return matches[0]
    return None

def generate_inventory(raw_dir: str, roi_bounds: Tuple[float, float, float, float]) -> pd.DataFrame:
    file_path = find_inventory_file(raw_dir)
    if not file_path:
        logger.error(f"No inventory file found in {raw_dir}")
        return pd.DataFrame(columns=['latitude', 'longitude', 'label'])
        
    logger.info(f"Loading inventory from {file_path}")
    try:
        df = pd.read_csv(file_path, on_bad_lines='skip')
    except Exception as e:
        logger.error(f"Error reading CSV: {e}")
        return pd.DataFrame(columns=['latitude', 'longitude', 'label'])
        
    lat_col = 'latitude' if 'latitude' in df.columns else 'lat' if 'lat' in df.columns else None
    lon_col = 'longitude' if 'longitude' in df.columns else 'lon' if 'lon' in df.columns else 'lng' if 'lng' in df.columns else None
    
    if not lat_col or not lon_col:
        logger.error("Could not find latitude/longitude columns in inventory.")
        return pd.DataFrame(columns=['latitude', 'longitude', 'label'])
        
    df = df.dropna(subset=[lat_col, lon_col])
    df = df[pd.to_numeric(df[lat_col], errors='coerce').notnull()]
    df = df[pd.to_numeric(df[lon_col], errors='coerce').notnull()]
    df[lat_col] = df[lat_col].astype(float)
    df[lon_col] = df[lon_col].astype(float)
    
    minx, miny, maxx, maxy = roi_bounds
    
    if 'country_name' in df.columns:
        pos_df = df[
            (df['country_name'] == 'India') |
            ((df[lon_col] >= minx) & (df[lon_col] <= maxx) &
             (df[lat_col] >= miny) & (df[lat_col] <= maxy))
        ].copy()
    else:
        pos_df = df[
            (df[lon_col] >= minx) & (df[lon_col] <= maxx) &
            (df[lat_col] >= miny) & (df[lat_col] <= maxy)
        ].copy()
    
    pos_df = pos_df[[lat_col, lon_col]].rename(columns={lat_col: 'latitude', lon_col: 'longitude'})
    pos_df['label'] = 1
    
    n_positive = len(pos_df)
    logger.info(f"Found {n_positive} positive landslide points in ROI.")
    
    if n_positive == 0:
        return pd.DataFrame(columns=['latitude', 'longitude', 'label'])
        
    gdf_pos = gpd.GeoDataFrame(
        pos_df, 
        geometry=gpd.points_from_xy(pos_df['longitude'], pos_df['latitude']),
        crs="EPSG:4326"
    )
    
    gdf_pos_proj = gdf_pos.to_crs("EPSG:3857")
    buffer_union = gdf_pos_proj.buffer(500).unary_union
    
    logger.info("Generating pseudo-absence points...")
    neg_points = []
    max_attempts = n_positive * 50
    attempts = 0
    
    while len(neg_points) < n_positive and attempts < max_attempts:
        rand_lons = np.random.uniform(minx, maxx, min(n_positive, 100))
        rand_lats = np.random.uniform(miny, maxy, min(n_positive, 100))
        
        test_gdf = gpd.GeoDataFrame(
            geometry=gpd.points_from_xy(rand_lons, rand_lats),
            crs="EPSG:4326"
        ).to_crs("EPSG:3857")
        
        for idx, point in test_gdf.iterrows():
            if len(neg_points) >= n_positive:
                break
            if not buffer_union.contains(point.geometry):
                p_4326 = gpd.GeoSeries([point.geometry], crs="EPSG:3857").to_crs("EPSG:4326").iloc[0]
                neg_points.append({'latitude': p_4326.y, 'longitude': p_4326.x, 'label': 0})
        
        attempts += 1
        
    neg_df = pd.DataFrame(neg_points)
    
    final_df = pd.concat([pos_df, neg_df], ignore_index=True)
    return final_df
