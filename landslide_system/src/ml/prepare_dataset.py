import os
import json
import logging
import pandas as pd
import numpy as np
import shutil

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def prepare_dataset():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    data_dir = os.path.join(base_dir, 'data', 'processed')
    
    input_file = os.path.join(data_dir, 'ml_dataset.csv')
    raw_backup_file = os.path.join(data_dir, 'ml_dataset_raw.csv')
    prepared_file = os.path.join(data_dir, 'ml_dataset_prepared.csv')
    metadata_file = os.path.join(data_dir, 'feature_columns.json')
    
    # Target Validation
    if not os.path.exists(input_file):
        logger.error(f"Input file not found at {input_file}")
        return
        
    # Save a backup of the raw Phase-3 data
    shutil.copy2(input_file, raw_backup_file)
    logger.info(f"Backed up raw dataset to {raw_backup_file}")
    
    # Load Data
    df = pd.read_csv(input_file)
    total_samples_before = len(df)
    
    # Feature Mapping
    target_column = "label"
    latitude_column = "latitude"
    longitude_column = "longitude"
    feature_columns = ["slope", "root_cohesion", "elevation", "soil_moisture"]
    
    if target_column not in df.columns:
        raise ValueError(f"Target column '{target_column}' missing from dataset.")
        
    unique_classes = df[target_column].unique()
    if not (set(unique_classes) == {0, 1} or set(unique_classes) == {0} or set(unique_classes) == {1}):
        logger.warning(f"Target column contains classes other than 0 and 1: {unique_classes}")
        
    # Data Hygiene Checks
    # 1. Detect and report missing values
    missing_counts = df.isnull().sum()
    total_missing = missing_counts.sum()
    
    # 2. Detect and report duplicate coordinate rows
    coord_duplicates = df.duplicated(subset=[latitude_column, longitude_column]).sum()
    
    # 3. Check for infinite (inf/-inf) values
    numeric_df = df.select_dtypes(include=[np.number])
    inf_count = np.isinf(numeric_df).sum().sum()
    if inf_count > 0:
        logger.warning(f"Found {inf_count} infinite values in numeric columns.")
        df.replace([np.inf, -np.inf], np.nan, inplace=True)
        
    # 4. Validate that numeric features are correctly cast to float types
    for col in feature_columns + [latitude_column, longitude_column]:
        if col in df.columns:
            df[col] = df[col].astype(float)
            
    # Clean the dataset (drop missing and duplicates)
    df = df.dropna()
    df = df.drop_duplicates(subset=[latitude_column, longitude_column])
    
    # Dataset Serialization
    df.to_csv(prepared_file, index=False)
    
    # Metadata Export
    metadata = {
        "target_column": target_column,
        "feature_columns": feature_columns,
        "latitude_column": latitude_column,
        "longitude_column": longitude_column,
        "categorical_columns": [],
        "numeric_columns": feature_columns
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
        
    # Stats for output
    total_samples = len(df)
    pos_samples = (df[target_column] == 1).sum()
    neg_samples = (df[target_column] == 0).sum()
    pos_pct = (pos_samples / total_samples * 100) if total_samples > 0 else 0
    neg_pct = (neg_samples / total_samples * 100) if total_samples > 0 else 0
    
    # Logging & Console Output
    print("\n" + "="*50)
    print("DATASET PREPARATION SUMMARY")
    print("="*50)
    print(f"Total sample count: {total_samples}")
    print(f"Positive sample count (y=1): {pos_samples} ({pos_pct:.2f}%)")
    print(f"Negative sample count (y=0): {neg_samples} ({neg_pct:.2f}%)")
    print(f"Number of predictive features: {len(feature_columns)}")
    print(f"Missing value count detected: {total_missing}")
    print(f"Duplicate coordinate rows detected: {coord_duplicates}")
    if inf_count > 0:
         print(f"Infinite values detected & replaced: {inf_count}")
    print(f"Successfully exported metadata to: {metadata_file}")
    print("="*50 + "\n")

if __name__ == "__main__":
    prepare_dataset()
