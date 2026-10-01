import os
import json
import joblib
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score, confusion_matrix,
    roc_curve, precision_recall_curve
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def train_baseline():
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
    
    # Preprocessing Pipeline
    logger.info("Initializing and training baseline Logistic Regression pipeline...")
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('classifier', LogisticRegression(random_state=42, class_weight='balanced'))
    ])
    
    pipeline.fit(X_train, y_train)
    
    # Evaluation
    def evaluate_model(X, y, set_name="Validation"):
        preds = pipeline.predict(X)
        probs = pipeline.predict_proba(X)[:, 1]
        
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
    
    # Artifact Export
    model_path = os.path.join(models_dir, 'baseline_logistic_regression.joblib')
    joblib.dump(pipeline, model_path)
    logger.info(f"Saved trained pipeline to {model_path}")
    
    metrics_export = {
        "validation": val_metrics,
        "test": test_metrics
    }
    
    metrics_path = os.path.join(results_dir, 'baseline_metrics.json')
    with open(metrics_path, 'w') as f:
        json.dump(metrics_export, f, indent=4)
        
    # Visualizations
    logger.info("Generating ROC, PR curves, and Confusion Matrix plots...")
    plt.figure(figsize=(10, 8))
    fpr_val, tpr_val, _ = roc_curve(y_val, val_probs)
    fpr_test, tpr_test, _ = roc_curve(y_test, test_probs)
    plt.plot(fpr_val, tpr_val, label=f'Validation (AUC = {val_metrics["ROC_AUC"]:.2f})')
    plt.plot(fpr_test, tpr_test, label=f'Test (AUC = {test_metrics["ROC_AUC"]:.2f})')
    plt.plot([0, 1], [0, 1], 'k--')
    plt.xlabel('False Positive Rate')
    plt.ylabel('True Positive Rate')
    plt.title('ROC Curve - Baseline Model')
    plt.legend(loc='lower right')
    plt.savefig(os.path.join(results_dir, 'roc_curve.png'))
    plt.close()
    
    plt.figure(figsize=(10, 8))
    prec_val, rec_val, _ = precision_recall_curve(y_val, val_probs)
    prec_test, rec_test, _ = precision_recall_curve(y_test, test_probs)
    plt.plot(rec_val, prec_val, label=f'Validation (PR-AUC = {val_metrics["PR_AUC"]:.2f})')
    plt.plot(rec_test, prec_test, label=f'Test (PR-AUC = {test_metrics["PR_AUC"]:.2f})')
    plt.xlabel('Recall')
    plt.ylabel('Precision')
    plt.title('Precision-Recall Curve - Baseline Model')
    plt.legend(loc='lower left')
    plt.savefig(os.path.join(results_dir, 'pr_curve.png'))
    plt.close()
    
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
    plt.savefig(os.path.join(results_dir, 'confusion_matrix.png'))
    plt.close()
    
    # Print metrics nicely
    print("\n" + "="*60)
    print("BASELINE MODEL EVALUATION (LOGISTIC REGRESSION)")
    print("="*60)
    print(f"{'Metric':<20} | {'Validation':<15} | {'Test':<15}")
    print("-" * 60)
    for key in val_metrics.keys():
        print(f"{key:<20} | {val_metrics[key]:<15.4f} | {test_metrics[key]:<15.4f}")
    print("="*60 + "\n")
    
    # Inference Test
    logger.info("Running Inference Test on saved model...")
    loaded_model = joblib.load(model_path)
    
    # Create dummy data using exactly feature_columns
    dummy_data = {feat: [np.random.uniform(0, 100)] for feat in features}
    dummy_df = pd.DataFrame(dummy_data)
    
    dummy_prob = loaded_model.predict_proba(dummy_df)[:, 1][0]
    
    assert 0.0 <= dummy_prob <= 1.0, f"Inference probability {dummy_prob} is out of bounds!"
    print(f"[INFERENCE TEST] Successfully generated probability: {dummy_prob:.4f} (Valid range: 0.0-1.0)")
    logger.info("Phase 4.3 Completed Successfully.")

if __name__ == "__main__":
    train_baseline()
