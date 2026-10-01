"""
predict_batch.py
----------------
CLI for batch landslide susceptibility inference.

Usage:
    python src/ml/predict_batch.py --input path/to/input.csv --output path/to/output.csv
"""

import argparse
import logging
import os
import sys

import pandas as pd

# Ensure project root is on path when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from src.ml.predict import LandslidePredictor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def run_batch(input_path: str, output_path: str) -> None:
    # Validate input file
    if not os.path.exists(input_path):
        logger.error("Input file not found: %s", input_path)
        sys.exit(1)

    logger.info("Loading input CSV: %s", input_path)
    df_input = pd.read_csv(input_path)

    if df_input.empty:
        logger.error("Input CSV is empty. Aborting.")
        sys.exit(1)

    # Initialize predictor
    predictor = LandslidePredictor()

    # Run inference
    logger.info("Running batch inference on %d rows...", len(df_input))
    results = predictor.predict(df_input)

    # Append results to original dataframe (preserving all original columns)
    df_output = df_input.copy()
    df_output['landslide_probability'] = [r['probability'] for r in results]
    df_output['susceptibility_class']  = [r['susceptibility'] for r in results]

    # Create output directory if needed
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)

    df_output.to_csv(output_path, index=False)
    logger.info("Batch inference complete. Output saved to: %s", output_path)
    logger.info(
        "Susceptibility class distribution:\n%s",
        df_output['susceptibility_class'].value_counts().to_string()
    )


def main():
    parser = argparse.ArgumentParser(
        description="Batch landslide susceptibility prediction CLI"
    )
    parser.add_argument(
        '--input',
        required=True,
        help='Path to input CSV file containing feature columns.'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Path where the output CSV with predictions will be saved.'
    )
    args = parser.parse_args()
    run_batch(args.input, args.output)


if __name__ == '__main__':
    main()
