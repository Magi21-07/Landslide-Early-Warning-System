from typing import List, Dict, Any

# Exact semantic feature order
FEATURE_ORDER: List[str] = [
    "slope_degrees",
    "elevation_m",
    "rainfall_3day_mm",
    "rainfall_15day_mm",
    "distance_to_river_m",
    "distance_to_road_m",
    "soil_clay_content",
    "soil_hydraulic_cond",
    "lithology_class",
    "ndvi_index",
    "tree_cover_density",
    "sar_soil_moisture",
    "weathering_index",
    "land_use_settlement"
]

FEATURE_CONTRACT: Dict[str, Dict[str, Any]] = {
    "slope_degrees": {
        "semantic_meaning": "Terrain Slope",
        "source": "SRTM/NASADEM (terrain_service)",
        "static_dynamic": "STATIC",
        "unit": "Degrees",
        "expected_type": "float"
    },
    "elevation_m": {
        "semantic_meaning": "Elevation",
        "source": "SRTM/NASADEM (terrain_service)",
        "static_dynamic": "STATIC",
        "unit": "Meters",
        "expected_type": "float"
    },
    "rainfall_3day_mm": {
        "semantic_meaning": "Rainfall (3-Day)",
        "source": "CHIRPS (rainfall_service)",
        "static_dynamic": "DYNAMIC",
        "unit": "mm",
        "expected_type": "float"
    },
    "rainfall_15day_mm": {
        "semantic_meaning": "Rainfall (15-Day)",
        "source": "CHIRPS (rainfall_service)",
        "static_dynamic": "DYNAMIC",
        "unit": "mm",
        "expected_type": "float"
    },
    "distance_to_river_m": {
        "semantic_meaning": "Distance to River",
        "source": "Overpass OSM (spatial_service)",
        "static_dynamic": "STATIC",
        "unit": "Meters",
        "expected_type": "float"
    },
    "distance_to_road_m": {
        "semantic_meaning": "Distance to Road",
        "source": "Overpass OSM (spatial_service)",
        "static_dynamic": "STATIC",
        "unit": "Meters",
        "expected_type": "float"
    },
    "soil_clay_content": {
        "semantic_meaning": "Soil Clay Content",
        "source": "SoilGrids v2 (spatial_service)",
        "static_dynamic": "STATIC",
        "unit": "Percent",
        "expected_type": "float"
    },
    "soil_hydraulic_cond": {
        "semantic_meaning": "Soil Hydraulic Property",
        "source": "SoilGrids v2 (spatial_service)",
        "static_dynamic": "STATIC",
        "unit": "Percent vol",
        "expected_type": "float"
    },
    "lithology_class": {
        "semantic_meaning": "Lithology",
        "source": "GLiM v1 (spatial_service fallback)",
        "static_dynamic": "STATIC",
        "unit": "Categorical",
        "expected_type": "str"
    },
    "ndvi_index": {
        "semantic_meaning": "Vegetation Index (NDVI)",
        "source": "Sentinel-2 MSI (sentinel_service)",
        "static_dynamic": "DYNAMIC",
        "unit": "Unitless",
        "expected_type": "float"
    },
    "tree_cover_density": {
        "semantic_meaning": "Tree Cover Density",
        "source": "Copernicus Landcover (gee_extractor)",
        "static_dynamic": "SLOW_CHANGING",
        "unit": "Fraction (0-100)",
        "expected_type": "float"
    },
    "sar_soil_moisture": {
        "semantic_meaning": "SAR Soil-Moisture Proxy",
        "source": "Sentinel-1 GRD (sentinel_service)",
        "static_dynamic": "DYNAMIC",
        "unit": "dB proxy",
        "expected_type": "float"
    },
    "weathering_index": {
        "semantic_meaning": "Weathering",
        "source": "spatial_service",
        "static_dynamic": "STATIC",
        "unit": "Unitless",
        "expected_type": "float"
    },
    "land_use_settlement": {
        "semantic_meaning": "Settlement / Land-Use Exposure",
        "source": "Overpass OSM / Dynamic",
        "static_dynamic": "STATIC",
        "unit": "Binary/Fraction",
        "expected_type": "float"
    }
}
