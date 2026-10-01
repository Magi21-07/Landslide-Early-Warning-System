import os
import json
import logging
import pandas as pd
import numpy as np
from sklearn.model_selection import GroupShuffleSplit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def split_dataset():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    data_dir = os.path.join(base_dir, 'data', 'processed')
    
    input_file = os.path.join(data_dir, 'ml_dataset_prepared.csv')
    metadata_file = os.path.join(data_dir, 'feature_columns.json')
    
    # Check if files exist
    if not os.path.exists(input_file):
        logger.error(f"Prepared dataset not found at {input_file}")
        return
        
    if not os.path.exists(metadata_file):
        logger.error(f"Metadata file not found at {metadata_file}")
        return
        
    # Load Data
    df = pd.read_csv(input_file)
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
        
    feature_cols = metadata['feature_columns']
    target_col = metadata['target_column']
    lat_col = metadata['latitude_column']
    lon_col = metadata['longitude_column']
    
    # Leakage Detection
    # 1. Ensure features don't contain latitude or longitude
    for col in [lat_col, lon_col]:
        if col in feature_cols:
            logger.error(f"Data Leakage Risk: Feature list contains coordinate column '{col}'. Removing it.")
            feature_cols.remove(col)
            
    # 2. Pearson correlation with target
    logger.info("Checking Pearson correlation between features and target...")
    correlations = df[feature_cols].corrwith(df[target_col])
    for feature, corr in correlations.items():
        if abs(corr) > 0.85:
            logger.warning(f"HIGH CORRELATION LEAKAGE RISK: Feature '{feature}' has correlation of {corr:.3f} with target > 0.85")
            
    # Spatial Grid Splitting Algorithm
    # Create grid_id (round to 1 decimal place, ~11km)
    df['grid_id'] = df[lat_col].round(1).astype(str) + '_' + df[lon_col].round(1).astype(str)
    
    # GroupShuffleSplit (Train / Temp) -> 70% Train, 30% Temp
    gss_1 = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=42)
    train_idx, temp_idx = next(gss_1.split(df, groups=df['grid_id']))
    
    train_df = df.iloc[train_idx].copy()
    temp_df = df.iloc[temp_idx].copy()
    
    # GroupShuffleSplit (Val / Test) -> 50% Val, 50% Test of Temp (15% overall each)
    gss_2 = GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=42)
    val_idx, test_idx = next(gss_2.split(temp_df, groups=temp_df['grid_id']))
    
    val_df = temp_df.iloc[val_idx].copy()
    test_df = temp_df.iloc[test_idx].copy()
    
    # Validation Assertions
    # 1. Assert no spatial leakage (no intersection of grid_id)
    train_grids = set(train_df['grid_id'])
    val_grids = set(val_df['grid_id'])
    test_grids = set(test_df['grid_id'])
    
    assert len(train_grids.intersection(val_grids)) == 0, "Spatial leakage detected between train and val!"
    assert len(train_grids.intersection(test_grids)) == 0, "Spatial leakage detected between train and test!"
    assert len(val_grids.intersection(test_grids)) == 0, "Spatial leakage detected between val and test!"
    
    # 2. Assert all contain expected columns
    expected_cols = df.columns.tolist()
    assert all(train_df.columns == expected_cols), "Train set columns mismatch!"
    assert all(val_df.columns == expected_cols), "Val set columns mismatch!"
    assert all(test_df.columns == expected_cols), "Test set columns mismatch!"
    
    # 3. Assert target contains only 0 and 1
    for name, subset in zip(['Train', 'Val', 'Test'], [train_df, val_df, test_df]):
        unique_targets = set(subset[target_col].unique())
        assert unique_targets.issubset({0, 1}), f"{name} target contains invalid values: {unique_targets}"
        
    logger.info("All validation assertions passed successfully.")
    
    # Drop grid_id before saving
    train_df = train_df.drop(columns=['grid_id'])
    val_df = val_df.drop(columns=['grid_id'])
    test_df = test_df.drop(columns=['grid_id'])
    
    # Export Data
    train_file = os.path.join(data_dir, 'train.csv')
    val_file = os.path.join(data_dir, 'val.csv')
    test_file = os.path.join(data_dir, 'test.csv')
    
    train_df.to_csv(train_file, index=False)
    val_df.to_csv(val_file, index=False)
    test_df.to_csv(test_file, index=False)
    
    logger.info("Saved train, val, and test datasets.")
    
    # Helper to calculate stats
    def get_stats(data, grids):
        total = len(data)
        pos = (data[target_col] == 1).sum()
        pct = (pos / total * 100) if total > 0 else 0
        return {
            "sample_count": int(total),
            "positive_pct": float(round(pct, 2)),
            "negative_pct": float(round(100 - pct, 2)),
            "unique_grids": len(grids)
        }
        
    split_summary = {
        "spatial_grouping_strategy": "Grid grouping by rounding latitude/longitude to 1 decimal place (approx. 11km). Uses GroupShuffleSplit to prevent spatial leakage.",
        "splits": {
            "train": get_stats(train_df, train_grids),
            "val": get_stats(val_df, val_grids),
            "test": get_stats(test_df, test_grids)
        }
    }
    
    summary_file = os.path.join(data_dir, 'split_summary.json')
    with open(summary_file, 'w') as f:
        json.dump(split_summary, f, indent=2)
        
    logger.info(f"Exported split summary to {summary_file}")
    
    print("\n" + "="*50)
    print("DATASET SPLITTING SUMMARY")
    print("="*50)
    print(f"Strategy: {split_summary['spatial_grouping_strategy']}")
    print(f"Train samples: {len(train_df)} ({split_summary['splits']['train']['positive_pct']}% positive, {len(train_grids)} grids)")
    print(f"Val samples  : {len(val_df)} ({split_summary['splits']['val']['positive_pct']}% positive, {len(val_grids)} grids)")
    print(f"Test samples : {len(test_df)} ({split_summary['splits']['test']['positive_pct']}% positive, {len(test_grids)} grids)")
    print("Validation assertions passed: True")
    print("="*50 + "\n")

if __name__ == "__main__":
    split_dataset()
