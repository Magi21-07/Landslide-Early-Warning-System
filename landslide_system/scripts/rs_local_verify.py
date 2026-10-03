import sys
import os
import datetime
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.etl.sentinel_service import get_remote_sensing_features

coords = [
    ("Mount Everest", 27.9881, 86.9250),
    ("Wayanad, Kerala", 11.6854, 76.1320),
    ("Shimla, Himachal", 31.1048, 77.1734)
]

def main():
    for name, lat, lon in coords:
        print(f"\n======================================")
        print(f"Testing {name} ({lat}, {lon})")
        print(f"======================================")
        try:
            metrics = get_remote_sensing_features(lat, lon)
            d = metrics.to_api_dict()
            
            s2 = d.get('sentinel2', {})
            s1 = d.get('sentinel1', {})
            prov = d.get('_provenance', {})
            
            print(f"S2 NDVI: {s2.get('ndvi')} | Quality: {s2.get('quality')} | Date: {s2.get('observation_date')}")
            print(f"S1 VV: {s1.get('vv_db')} | VH: {s1.get('vh_db')} | Quality: {s1.get('quality')} | Date: {s1.get('observation_date')}")
            print(f"Provenance Cache Status: {prov.get('cache_status')}")
            print(f"S2 Status: {prov.get('sentinel2', {}).get('status')}")
            print(f"S1 Status: {prov.get('sentinel1', {}).get('status')}")
            
            # Assertions for the test
            assert s2.get('quality') in ["VALID", "UNAVAILABLE"], "Invalid S2 quality"
            assert s1.get('quality') in ["VALID", "UNAVAILABLE"], "Invalid S1 quality"
            assert prov.get('cache_status') in ["HIT", "MISS"], "Invalid cache status"
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == "__main__":
    main()
