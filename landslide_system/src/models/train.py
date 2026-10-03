import pandas as pd
import numpy as np
import os
import pickle
import json
import shap
import xgboost as xgb
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.metrics import (roc_auc_score, average_precision_score, accuracy_score, 
                             precision_score, recall_score, f1_score, confusion_matrix)
from src.models.feature_contract import FEATURE_ORDER

def load_data():
    base_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'processed')
    dataset_path = os.path.join(base_dir, 'landslide_14factor_dataset.parquet')
    
    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"14-factor dataset not found at {dataset_path}. Run prepare_training_data.py first.")
        
    df = pd.read_parquet(dataset_path)
    
    # Load original split coordinates to maintain spatial leakage prevention
    train_orig = pd.read_csv(os.path.join(base_dir, 'train.csv'))
    val_orig = pd.read_csv(os.path.join(base_dir, 'val.csv'))
    test_orig = pd.read_csv(os.path.join(base_dir, 'test.csv'))
    
    # Merge to split
    # Using small tolerance for float matching if needed, but exact match should work since it's the same seed dataset
    train_df = df.merge(train_orig[['latitude', 'longitude']], on=['latitude', 'longitude'], how='inner')
    val_df = df.merge(val_orig[['latitude', 'longitude']], on=['latitude', 'longitude'], how='inner')
    test_df = df.merge(test_orig[['latitude', 'longitude']], on=['latitude', 'longitude'], how='inner')
    
    return train_df, val_df, test_df

def main():
    print("Loading datasets...")
    train_df, val_df, test_df = load_data()
    
    X_train = train_df[FEATURE_ORDER]
    y_train = train_df['label']
    X_val = val_df[FEATURE_ORDER]
    y_val = val_df['label']
    X_test = test_df[FEATURE_ORDER]
    y_test = test_df['label']
    
    print(f"Train size: {len(X_train)}, Val size: {len(X_val)}, Test size: {len(X_test)}")
    
    # Categorical handling: lithology_class
    # We will use ColumnTransformer, ensuring output is pandas DataFrame to preserve feature names for SHAP
    categorical_features = ['lithology_class']
    # All other features are numerical, we passthrough them. We don't scale for XGBoost.
    numerical_features = [f for f in FEATURE_ORDER if f not in categorical_features]
    
    preprocessor = ColumnTransformer(
        transformers=[
            ('cat', OneHotEncoder(handle_unknown='ignore', sparse_output=False), categorical_features),
            ('num', 'passthrough', numerical_features)
        ],
        remainder='drop',
        verbose_feature_names_out=False
    )
    
    preprocessor.set_output(transform="pandas")
    
    print("Fitting preprocessor...")
    X_train_transformed = preprocessor.fit_transform(X_train)
    X_val_transformed = preprocessor.transform(X_val)
    X_test_transformed = preprocessor.transform(X_test)
    
    # Save a mapping of transformed feature -> original feature
    feature_mapping = {}
    for col in X_train_transformed.columns:
        if col in numerical_features:
            feature_mapping[col] = col
        else:
            # It's an OHE column for lithology_class
            feature_mapping[col] = 'lithology_class'
            
    print("Training XGBoost Classifier...")
    # Using scale_pos_weight if imbalanced, but here we just train.
    # missing=np.nan is native to XGBoost.
    clf = xgb.XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        random_state=42,
        missing=np.nan,
        n_jobs=1,
        eval_metric='logloss'
    )
    
    clf.fit(X_train_transformed, y_train, eval_set=[(X_val_transformed, y_val)], verbose=False)
    
    print("Evaluating model...")
    y_pred_proba = clf.predict_proba(X_test_transformed)[:, 1]
    y_pred = clf.predict(X_test_transformed)
    
    metrics = {
        'roc_auc': float(roc_auc_score(y_test, y_pred_proba)),
        'pr_auc': float(average_precision_score(y_test, y_pred_proba)),
        'accuracy': float(accuracy_score(y_test, y_pred)),
        'precision': float(precision_score(y_test, y_pred, zero_division=0)),
        'recall': float(recall_score(y_test, y_pred)),
        'f1': float(f1_score(y_test, y_pred)),
        'confusion_matrix': confusion_matrix(y_test, y_pred).tolist()
    }
    
    for k, v in metrics.items():
        print(f"{k}: {v}")
        
    print("Initializing SHAP TreeExplainer...")
    explainer = shap.TreeExplainer(clf)
    
    # Save artifacts versioned
    model_dir = os.path.dirname(__file__)
    
    # First, save v2 artifacts safely
    with open(os.path.join(model_dir, 'landslide_model_v2.pkl'), 'wb') as f:
        pickle.dump(clf, f)
        
    with open(os.path.join(model_dir, 'preprocessor_v2.pkl'), 'wb') as f:
        pickle.dump(preprocessor, f)
        
    with open(os.path.join(model_dir, 'shap_explainer_v2.pkl'), 'wb') as f:
        pickle.dump(explainer, f)
        
    metadata = {
        'model_type': 'XGBoostClassifier',
        'model_version': 'v2.0',
        'feature_list': FEATURE_ORDER,
        'transformed_features': list(X_train_transformed.columns),
        'feature_mapping': feature_mapping,
        'test_metrics': metrics
    }
    
    with open(os.path.join(model_dir, 'model_metadata_v2.json'), 'w') as f:
        json.dump(metadata, f, indent=4)
        
    print("Updating active model pointer (landslide_model.pkl)...")
    import shutil
    # Keep backup of old model
    if os.path.exists(os.path.join(model_dir, 'landslide_model.pkl')):
        shutil.copy(os.path.join(model_dir, 'landslide_model.pkl'), os.path.join(model_dir, 'landslide_model_v1_backup.pkl'))
        
    shutil.copy(os.path.join(model_dir, 'landslide_model_v2.pkl'), os.path.join(model_dir, 'landslide_model.pkl'))
    shutil.copy(os.path.join(model_dir, 'preprocessor_v2.pkl'), os.path.join(model_dir, 'preprocessor.pkl'))
    shutil.copy(os.path.join(model_dir, 'shap_explainer_v2.pkl'), os.path.join(model_dir, 'shap_explainer.pkl'))
    shutil.copy(os.path.join(model_dir, 'model_metadata_v2.json'), os.path.join(model_dir, 'model_metadata.json'))

    print("Training complete and artifacts saved.")

if __name__ == '__main__':
    main()
