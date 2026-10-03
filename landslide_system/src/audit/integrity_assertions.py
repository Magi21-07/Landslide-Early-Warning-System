"""
src/audit/integrity_assertions.py
----------------------------------
Phase Q: Hard Data Integrity Assertions

Validates 14-factor feature vectors, model outputs, and SHAP results
against the locked semantic contract. These assertions run at inference
time and in automated tests.

IMPORTANT: These are engineering assertions. Passing does NOT imply
scientific geotechnical validation.
"""
from __future__ import annotations

import logging
import math
from typing import Any, Dict, List, Optional

import numpy as np

from src.models.feature_contract import FEATURE_ORDER

logger = logging.getLogger(__name__)

# Risk level boundaries (must match risk.py exactly)
RISK_THRESHOLDS = {
    "LOW": (0.0, 0.30),
    "MODERATE": (0.30, 0.55),
    "HIGH": (0.55, 0.75),
    "CRITICAL": (0.75, 1.0),
}

NDVI_BOUNDS = (-1.0, 1.0)
PROB_BOUNDS = (0.0, 1.0)
DISTANCE_MIN = 0.0
WEATHERING_BOUNDS = (0.0, 1.0)


class AssertionError_(Exception):
    """Custom assertion error for integrity failures."""
    pass


def assert_14_semantic_features(features: Dict[str, Any], context: str = "inference") -> None:
    """
    Assert exactly 14 semantic features exist and match the locked contract.
    """
    if len(features) != 14:
        raise AssertionError_(
            f"[{context}] Semantic feature count is {len(features)}, expected exactly 14. "
            f"Present: {list(features.keys())}"
        )
    missing = [f for f in FEATURE_ORDER if f not in features]
    if missing:
        raise AssertionError_(
            f"[{context}] Missing features from contract: {missing}"
        )
    extra = [f for f in features if f not in FEATURE_ORDER]
    if extra:
        raise AssertionError_(
            f"[{context}] Extra features not in contract: {extra}"
        )


def assert_rainfall_monotonicity(features: Dict[str, Any], context: str = "inference") -> None:
    """
    Assert rainfall_3day_mm <= rainfall_15day_mm when both are not NaN.
    """
    r3 = features.get("rainfall_3day_mm")
    r15 = features.get("rainfall_15day_mm")

    if r3 is None or r15 is None:
        return

    # Skip NaN checks
    if isinstance(r3, float) and math.isnan(r3):
        return
    if isinstance(r15, float) and math.isnan(r15):
        return

    if r3 > r15:
        raise AssertionError_(
            f"[{context}] Monotonicity violated: rainfall_3day_mm ({r3}) > rainfall_15day_mm ({r15}). "
            "3-day sum cannot exceed 15-day cumulative."
        )


def assert_ndvi_bounds(features: Dict[str, Any], context: str = "inference") -> None:
    """Assert NDVI is within [-1.0, 1.0] when not NaN."""
    ndvi = features.get("ndvi_index")
    if ndvi is None or (isinstance(ndvi, float) and math.isnan(ndvi)):
        return
    if not (NDVI_BOUNDS[0] <= ndvi <= NDVI_BOUNDS[1]):
        raise AssertionError_(
            f"[{context}] NDVI value {ndvi} out of valid bounds {NDVI_BOUNDS}."
        )


def assert_distances_non_negative(features: Dict[str, Any], context: str = "inference") -> None:
    """Assert distances are >= 0 when not NaN."""
    for key in ("distance_to_river_m", "distance_to_road_m"):
        val = features.get(key)
        if val is None or (isinstance(val, float) and math.isnan(val)):
            continue
        if val < DISTANCE_MIN:
            raise AssertionError_(
                f"[{context}] {key} is negative: {val}. Distances must be >= 0."
            )


def assert_weathering_bounds(features: Dict[str, Any], context: str = "inference") -> None:
    """Assert weathering_index is within [0, 1] when present."""
    w = features.get("weathering_index")
    if w is None or (isinstance(w, float) and math.isnan(w)):
        return
    if not (WEATHERING_BOUNDS[0] <= w <= WEATHERING_BOUNDS[1]):
        raise AssertionError_(
            f"[{context}] weathering_index {w} out of bounds {WEATHERING_BOUNDS}."
        )


def assert_probability_bounds(probability: float, context: str = "inference") -> None:
    """Assert model output probability is within [0.0, 1.0]."""
    if not (PROB_BOUNDS[0] <= probability <= PROB_BOUNDS[1]):
        raise AssertionError_(
            f"[{context}] Probability {probability} out of bounds [0, 1]."
        )


def assert_risk_level_matches_probability(risk_level: str, probability: float, context: str = "inference") -> None:
    """Assert risk_level matches the configured probability thresholds."""
    expected = None
    if probability < 0.30:
        expected = "LOW"
    elif probability < 0.55:
        expected = "MODERATE"
    elif probability < 0.75:
        expected = "HIGH"
    else:
        expected = "CRITICAL"

    if risk_level != expected:
        raise AssertionError_(
            f"[{context}] risk_level '{risk_level}' does not match probability {probability:.3f}. "
            f"Expected '{expected}' per locked thresholds."
        )


def assert_shap_factors_in_contract(top_risk_factors: List[Dict], context: str = "inference") -> None:
    """Assert top_risk_factors only reference the 14 semantic factor labels."""
    VALID_LABELS = {
        "Terrain Slope", "Elevation", "Rainfall (3-Day)", "Rainfall (15-Day)",
        "Distance to River", "Distance to Road", "Soil Clay Content",
        "Soil Hydraulic Property", "Lithology", "Vegetation Index (NDVI)",
        "Tree Cover Density", "SAR Soil-Moisture Proxy", "Weathering",
        "Settlement / Land-Use Exposure"
    }
    for entry in top_risk_factors:
        factor = entry.get("factor", "")
        if factor not in VALID_LABELS:
            raise AssertionError_(
                f"[{context}] SHAP factor '{factor}' not in 14-factor semantic label set."
            )


def assert_shap_sorted_by_contribution(top_risk_factors: List[Dict], context: str = "inference") -> None:
    """Assert top_risk_factors are sorted descending by absolute contribution."""
    def parse_pct(s: str) -> float:
        try:
            return abs(float(s.strip("%").strip("+").strip("-")))
        except Exception:
            return 0.0

    pcts = [parse_pct(f.get("contribution", "0%")) for f in top_risk_factors]
    for i in range(len(pcts) - 1):
        if pcts[i] < pcts[i + 1]:
            raise AssertionError_(
                f"[{context}] top_risk_factors not sorted descending by contribution. "
                f"Index {i}={pcts[i]}% < index {i+1}={pcts[i+1]}%"
            )


def assert_coordinate_consistency(
    request_lat: float, request_lon: float,
    response_lat: float, response_lon: float,
    context: str = "inference"
) -> None:
    """Assert input coordinate matches response coordinate."""
    if abs(request_lat - response_lat) > 1e-6 or abs(request_lon - response_lon) > 1e-6:
        raise AssertionError_(
            f"[{context}] Coordinate mismatch: request ({request_lat}, {request_lon}) != "
            f"response ({response_lat}, {response_lon})."
        )


def run_all_feature_assertions(
    features: Dict[str, Any],
    context: str = "inference"
) -> List[str]:
    """
    Run all feature-level assertions. Returns list of failure messages.
    Does not raise — collects all failures for reporting.
    """
    failures = []
    assertions = [
        lambda: assert_14_semantic_features(features, context),
        lambda: assert_rainfall_monotonicity(features, context),
        lambda: assert_ndvi_bounds(features, context),
        lambda: assert_distances_non_negative(features, context),
        lambda: assert_weathering_bounds(features, context),
    ]
    for assertion in assertions:
        try:
            assertion()
        except AssertionError_ as e:
            failures.append(str(e))
            logger.warning("Integrity assertion failed: %s", str(e))

    return failures


def run_all_response_assertions(
    probability: float,
    risk_level: str,
    top_risk_factors: List[Dict],
    request_lat: float,
    request_lon: float,
    response_lat: float,
    response_lon: float,
    context: str = "inference"
) -> List[str]:
    """
    Run all response-level assertions. Returns list of failure messages.
    """
    failures = []
    assertions = [
        lambda: assert_probability_bounds(probability, context),
        lambda: assert_risk_level_matches_probability(risk_level, probability, context),
        lambda: assert_shap_factors_in_contract(top_risk_factors, context),
        lambda: assert_shap_sorted_by_contribution(top_risk_factors, context),
        lambda: assert_coordinate_consistency(request_lat, request_lon, response_lat, response_lon, context),
    ]
    for assertion in assertions:
        try:
            assertion()
        except AssertionError_ as e:
            failures.append(str(e))
            logger.warning("Integrity assertion failed: %s", str(e))

    return failures
