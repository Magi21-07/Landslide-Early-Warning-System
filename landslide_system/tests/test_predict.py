"""
tests/test_predict.py
---------------------
Unit tests for src/ml/predict.py (LandslidePredictor).
"""

import os
import sys
import json
import tempfile
import pytest
import numpy as np
import pandas as pd

# Ensure project root on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.ml.predict import LandslidePredictor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def predictor():
    """Load the real predictor once per test module."""
    return LandslidePredictor()


@pytest.fixture
def valid_dict():
    return {
        "slope": 25.0,
        "root_cohesion": 0.5,
        "elevation": 1200.0,
        "soil_moisture": 40.0
    }


@pytest.fixture
def valid_df(valid_dict):
    return pd.DataFrame([valid_dict])


# ---------------------------------------------------------------------------
# 1. Initialization & model loading
# ---------------------------------------------------------------------------

class TestInitialization:

    def test_predictor_loads_without_error(self, predictor):
        assert predictor.model is not None

    def test_feature_columns_loaded(self, predictor):
        assert isinstance(predictor.feature_columns, list)
        assert len(predictor.feature_columns) > 0

    def test_thresholds_loaded(self, predictor):
        assert isinstance(predictor.thresholds, list)
        assert len(predictor.thresholds) == 5

    def test_thresholds_cover_full_range(self, predictor):
        assert predictor.thresholds[-1]['max'] == 1.00

    def test_invalid_model_path_raises(self):
        with pytest.raises(Exception):
            LandslidePredictor(model_path='nonexistent/model.joblib')

    def test_invalid_meta_path_raises(self):
        with pytest.raises(Exception):
            LandslidePredictor(feature_meta_path='nonexistent/meta.json')


# ---------------------------------------------------------------------------
# 2. Input validation — valid inputs
# ---------------------------------------------------------------------------

class TestValidInputs:

    def test_single_dict_returns_dict(self, predictor, valid_dict):
        result = predictor.predict(valid_dict)
        assert isinstance(result, dict)

    def test_dataframe_returns_list(self, predictor, valid_df):
        result = predictor.predict(valid_df)
        assert isinstance(result, list)
        assert len(result) == len(valid_df)

    def test_result_has_probability_key(self, predictor, valid_dict):
        result = predictor.predict(valid_dict)
        assert 'probability' in result

    def test_result_has_susceptibility_key(self, predictor, valid_dict):
        result = predictor.predict(valid_dict)
        assert 'susceptibility' in result

    def test_extra_columns_ignored_gracefully(self, predictor, valid_dict):
        """Extra keys that aren't features should be silently ignored."""
        data = {**valid_dict, "latitude": 28.0, "longitude": 85.0, "id": 999}
        result = predictor.predict(data)
        assert 'probability' in result


# ---------------------------------------------------------------------------
# 3. Input validation — invalid inputs that must raise ValueError
# ---------------------------------------------------------------------------

class TestInvalidInputs:

    def test_missing_feature_raises_valueerror(self, predictor, valid_dict):
        bad = {k: v for k, v in valid_dict.items() if k != 'slope'}
        with pytest.raises(ValueError, match="Missing required feature"):
            predictor.predict(bad)

    def test_nan_value_raises_valueerror(self, predictor, valid_dict):
        bad = {**valid_dict, "slope": float('nan')}
        with pytest.raises(ValueError, match="NaN"):
            predictor.predict(bad)

    def test_none_value_raises_valueerror(self, predictor, valid_dict):
        bad = {**valid_dict, "elevation": None}
        with pytest.raises(ValueError, match="NaN"):
            predictor.predict(bad)

    def test_non_numeric_raises_valueerror(self, predictor, valid_dict):
        bad = {**valid_dict, "slope": "steep"}
        with pytest.raises(ValueError):
            predictor.predict(bad)

    def test_wrong_type_raises_typeerror(self, predictor):
        with pytest.raises(TypeError):
            predictor.predict("this is a string")


# ---------------------------------------------------------------------------
# 4. Probability range checks
# ---------------------------------------------------------------------------

class TestProbabilityRange:

    def test_probability_between_0_and_1(self, predictor, valid_dict):
        result = predictor.predict(valid_dict)
        assert 0.0 <= result['probability'] <= 1.0

    def test_batch_probabilities_all_in_range(self, predictor):
        rows = [
            {"slope": s, "root_cohesion": r, "elevation": e, "soil_moisture": m}
            for s, r, e, m in [
                (5.0,   0.1, 100.0,  10.0),
                (45.0,  0.8, 3000.0, 80.0),
                (20.0,  0.3, 800.0,  30.0),
                (60.0,  0.9, 4000.0, 95.0),
                (1.0,   0.05, 50.0,   5.0),
            ]
        ]
        results = predictor.predict(pd.DataFrame(rows))
        for r in results:
            assert 0.0 <= r['probability'] <= 1.0

    def test_probability_rounded_to_4_decimal_places(self, predictor, valid_dict):
        result = predictor.predict(valid_dict)
        p = result['probability']
        assert round(p, 4) == p


# ---------------------------------------------------------------------------
# 5. Threshold boundary mapping — all 5 risk levels
# ---------------------------------------------------------------------------

class TestThresholdMapping:

    def _mock_prob(self, predictor, probability: float) -> str:
        return predictor._map_susceptibility(probability)

    def test_very_low(self, predictor):
        assert self._mock_prob(predictor, 0.10) == "Very Low"

    def test_low(self, predictor):
        assert self._mock_prob(predictor, 0.30) == "Low"

    def test_moderate(self, predictor):
        assert self._mock_prob(predictor, 0.50) == "Moderate"

    def test_high(self, predictor):
        assert self._mock_prob(predictor, 0.70) == "High"

    def test_very_high(self, predictor):
        assert self._mock_prob(predictor, 0.90) == "Very High"

    def test_exact_boundary_at_0_20(self, predictor):
        assert self._mock_prob(predictor, 0.20) == "Very Low"

    def test_exact_boundary_at_0_40(self, predictor):
        assert self._mock_prob(predictor, 0.40) == "Low"

    def test_exact_boundary_at_1_00(self, predictor):
        assert self._mock_prob(predictor, 1.00) == "Very High"


# ---------------------------------------------------------------------------
# 6. Batch inference
# ---------------------------------------------------------------------------

class TestBatchInference:

    def test_batch_on_dataframe(self, predictor):
        df = pd.DataFrame([
            {"slope": 10.0, "root_cohesion": 0.2, "elevation": 500.0,  "soil_moisture": 20.0},
            {"slope": 35.0, "root_cohesion": 0.6, "elevation": 2000.0, "soil_moisture": 55.0},
            {"slope": 55.0, "root_cohesion": 0.9, "elevation": 3500.0, "soil_moisture": 85.0},
        ])
        results = predictor.predict(df)
        assert len(results) == 3
        for r in results:
            assert 'probability' in r
            assert 'susceptibility' in r
            assert r['susceptibility'] in {
                "Very Low", "Low", "Moderate", "High", "Very High"
            }

    def test_batch_via_csv_roundtrip(self, predictor):
        """Write a temp CSV, run inference, confirm output CSV has extra columns."""
        from src.ml.predict_batch import run_batch

        rows = [
            {"latitude": 27.0, "longitude": 85.0, "slope": 30.0,
             "root_cohesion": 0.5, "elevation": 1500.0, "soil_moisture": 45.0},
            {"latitude": 28.0, "longitude": 86.0, "slope": 10.0,
             "root_cohesion": 0.1, "elevation": 200.0,  "soil_moisture": 10.0},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            in_path  = os.path.join(tmpdir, "input.csv")
            out_path = os.path.join(tmpdir, "output.csv")

            pd.DataFrame(rows).to_csv(in_path, index=False)
            run_batch(in_path, out_path)

            df_out = pd.read_csv(out_path)
            assert 'landslide_probability' in df_out.columns
            assert 'susceptibility_class' in df_out.columns
            # Original columns preserved
            assert 'latitude' in df_out.columns
            assert 'longitude' in df_out.columns
            assert len(df_out) == 2
