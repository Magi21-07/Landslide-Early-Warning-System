import sys
import os
import json
import logging
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.features.feature_builder import FeatureBuilder
from src.risk.rainfall_service import RainfallService
import ee

coords = [
    ("Mount Everest", 27.9881, 86.9250),
    ("Wayanad, Kerala", 11.6854, 76.1320),
    ("Shimla, Himachal", 31.1048, 77.1734)
]

def main():
    try:
        from src.etl.gee_extractor import initialize_gee
        initialize_gee("credentials.json")
    except Exception as e:
        print("GEE Init failed, will run with mock/unavailable:")
        print(e)
        
    rainfall_service = RainfallService("credentials.json")
    builder = FeatureBuilder(rainfall_service)
    
    for name, lat, lon in coords:
        print(f"\n======================================")
        print(f"Testing {name} ({lat}, {lon})")
        print(f"======================================")
        
        try:
            feats, meta = builder.get_features(lat, lon)
            
            print("--- STATIC ---")
            print(f"Slope: {feats.get('slope_degrees')}")
            print(f"Elevation: {feats.get('elevation_m')}")
            print(f"River Dist: {feats.get('distance_to_river_m')}")
            print(f"Road Dist: {feats.get('distance_to_road_m')}")
            print(f"Soil Clay: {feats.get('soil_clay_content')}")
            print(f"Lithology: {feats.get('lithology_class')}")
            
            print("\n--- DYNAMIC ---")
            print(f"Rainfall 3D: {feats.get('rainfall_3day_mm')}")
            print(f"Rainfall 15D: {feats.get('rainfall_15day_mm')}")
            print(f"NDVI: {feats.get('ndvi_index')}")
            print(f"Tree Cover: {feats.get('tree_cover_density')}")
            print(f"SAR Moisture: {feats.get('sar_soil_moisture')}")
            
            print("\n--- METADATA ---")
            print(json.dumps(meta, indent=2))
            
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    main()
