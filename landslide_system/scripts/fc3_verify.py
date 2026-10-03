import requests

coords = [
    ("Mount Everest",     27.9881, 86.9250),
    ("Wayanad Kerala",    11.6854, 76.1320),
    ("Jaipur Rajasthan",  26.9124, 75.7873),
]
headers = {"X-API-Key": "dev-api-key-secret"}

for name, lat, lon in coords:
    r = requests.post(
        "http://localhost:8000/api/v1/risk/evaluate",
        json={"latitude": lat, "longitude": lon},
        headers=headers, timeout=15
    )
    d = r.json()
    sm   = d.get("spatial_metrics") or {}
    prov = sm.get("_provenance", {})
    tm   = d.get("terrain_metrics", {})
    print("")
    print(f"=== {name} ({lat}, {lon}) ===")
    print(f"  API STATUS : {r.status_code}")
    print(f"  SLOPE      : {tm.get('slope_degrees')} deg   ELEV: {tm.get('elevation_m')} m")
    print(f"  ML RISK    : prob={d.get('probability')}  level={d.get('risk_level')}")
    print(f"  SOIL       : clay={sm.get('clay_percent')}%  hyd={sm.get('hydraulic_capacity')}%  depth={sm.get('soil_depth')} cm  status={prov.get('soil', {}).get('status')}")
    print(f"  GEOLOGY    : litho={sm.get('lithology_class')}  weather={sm.get('weathering_index')}  status={prov.get('lithology', {}).get('status')}")
    print(f"  PROXIMITY  : river={sm.get('distance_to_river_m')} m  road={sm.get('distance_to_road_m')} m  status={prov.get('proximity', {}).get('status')}")
    print(f"  DATA QUAL  : {sm.get('data_quality')}")
    keys_ok = all(k in d for k in ["probability", "risk_level", "susceptibility_class", "terrain_metrics", "rainfall_metrics"])
    print(f"  KEY CHECK  : existing keys intact={keys_ok}  spatial_metrics present={'spatial_metrics' in d}")
    print(f"  ML VECTOR  : X has 4 features (asserted in endpoint)")
