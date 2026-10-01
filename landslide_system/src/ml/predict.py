import os
import json
import logging
import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _resolve_path(path: str) -> str:
    """Resolve path relative to the project root (two levels above this file)."""
    if os.path.isabs(path):
        return path
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    return os.path.join(root, path)


class LandslidePredictor:
    """Reusable prediction pipeline for landslide susceptibility."""

    DEFAULT_MODEL_PATH   = 'models/xgboost_landslide.joblib'
    DEFAULT_META_PATH    = 'data/processed/feature_columns.json'
    DEFAULT_CONFIG_PATH  = 'config/susceptibility_config.json'

    def __init__(
        self,
        model_path: str = None,
        feature_meta_path: str = None,
        config_path: str = None
    ):
        model_path        = _resolve_path(model_path or self.DEFAULT_MODEL_PATH)
        feature_meta_path = _resolve_path(feature_meta_path or self.DEFAULT_META_PATH)
        config_path       = _resolve_path(config_path or self.DEFAULT_CONFIG_PATH)

        logger.info("Loading model from: %s", model_path)
        self.model = joblib.load(model_path)

        with open(feature_meta_path, 'r') as f:
            meta = json.load(f)
        self.feature_columns: list = meta['feature_columns']
        logger.info("Feature columns loaded: %s", self.feature_columns)

        with open(config_path, 'r') as f:
            cfg = json.load(f)
        self.thresholds: list = cfg['thresholds']   # list of {max, label}
        logger.info("Susceptibility thresholds loaded: %d levels", len(self.thresholds))

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def predict(self, data):
        """
        Predict landslide probability and susceptibility class.

        Parameters
        ----------
        data : dict | pd.DataFrame
            A single sample as dict, or a DataFrame with one or more rows.

        Returns
        -------
        dict  (single dict input)  – {"probability": float, "susceptibility": str}
        list  (DataFrame input)    – list of dicts
        """
        single = isinstance(data, dict)
        df = self._validate_and_prepare(data)

        probs = self.model.predict_proba(df)[:, 1]

        results = [
            {
                "probability": round(float(p), 4),
                "susceptibility": self._map_susceptibility(round(float(p), 4))
            }
            for p in probs
        ]

        return results[0] if single else results

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _validate_and_prepare(self, data) -> pd.DataFrame:
        """Validate input, reject bad values, and reorder columns."""
        if isinstance(data, dict):
            df = pd.DataFrame([data])
        elif isinstance(data, pd.DataFrame):
            df = data.copy()
        else:
            raise TypeError("Input must be a dict or pandas DataFrame.")

        # Check required features are present
        missing = [c for c in self.feature_columns if c not in df.columns]
        if missing:
            raise ValueError(
                f"Missing required feature columns: {missing}. "
                f"Required: {self.feature_columns}"
            )

        # Extract only the training features (ignore extras gracefully)
        df = df[self.feature_columns]

        # Check for NaN / None
        if df.isnull().any().any():
            bad_cols = df.columns[df.isnull().any()].tolist()
            raise ValueError(
                f"Input contains NaN/None values in columns: {bad_cols}. "
                "All feature values must be non-null."
            )

        # Validate numeric types
        for col in self.feature_columns:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"Column '{col}' contains non-numeric values: {exc}"
                ) from exc

        return df

    def _map_susceptibility(self, probability: float) -> str:
        """Map a probability score to a susceptibility label."""
        for tier in self.thresholds:
            if probability <= tier['max']:
                return tier['label']
        return self.thresholds[-1]['label']   # fallback for exactly 1.0
