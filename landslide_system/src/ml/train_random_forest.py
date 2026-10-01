import os
import json
import joblib
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    roc_curve, precision_recall_curve
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def train_random_forest():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    data_dir = os.path.join(base_dir, 'data', 'processed')
    models_dir = os.path.join(base_dir, 'models')
    results_dir = os.path.join(base_dir, 'results', 'ml')
    
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    
    # Load feature mappings
    metadata_file = os.path.join(data_dir, 'feature_columns.json')
    with open(metadata_file, 'r') as f:
        metadata = json.load(f)
        
    features = metadata['feature_columns']
    target = metadata['target_column']
    
    # Load data
    train_df = pd.read_csv(os.path.join(data_dir, 'train.csv'))
    val_df = pd.read_csv(os.path.join(data_dir, 'val.csv'))
    test_df = pd.read_csv(os.path.join(data_dir, 'test.csv'))
    
    X_train, y_train = train_df[features], train_df[target]
    X_val, y_val = val_df[features], val_df[target]
    X_test, y_test = test_df[features], test_df[target]
    
    # Model Training
    logger.info("Initializing and training Random Forest Classifier...")
    rf_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_split=5,
        random_state=42,
        class_weight='balanced'
    )
    
    rf_model.fit(X_train, y_train)
    
    # Evaluation
    def evaluate_model(X, y, set_name="Validation"):
        preds = rf_model.predict(X)
        probs = rf_model.predict_proba(X)[:, 1]
        
        metrics = {
            "Accuracy": accuracy_score(y, preds),
            "Precision": precision_score(y, preds),
            "Recall": recall_score(y, preds),
            "F1_Score": f1_score(y, preds),
            "ROC_AUC": roc_auc_score(y, probs),
            "PR_AUC": average_precision_score(y, probs)
        }
        
        cm = confusion_matrix(y, preds)
        
        return metrics, probs, cm

    val_metrics, val_probs, val_cm = evaluate_model(X_val, y_val, "Validation")
    test_metrics, test_probs, test_cm = evaluate_model(X_test, y_test, "Test")
    
    # Feature Importance
    importances = rf_model.feature_importances_
    fi_df = pd.DataFrame({
        'Feature': features,
        'Importance': importances
    }).sort_values(by='Importance', ascending=False)
    fi_df.to_csv(os.path.join(results_dir, 'random_forest_feature_importance.csv'), index=False)
    
    # Artifact Export
    model_path = os.path.join(models_dir, 'random_forest_landslide.joblib')
    joblib.dump(rf_model, model_path)
    logger.info(f"Saved trained model to {model_path}")
    
    metrics_export = {
        "validation": val_metrics,
        "test": test_metrics
    }
    
    metrics_path = os.path.join(results_dir, 'random_forest_metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(metrics_export, f, indent=4)
        
    # Visualizations
    logger.info("Generating ROC, PR curves, Confusion Matrix, and Feature Importance plots...")
    
    # ROC Curve
    plt.figure(figsize=(10, 8))
    fpr_val, tpr_val, _ = roc_curve(y_val, val_probs)
    fpr_test, tpr_test, _ = roc_curve(y_test, test_probs)
    plt.plot(fpr_val, tpr_val, label=f'Validation (AUC = {val_metrics["ROC_AUC"]:.2f})')
    plt.plot(fpr_test, tpr_test, label=f'Test (AUC = {test_metrics["ROC_AUC"]:.2f})')
    plt.plot([0, 1], [0, 1], 'k--')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('ROC Curve - Random Forest')
    plt.legend(loc='lower right')
    plt.savefig(os.path.join(results_dir, 'rf_roc_curve.png'))
    plt.close()
    
    # PR Curve
    plt.figure(figsize=(10, 8))
    prec_val, rec_val, _ = precision_recall_curve(y_val, val_probs)
    prec_test, rec_test, _ = precision_recall_curve(y_test, test_probs)
    plt.plot(rec_val, prec_val, label=f'Validation (PR-AUC = {val_metrics["PR_AUC"]:.2f})')
    plt.plot(rec_test, prec_test, label=f'Test (PR-AUC = {test_metrics["PR_AUC"]:.2f})')
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('Precision-Recall Curve - Random Forest')
    plt.legend(loc='lower left')
    plt.savefig(os.path.join(results_dir, 'rf_pr_curve.png'))
    plt.close()
    
    # Confusion Matrix
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    sns.heatmap(val_cm, annot=True, fmt='d', cmap='Blues', ax=axes[0])
    axes[0].set_title('Validation Confusion Matrix')
    axes[0].set_xlabel('Predicted')
    axes[0].set_ylabel('Actual')
    
    sns.heatmap(test_cm, annot=True, fmt='d', cmap='Blues', ax=axes[1])
    axes[1].set_title('Test Confusion Matrix')
    axes[1].set_xlabel('Predicted')
    axes[1].set_ylabel('Actual')
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, 'rf_confusion_matrix.png'))
    plt.close()
    
    # Feature Importance Plot
    plt.figure(figsize=(8, 6))
    sns.barplot(x='Importance', y='Feature', data=fi_df, palette='viridis')
    plt.title('Feature Importance (Mean Decrease in Impurity)')
    plt.xlabel('Importance')
    plt.ylabel('Feature')
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, 'rf_feature_importance.png'))
    plt.close()
    
    # Load Baseline Metrics for comparison
    baseline_metrics_path = os.path.join(results_dir, 'baseline_metrics.json')
    baseline_metrics = None
    if os.path.exists(baseline_metrics_path):
        with open(baseline_metrics_path, 'r') as f:
            baseline_metrics = json.load(f)
            
    # Print metrics nicely
    print("\n" + "="*85)
    print("RANDOM FOREST MODEL EVALUATION & BASELINE COMPARISON")
    print("="*85)
    print(f"{'Metric':<15} | {'RF Validation':<15} | {'RF Test':<15} | {'LR Test (Baseline)':<20}")
    print("-" * 85)
    for key in val_metrics.keys():
        rf_val_val = f"{val_metrics[key]:.4f}"
        rf_test_val = f"{test_metrics[key]:.4f}"
        lr_test_val = f"{baseline_metrics['test'][key]:.4f}" if baseline_metrics else "N/A"
        print(f"{key:<15} | {rf_val_val:<15} | {rf_test_val:<15} | {lr_test_val:<20}")
    print("="*85 + "\n")
    
    # Inference Test
    logger.info("Running Inference Test on saved Random Forest model...")
    loaded_model = joblib.load(model_path)
    
    dummy_data = {feat: [np.random.uniform(0, 100)] for feat in features}
    dummy_df = pd.DataFrame(dummy_data)
    
    dummy_prob = loaded_model.predict_proba(dummy_df)[:, 1][0]
    
    assert 0.0 <= dummy_prob <= 1.0, f"Inference probability {dummy_prob} is out of bounds!"
    print(f"[INFERENCE TEST] Successfully generated probability: {dummy_prob:.4f} (Valid range: 0.0-1.0)")
    logger.info("Phase 4.4 Completed Successfully.")

if __name__ == "__main__":
    train_random_forest()
