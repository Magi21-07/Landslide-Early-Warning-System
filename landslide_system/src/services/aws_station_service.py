import math
import json

# Mock AWS/IMD Station Registry (Regional)
# Realistically, this would be fetched live from an AWS/IMD API endpoint.
STATIONS = {
    "SHIMLA_AWS": {"lat": 31.1048, "lon": 77.1734, "rainfall_1h": 0.5, "rainfall_24h": 5.0, "rainfall_3day": 12.5},
    "KULLU_AWS": {"lat": 31.9579, "lon": 77.1095, "rainfall_1h": 0.0, "rainfall_24h": 2.0, "rainfall_3day": 8.0},
    "MANDI_AWS": {"lat": 31.5892, "lon": 76.9320, "rainfall_1h": 1.5, "rainfall_24h": 10.0, "rainfall_3day": 25.0},
    "DHARAMSHALA_AWS": {"lat": 32.2190, "lon": 76.3234, "rainfall_1h": 5.0, "rainfall_24h": 20.0, "rainfall_3day": 40.0},
    "RAMPUR_AWS": {"lat": 31.4485, "lon": 77.6293, "rainfall_1h": 0.0, "rainfall_24h": 1.0, "rainfall_3day": 5.0}
}

def haversine(lat1, lon1, lat2, lon2):
    """Calculate the great circle distance in kilometers between two points on the earth."""
    R = 6371.0 # Radius of earth in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_station_telemetry() -> dict:
    """
    Ingestion Function: Returns 1-hour, 24-hour, and 3-day cumulative 
    rainfall for active stations.
    """
    return STATIONS

def interpolate_aws_rainfall(target_lat: float, target_lon: float) -> dict:
    telemetry = get_station_telemetry()
    if not telemetry:
        return {
            "rainfall_3day_mm": 0.0,
            "nearest_station_id": None,
            "nearest_distance_km": float('inf'),
            "status": "FALLBACK_CHIRPS",
            "active_stations_count": 0
        }
        
    nearest_station = None
    min_dist = float('inf')
    
    weights = []
    values = []
    
    for stat_id, data in telemetry.items():
        dist = haversine(target_lat, target_lon, data["lat"], data["lon"])
        
        if dist < min_dist:
            min_dist = dist
            nearest_station = stat_id
            
        if dist < 0.01:
            # Zero-Distance Safeguard
            return {
                "rainfall_3day_mm": float(data["rainfall_3day"]),
                "nearest_station_id": stat_id,
                "nearest_distance_km": dist,
                "status": "LIVE_AWS_INTERPOLATED",
                "active_stations_count": len(telemetry)
            }
            
        w = 1.0 / (dist ** 2)
        weights.append(w)
        values.append(data["rainfall_3day"])
        
    if min_dist > 50.0:
        return {
            "rainfall_3day_mm": 0.0,
            "nearest_station_id": nearest_station,
            "nearest_distance_km": min_dist,
            "status": "FALLBACK_CHIRPS",
            "active_stations_count": len(telemetry)
        }
        
    interpolated_rainfall = sum(w * v for w, v in zip(weights, values)) / sum(weights)
    
    return {
        "rainfall_3day_mm": float(interpolated_rainfall),
        "nearest_station_id": nearest_station,
        "nearest_distance_km": min_dist,
        "status": "LIVE_AWS_INTERPOLATED",
        "active_stations_count": len(telemetry)
    }

if __name__ == "__main__":
    target_lat = 31.1070
    target_lon = 77.2100
    
    print(f"--- Interpolating AWS Rainfall for Target ({target_lat}, {target_lon}) ---")
    telemetry = get_station_telemetry()
    
    print(f"{'Station':<18} | {'Dist (km)':>10} | {'Weight (1/d^2)':>15} | {'3D Rain (mm)':>12}")
    print("-" * 65)
    for stat_id, data in telemetry.items():
        dist = haversine(target_lat, target_lon, data["lat"], data["lon"])
        w = 1.0 / (dist ** 2) if dist >= 0.01 else float('inf')
        print(f"{stat_id:<18} | {dist:>10.2f} | {w:>15.6f} | {data['rainfall_3day']:>12.2f}")
        
    result = interpolate_aws_rainfall(target_lat, target_lon)
    print("\nInterpolation Result:")
    print(json.dumps(result, indent=4))
    
    print("\n--- Testing Fallback Mechanism (>50km target: 20.0, 80.0) ---")
    fb_result = interpolate_aws_rainfall(20.0, 80.0)
    print(json.dumps(fb_result, indent=4))
