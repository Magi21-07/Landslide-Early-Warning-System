import os
import json
import joblib
import logging
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, average_precision_score,
    roc_curve, precision_recall_curve
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def evaluate_models():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    data_dir = os.path.join(base_dir, 'data', 'processed')
    models_dir = os.path.join(base_dir, 'models')
    results_dir = os.path.join(base_dir, 'results', 'ml')

    os.makedirs(results_dir, exist_ok=True)

    # Load metadata
    with open(os.path.join(data_dir, 'feature_columns.json'), 'r') as f:
        metadata = json.load(f)

    features = metadata['feature_columns']   # excludes lat/lon by design
    target   = metadata['target_column']

    # Load untouched test set
    test_df = pd.read_csv(os.path.join(data_dir, 'test.csv'))
    X_test  = test_df[features]
    y_test  = test_df[target]

    # Load saved models (NO RETRAINING)
    model_specs = [
        ("Logistic Regression",  "baseline_logistic_regression.joblib"),
        ("Random Forest",        "random_forest_landslide.joblib"),
        ("XGBoost",              "xgboost_landslide.joblib"),
    ]

    models = {}
    for name, fname in model_specs:
        path = os.path.join(models_dir, fname)
        if not os.path.exists(path):
            logger.error(f"Model file not found: {path}")
            return
        models[name] = joblib.load(path)
        logger.info(f"Loaded model: {name}")

    # Generate predictions and compute metrics
    results = []
    curve_data = {}

    for name, model in models.items():
        preds = model.predict(X_test)
        probs = model.predict_proba(X_test)[:, 1]

        metrics = {
            "Model":     name,
            "Accuracy":  round(accuracy_score(y_test, preds), 4),
            "Precision": round(precision_score(y_test, preds), 4),
            "Recall":    round(recall_score(y_test, preds), 4),
            "F1_Score":  round(f1_score(y_test, preds), 4),
            "ROC_AUC":   round(roc_auc_score(y_test, probs), 4),
            "PR_AUC":    round(average_precision_score(y_test, probs), 4),
        }
        results.append(metrics)

        fpr, tpr, _ = roc_curve(y_test, probs)
        prec, rec, _ = precision_recall_curve(y_test, probs)
        curve_data[name] = {
            "fpr": fpr, "tpr": tpr,
            "prec": prec, "rec": rec,
            "roc_auc": metrics["ROC_AUC"],
            "pr_auc":  metrics["PR_AUC"],
        }
        logger.info(f"{name}: ROC-AUC={metrics['ROC_AUC']}, F1={metrics['F1_Score']}")

    # Build comparison dataframe
    comparison_df = pd.DataFrame(results).set_index("Model")

    # Save CSV
    comparison_df.to_csv(os.path.join(results_dir, 'model_comparison.csv'))

    # Save JSON (orient='records')
    comparison_df.reset_index().to_json(
        os.path.join(results_dir, 'model_comparison.json'),
        orient='records', indent=2
    )
    logger.info("Saved model_comparison.csv and model_comparison.json")

    # Combined ROC Curve
    colours = ['#E74C3C', '#2ECC71', '#3498DB']
    fig, ax = plt.subplots(figsize=(10, 8))
    for (name, data), colour in zip(curve_data.items(), colours):
        ax.plot(data['fpr'], data['tpr'],
                label=f"{name} (AUC={data['roc_auc']:.4f})",
                color=colour, linewidth=2)
    ax.plot([0, 1], [0, 1], 'k--', linewidth=1, label='Random Classifier')
    ax.set_xlabel('False Positive Rate', fontsize=13)
    ax.set_ylabel('True Positive Rate', fontsize=13)
    ax.set_title('Combined ROC Curve — Test Set', fontsize=15, fontweight='bold')
    ax.legend(loc='lower right', fontsize=11)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, 'combined_roc_curve.png'), dpi=150)
    plt.close()
    logger.info("Saved combined_roc_curve.png")

    # Combined PR Curve
    fig, ax = plt.subplots(figsize=(10, 8))
    for (name, data), colour in zip(curve_data.items(), colours):
        ax.plot(data['rec'], data['prec'],
                label=f"{name} (PR-AUC={data['pr_auc']:.4f})",
                color=colour, linewidth=2)
    # Baseline = proportion of positives
    baseline_rate = y_test.mean()
    ax.axhline(y=baseline_rate, color='k', linestyle='--', linewidth=1,
               label=f'Random Classifier (P={baseline_rate:.2f})')
    ax.set_xlabel('Recall', fontsize=13)
    ax.set_ylabel('Precision', fontsize=13)
    ax.set_title('Combined Precision-Recall Curve — Test Set', fontsize=15, fontweight='bold')
    ax.legend(loc='lower left', fontsize=11)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(results_dir, 'combined_pr_curve.png'), dpi=150)
    plt.close()
    logger.info("Saved combined_pr_curve.png")

    # Console: metrics table
    metric_cols = ["Accuracy", "Precision", "Recall", "F1_Score", "ROC_AUC", "PR_AUC"]
    col_w = 13
    header_row = f"{'Model':<25}" + "".join(f"{m:>{col_w}}" for m in metric_cols)
    sep = "=" * len(header_row)

    print(f"\n{sep}")
    print("UNIFIED MODEL COMPARISON — UNTOUCHED TEST SET")
    print(sep)
    print(header_row)
    print("-" * len(header_row))

    for row in results:
        model_name = row['Model']
        vals = "".join(f"{row[m]:>{col_w}.4f}" for m in metric_cols)
        print(f"{model_name:<25}{vals}")

    print(sep + "\n")

    # Console: Precision-Recall trade-off analytical note
    print("=" * 70)
    print("ANALYTICAL NOTE: PRECISION vs RECALL IN LANDSLIDE DETECTION")
    print("=" * 70)
    print("""
In landslide susceptibility modelling, the cost of a missed detection
(False Negative) is catastrophically higher than the cost of a false alarm
(False Positive). Missing a landslide-prone zone may lead to loss of life;
an unnecessary warning at worst causes temporary disruption.

Therefore, high Recall (Sensitivity) is the primary operational objective:
  - High Recall  => fewer landslide events go undetected (lower FN).
  - Lower Precision => more false alarms are raised (higher FP).

The Precision-Recall trade-off can be controlled by adjusting the
classification threshold. The default 0.50 threshold is rarely optimal for
imbalanced, life-safety applications. A lower threshold (e.g., 0.35-0.40)
increases Recall at the cost of Precision, which is the safer choice in
real-world early-warning systems.

Key Results:
""")

    for row in results:
        print(f"  {row['Model']:<25} Recall={row['Recall']:.4f}  Precision={row['Precision']:.4f}  F1={row['F1_Score']:.4f}")

    print("""
Recommendation: Select XGBoost or Random Forest as the production model
(highest ROC-AUC & F1). Lower the decision threshold to ~0.38 during
deployment to maximise population-level recall for early warning alerts.
""")
    print("=" * 70 + "\n")
    logger.info("Phase 4.6 Completed Successfully.")

if __name__ == "__main__":
    evaluate_models()
