import requests
import numpy as np
import logging

logger = logging.getLogger(__name__)

def get_terrain_features(lat: float, lon: float) -> dict:
    """
    Queries dynamic elevation and estimates local terrain slope 
    by sampling surrounding grid points (+/- 0.005 degrees).
    """
    delta = 0.005
    locations = [
        {"latitude": lat, "longitude": lon},
        {"latitude": lat + delta, "longitude": lon},
        {"latitude": lat - delta, "longitude": lon},
        {"latitude": lat, "longitude": lon + delta},
        {"latitude": lat, "longitude": lon - delta},
    ]

    try:
        lat_str = ",".join(str(p["latitude"]) for p in locations)
        lon_str = ",".join(str(p["longitude"]) for p in locations)
        response = requests.get(
            f"https://api.open-meteo.com/v1/elevation?latitude={lat_str}&longitude={lon_str}",
            timeout=5
        )
        response.raise_for_status()
        elevations = response.json().get("elevation", [200.0] * 5)
    except Exception as e:
        logger.warning(f"Elevation API failed: {e}. Falling back to default.")
        # Pure math fallback if network API times out or goes offline
        elevations = [200.0] * 5

    center_elev = elevations[0]

    # Calculate slope angle in degrees from elevation gradients
    dz_dx = (elevations[3] - elevations[4]) / (2 * delta * 111000)
    dz_dy = (elevations[1] - elevations[2]) / (2 * delta * 111000)
    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = float(np.degrees(slope_rad))

    return {
        "elevation_m": round(center_elev, 1),
        "slope_degrees": round(slope_deg, 2)
    }
