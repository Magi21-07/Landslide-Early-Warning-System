import ee
import logging
import pandas as pd

logger = logging.getLogger(__name__)

def extract_soil_moisture(region: ee.Geometry) -> ee.Image:
    try:
        dataset = ee.ImageCollection("NASA/GLDAS/V021/NOAH/G025/T3H").filterBounds(region).filterDate('2020-01-01', '2020-01-02')
        return dataset.select('SoilMoi0_10cm_inst').mean().rename('soil_moisture')
    except Exception as e:
        logger.error(f"Error extracting soil moisture: {e}")
        return None

def sample_cloud_features(df: pd.DataFrame, image_stack: ee.Image) -> pd.DataFrame:
    """
    Samples pixel values directly on Google's cloud using sampleRegions.
    """
    if df.empty:
        logger.warning("Empty DataFrame provided to sample_cloud_features.")
        return df

    features = []
    for _, row in df.iterrows():
        geom = ee.Geometry.Point([row['longitude'], row['latitude']])
        feature = ee.Feature(geom, {'label': int(row['label'])})
        features.append(feature)
        
    fc = ee.FeatureCollection(features)
    
    logger.info("Calling sampleRegions on Earth Engine...")
    try:
        sampled = image_stack.sampleRegions(
            collection=fc,
            scale=30,
            geometries=True,
            tileScale=16
        )
        
        sampled_info = sampled.getInfo()
        
        sampled_features = sampled_info.get('features', [])
        records = []
        for feat in sampled_features:
            props = feat.get('properties', {})
            coords = feat.get('geometry', {}).get('coordinates', [None, None])
            records.append({
                'longitude': coords[0],
                'latitude': coords[1],
                'elevation': props.get('elevation'),
                'slope': props.get('slope'),
                'root_cohesion': props.get('root_cohesion'),
                'soil_moisture': props.get('soil_moisture'),
                'label': props.get('label')
            })
            
        final_df = pd.DataFrame(records)
        return final_df
    except Exception as e:
        logger.error(f"Error during cloud sampling: {e}")
        return pd.DataFrame(columns=['latitude', 'longitude', 'slope', 'root_cohesion', 'elevation', 'soil_moisture', 'label'])
