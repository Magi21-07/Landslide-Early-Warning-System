import logging
import rasterio
from rasterio.features import rasterize
import geopandas as gpd
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

def align_vectors_to_grid(vector_path: str, template_raster_path: str, output_path: str) -> bool:
    """
    Rasterizes vector features to match a 30m uniform template raster.
    """
    try:
        # Load vector data
        gdf = gpd.read_file(vector_path)
        
        # Load template raster
        with rasterio.open(template_raster_path) as src:
            transform = src.transform
            shape = src.shape
            crs = src.crs
            
        # Ensure CRS match
        if gdf.crs != crs:
            gdf = gdf.to_crs(crs)
            
        # Rasterize
        shapes = ((geom, 1) for geom in gdf.geometry)
        rasterized = rasterize(
            shapes=shapes,
            out_shape=shape,
            transform=transform,
            fill=0,
            dtype=rasterio.uint8
        )
        
        # Write output
        profile = src.profile
        profile.update(dtype=rasterio.uint8, count=1)
        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(rasterized, 1)
            
        return True
    except Exception as e:
        logger.error(f"Error aligning vectors to grid: {e}")
        return False
