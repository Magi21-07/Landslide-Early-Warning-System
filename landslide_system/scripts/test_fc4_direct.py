import sys
import os

# Add root to python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

locations = [
    {"name": "Wayanad, Kerala", "lat": 11.6854, "lon": 76.1320},
    {"name": "Mount Everest", "lat": 27.9881, "lon": 86.9250},
    {"name": "Shimla", "lat": 31.1046, "lon": 77.1734}
]

for loc in locations:
    print(f"\n--- Testing {loc['name']} ({loc['lat']}, {loc['lon']}) ---")
    resp = client.post(
        "/api/v1/risk/evaluate",
        json={"latitude": loc['lat'], "longitude": loc['lon']},
        headers={"X-API-Key": "dev-api-key-secret"}
    )
    if resp.status_code == 200:
        data = resp.json()
        print(f"Probability: {data.get('probability')}")
        print(f"Risk Level: {data.get('risk_level')}")
        print("Top 3 Factors:")
        for f in data.get('top_risk_factors', [])[:3]:
            print(f"  {f['factor']}: {f['contribution']}")
            
        # Verify 14 factors were used (via metadata)
        meta = data.get("factor_metadata", {})
        if meta:
            print(f"Extracted {len(meta)} factors.")
    else:
        print(f"FAILED: {resp.status_code} - {resp.text}")
