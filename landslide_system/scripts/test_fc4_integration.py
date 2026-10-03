import asyncio
import json
import httpx
import time

async def test_location(client, lat, lon, name):
    print(f"\n--- Testing {name} ({lat}, {lon}) ---")
    start = time.time()
    try:
        resp = await client.post(
            "http://localhost:8000/api/v1/risk/evaluate",
            json={"latitude": lat, "longitude": lon},
            headers={"X-API-Key": "test_dev_key"},
            timeout=15.0
        )
        duration = time.time() - start
        
        if resp.status_code != 200:
            print(f"FAILED (Status {resp.status_code}): {resp.text}")
            return False
            
        data = resp.json()
        
        # Verify 14 semantic features indirectly (via backend integrity assertions or output fields)
        prob = data.get("probability")
        risk_level = data.get("risk_level")
        top_factors = data.get("top_risk_factors", [])
        
        print(f"Success in {duration:.2f}s")
        print(f"Probability: {prob}")
        print(f"Risk Level: {risk_level}")
        print(f"Top 3 Factors:")
        for f in top_factors[:3]:
            print(f"  {f['factor']}: {f['contribution']}")
            
        return True
    except Exception as e:
        print(f"FAILED (Exception): {e}")
        return False

async def main():
    async with httpx.AsyncClient() as client:
        # Wayanad
        w = await test_location(client, 11.6854, 76.1320, "Wayanad, Kerala")
        # Everest
        e = await test_location(client, 27.9881, 86.9250, "Mount Everest")
        # Shimla
        s = await test_location(client, 31.1046, 77.1734, "Shimla")

if __name__ == "__main__":
    asyncio.run(main())
