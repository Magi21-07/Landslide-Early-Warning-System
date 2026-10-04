"""
tests/etl/test_spatial_service.py
-----------------------------------
FC-3 Comprehensive test suite for:
  - src/etl/spatial_models.py
  - src/etl/spatial_service.py
  - API contract regression (spatial_metrics key, model input shape)

Test categories:
  A. Coordinate validation
  B. Soil properties (SoilGrids v2)
  C. Lithology & Weathering
  D. Proximity metrics (Overpass)
  E. Coordinate consistency / cache isolation
  F. API contract checks
  G. MODEL SHAPE SAFETY — X.shape[1] == 4 (CRITICAL)
"""

from __future__ import annotations

import json
import math
import time
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module under test
# ---------------------------------------------------------------------------

from src.etl.spatial_models import (
    FactorProvenance,
    SourceStatus,
    StaticSpatialMetrics,
)
from src.etl import spatial_service
from src.etl.spatial_service import (
    _haversine_m,
    _min_distance_to_way_m,
    _point_to_segment_distance_m,
    _validate_coordinates,
    get_lithology_and_weathering,
    get_proximity_metrics,
    get_soil_properties,
    get_static_spatial_metrics,
)


# ===========================================================================
# A. Coordinate Validation
# ===========================================================================

class TestCoordinateValidation:
    def test_valid_coordinates_no_exception(self):
        _validate_coordinates(27.9881, 86.9250)
        _validate_coordinates(0.0, 0.0)
        _validate_coordinates(-89.9, 179.9)

    def test_latitude_too_high(self):
        with pytest.raises(ValueError, match="latitude"):
            _validate_coordinates(91.0, 0.0)

    def test_latitude_too_low(self):
        with pytest.raises(ValueError, match="latitude"):
            _validate_coordinates(-91.0, 0.0)

    def test_longitude_too_high(self):
        with pytest.raises(ValueError, match="longitude"):
            _validate_coordinates(0.0, 181.0)

    def test_longitude_too_low(self):
        with pytest.raises(ValueError, match="longitude"):
            _validate_coordinates(0.0, -181.0)

    def test_boundary_values_valid(self):
        _validate_coordinates(-90.0, -180.0)
        _validate_coordinates(90.0, 180.0)


# ===========================================================================
# B. Soil Properties
# ===========================================================================

def _make_soilgrids_response(clay_decig: float, wv0033_cm3: float, bdricm: float) -> dict:
    """Build a minimal SoilGrids v2 JSON response fixture."""
    def layer(name, value, depth="0-5cm"):
        return {
            "name": name,
            "depths": [{"label": depth, "values": {"mean": value}}],
        }
    return {
        "properties": {
            "layers": [
                layer("clay",    clay_decig),
                layer("wv0033",  wv0033_cm3),
                layer("bdricm",  bdricm),
            ]
        }
    }


class TestSoilProperties:
    def test_valid_soilgrids_response_unit_conversion(self):
        """clay decig/kg ÷ 10 → %, wv0033 cm³/dm³ ÷ 10 → %vol."""
        mock_json = _make_soilgrids_response(clay_decig=250.0, wv0033_cm3=300.0, bdricm=120.0)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_json

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.return_value = mock_resp

            result, prov = get_soil_properties(27.9881, 86.9250)

        assert result["clay_percent"]       == pytest.approx(25.0, abs=0.05)
        assert result["hydraulic_capacity"] == pytest.approx(30.0, abs=0.05)
        assert result["soil_depth"]         == pytest.approx(120.0, abs=0.1)
        assert prov.status == SourceStatus.REAL
        assert prov.fallback_used is False

    def test_unit_conversion_accuracy(self):
        """Verify decig/kg → % is exactly ÷10."""
        mock_json = _make_soilgrids_response(clay_decig=173.0, wv0033_cm3=185.0, bdricm=50.0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_json

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.return_value = mock_resp
            result, prov = get_soil_properties(11.6854, 76.1320)

        assert result["clay_percent"]       == pytest.approx(17.3, abs=0.01)
        assert result["hydraulic_capacity"] == pytest.approx(18.5, abs=0.01)

    def test_api_timeout_returns_fallback(self):
        import httpx
        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.side_effect = httpx.TimeoutException("timed out")

            result, prov = get_soil_properties(26.9124, 75.7873)

        assert result["clay_percent"]       == spatial_service._SOIL_FALLBACK["clay_percent"]
        assert result["hydraulic_capacity"] == spatial_service._SOIL_FALLBACK["hydraulic_capacity"]
        assert prov.status      == SourceStatus.FALLBACK
        assert prov.fallback_used is True

    def test_http_500_returns_fallback(self):
        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.side_effect = httpx.HTTPStatusError(
                "server error", request=MagicMock(), response=mock_resp
            )
            result, prov = get_soil_properties(27.9881, 86.9250)

        assert prov.status == SourceStatus.FALLBACK

    def test_malformed_json_returns_fallback(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.side_effect = json.JSONDecodeError("bad json", "", 0)

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.return_value = mock_resp
            result, prov = get_soil_properties(11.6854, 76.1320)

        assert prov.status == SourceStatus.FALLBACK

    def test_missing_property_returns_partial(self):
        """If one property is missing, the function still succeeds with partial REAL data."""
        # Only clay present
        mock_json = {"properties": {"layers": [
            {"name": "clay", "depths": [{"label": "0-5cm", "values": {"mean": 200.0}}]},
        ]}}
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_json

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.return_value = mock_resp
            result, prov = get_soil_properties(26.9124, 75.7873)

        assert result["clay_percent"] == pytest.approx(20.0, abs=0.01)
        # wv0033 missing → falls back to FALLBACK value for hyd_cap
        assert result["hydraulic_capacity"] == spatial_service._SOIL_FALLBACK["hydraulic_capacity"]

    def test_clay_out_of_range_discarded(self):
        """clay_percent > 100 must be discarded and replaced by fallback."""
        mock_json = _make_soilgrids_response(clay_decig=1100.0, wv0033_cm3=200.0, bdricm=80.0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_json

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.return_value = mock_resp
            result, _ = get_soil_properties(26.9124, 75.7873)

        # 1100 ÷ 10 = 110 % → invalid → fallback value used
        assert result["clay_percent"] == spatial_service._SOIL_FALLBACK["clay_percent"]

    def test_coordinate_validation_respected(self):
        with pytest.raises(ValueError):
            get_soil_properties(95.0, 0.0)


# ===========================================================================
# C. Lithology & Weathering
# ===========================================================================

class TestLithologyAndWeathering:
    def test_returns_fallback_with_provenance(self):
        """No GLiM raster → always FALLBACK, clearly marked."""
        result, prov = get_lithology_and_weathering(27.9881, 86.9250)

        assert prov.status      == SourceStatus.FALLBACK
        assert prov.fallback_used is True
        assert result["lithology_class"] == "Sedimentary"   # configured fallback
        assert result["weathering_index"] is None           # UNAVAILABLE

    def test_weathering_index_is_unavailable(self):
        result, _ = get_lithology_and_weathering(11.6854, 76.1320)
        assert result["weathering_index"] is None

    def test_no_coordinate_range_heuristic(self):
        """
        CRITICAL: Two geographically distinct coordinates must NOT differ because
        of hardcoded if-lat-range logic. Since no real raster exists, both return
        the same FALLBACK class — proving that no coordinate heuristic is applied.
        """
        r1, _ = get_lithology_and_weathering(27.9881, 86.9250)   # Everest (mountain)
        r2, _ = get_lithology_and_weathering(26.9124, 75.7873)   # Jaipur (plain)

        # Both must return the same FALLBACK — not differentiated by lat/lon
        assert r1["lithology_class"] == r2["lithology_class"], (
            "Lithology MUST NOT differ by lat/lon heuristics when no real raster exists"
        )

    def test_weathering_range_when_present(self):
        """If weathering_index is ever set (future), must be in [0.0, 1.0]."""
        result, _ = get_lithology_and_weathering(27.9881, 86.9250)
        wi = result.get("weathering_index")
        if wi is not None:
            assert 0.0 <= wi <= 1.0, f"weathering_index {wi} outside [0,1]"

    def test_coordinate_validation_respected(self):
        with pytest.raises(ValueError):
            get_lithology_and_weathering(0.0, 200.0)


# ===========================================================================
# D. Proximity Metrics
# ===========================================================================

def _make_overpass_response(river_nodes=None, road_nodes=None) -> dict:
    """Build a minimal Overpass JSON response fixture."""
    elements = []
    if river_nodes:
        elements.append({
            "type": "way",
            "tags": {"waterway": "river"},
            "geometry": river_nodes,
        })
    if road_nodes:
        elements.append({
            "type": "way",
            "tags": {"highway": "primary"},
            "geometry": road_nodes,
        })
    return {"elements": elements}


class TestProximityMetrics:
    def test_valid_overpass_response_distance_computed(self):
        """
        Target at (10.0, 80.0). River segment runs from (10.001, 79.9) to (10.001, 80.1).
        Expected perpendicular distance ≈ 111m (0.001° latitude offset).
        """
        target_lat, target_lon = 10.0, 80.0
        river_nodes = [
            {"lat": 10.001, "lon": 79.9},
            {"lat": 10.001, "lon": 80.1},
        ]
        road_nodes = [
            {"lat": 9.998, "lon": 79.95},
            {"lat": 9.998, "lon": 80.05},
        ]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_overpass_response(river_nodes, road_nodes)

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.post.return_value = mock_resp
            result, prov = get_proximity_metrics(target_lat, target_lon)

        assert prov.status == SourceStatus.REAL
        # River ~0.001° lat above target ≈ 111 m
        assert result["distance_to_river_m"] == pytest.approx(111.0, abs=20.0)
        # Road ~0.002° lat below target ≈ 222 m
        assert result["distance_to_road_m"]  == pytest.approx(222.0, abs=30.0)

    def test_distances_are_non_negative(self):
        """distance_to_river_m and distance_to_road_m must never be negative."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = _make_overpass_response(
            river_nodes=[{"lat": 10.001, "lon": 80.0}, {"lat": 10.002, "lon": 80.0}],
            road_nodes=[{"lat": 9.999, "lon": 80.0}, {"lat": 9.998, "lon": 80.0}],
        )
        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.post.return_value = mock_resp
            result, _ = get_proximity_metrics(10.0, 80.0)

        assert result["distance_to_river_m"] >= 0.0
        assert result["distance_to_road_m"]  >= 0.0

    def test_no_feature_found_distinguished_from_api_failure(self):
        """Empty Overpass response → NO_FEATURE_FOUND, NOT API_FAILURE — status=REAL."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"elements": []}

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.post.return_value = mock_resp
            result, prov = get_proximity_metrics(27.9881, 86.9250)

        # Should NOT fall back to FALLBACK status — source responded
        assert prov.status == SourceStatus.REAL
        # Should report the bbox-threshold estimate
        assert result["distance_to_river_m"] > 0.0

    def test_api_timeout_returns_fallback(self):
        import httpx
        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.post.side_effect = httpx.TimeoutException("timeout")
            result, prov = get_proximity_metrics(27.9881, 86.9250)

        assert prov.status      == SourceStatus.FALLBACK
        assert prov.fallback_used is True
        assert result["distance_to_river_m"] == spatial_service._PROXIMITY_FALLBACK["distance_to_river_m"]
        assert result["distance_to_road_m"]  == spatial_service._PROXIMITY_FALLBACK["distance_to_road_m"]

    def test_rivers_and_roads_separated(self):
        """Waterway tags → river bucket; highway tags → road bucket."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "elements": [
                {"type": "way", "tags": {"waterway": "stream"},
                 "geometry": [{"lat": 10.001, "lon": 80.0}, {"lat": 10.002, "lon": 80.0}]},
                {"type": "way", "tags": {"highway": "secondary"},
                 "geometry": [{"lat": 10.005, "lon": 80.0}, {"lat": 10.006, "lon": 80.0}]},
            ]
        }
        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.post.return_value = mock_resp
            result, _ = get_proximity_metrics(10.0, 80.0)

        # River is 0.001° away (~111m), road is 0.005° away (~555m)
        assert result["distance_to_river_m"] < result["distance_to_road_m"]

    def test_coordinate_validation_respected(self):
        with pytest.raises(ValueError):
            get_proximity_metrics(91.0, 0.0)


# ===========================================================================
# Haversine & Geometry Helpers
# ===========================================================================

class TestGeometryHelpers:
    def test_haversine_known_distance(self):
        """London to Paris ≈ 342 km."""
        d = _haversine_m(51.5, -0.13, 48.85, 2.35)
        assert d == pytest.approx(342_000, rel=0.05)

    def test_haversine_self_zero(self):
        assert _haversine_m(10.0, 80.0, 10.0, 80.0) == pytest.approx(0.0, abs=0.01)

    def test_point_to_segment_perpendicular(self):
        """Point directly above midpoint of horizontal segment."""
        # Segment from (0,0) to (0, 0.01) in lat/lon
        d = _point_to_segment_distance_m(0.001, 0.005, 0.0, 0.0, 0.0, 0.01)
        # 0.001° lat offset ≈ 111m
        assert d == pytest.approx(111.12, abs=5.0)

    def test_point_to_segment_endpoint_clamp(self):
        """
        Point at (0.0, 0.02) lies beyond segment end at (0.0, 0.01).
        The clamp projects to the endpoint (0.0, 0.01), so the distance
        equals the remaining lon gap: 0.02 - 0.01 = 0.01° ≈ 1111 m.
        """
        d = _point_to_segment_distance_m(0.0, 0.02, 0.0, 0.0, 0.0, 0.01)
        assert d == pytest.approx(0.01 * 111_120, rel=0.02)

    def test_min_distance_to_way(self):
        nodes = [
            {"lat": 10.001, "lon": 80.0},
            {"lat": 10.001, "lon": 80.01},
            {"lat": 10.002, "lon": 80.01},
        ]
        d = _min_distance_to_way_m(10.0, 80.005, nodes)
        assert d > 0.0
        assert d == pytest.approx(111.12, abs=20.0)  # ~0.001° lat offset


# ===========================================================================
# E. Coordinate Consistency (Cache Isolation)
# ===========================================================================

class TestCoordinateConsistency:
    """
    Two distinct coordinates must produce independent results.
    Cache keys must not cross-contaminate.
    """

    def _mock_soil_response(self, clay: float):
        mock_json = _make_soilgrids_response(clay, 200.0, 80.0)
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = mock_json
        return mock_resp

    def test_two_coordinates_independent_soil(self):
        """Different lat/lon → different SoilGrids calls, independent results."""
        call_count = {"n": 0}
        clay_values = [300.0, 150.0]   # Everest=30%, Jaipur=15%

        def side_effect(*args, **kwargs):
            resp = self._mock_soil_response(clay_values[call_count["n"]])
            call_count["n"] += 1
            return resp

        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.side_effect = side_effect

            r1, _ = get_soil_properties(27.9881, 86.9250)
            r2, _ = get_soil_properties(11.6854, 76.1320)

        assert r1["clay_percent"] != r2["clay_percent"]
        assert r1["clay_percent"] == pytest.approx(30.0, abs=0.01)
        assert r2["clay_percent"] == pytest.approx(15.0, abs=0.01)


# ===========================================================================
# F. API Contract Checks
# ===========================================================================

class TestApiContract:
    def test_get_static_spatial_metrics_returns_required_keys(self):
        """spatial_metrics dict must include all 7 factor keys + data_quality + _provenance."""
        with patch("src.etl.spatial_service.get_soil_properties") as mock_soil, \
             patch("src.etl.spatial_service.get_lithology_and_weathering") as mock_litho, \
             patch("src.etl.spatial_service.get_proximity_metrics") as mock_prox:

            prov_real = FactorProvenance("TEST", SourceStatus.FALLBACK, True, "NONE")
            mock_soil.return_value  = ({"clay_percent": 20.0, "hydraulic_capacity": 15.0, "soil_depth": 100.0}, prov_real)
            mock_litho.return_value = ({"lithology_class": "Sedimentary", "weathering_index": None}, prov_real)
            mock_prox.return_value  = ({"distance_to_river_m": 500.0, "distance_to_road_m": 300.0}, prov_real)

            result = get_static_spatial_metrics(27.9881, 86.9250)

        required_keys = [
            "clay_percent", "hydraulic_capacity", "soil_depth",
            "lithology_class", "weathering_index",
            "distance_to_river_m", "distance_to_road_m",
            "data_quality", "retrieved_at", "_provenance",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_all_external_failures_return_200_no_exception(self):
        """Total API failure → degraded result, NO exception raised."""
        import httpx
        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.side_effect  = httpx.TimeoutException("timeout")
            ctx.post.side_effect = httpx.TimeoutException("timeout")

            # Must not raise
            result = get_static_spatial_metrics(27.9881, 86.9250)

        assert isinstance(result, dict)
        assert result["clay_percent"]        == spatial_service._SOIL_FALLBACK["clay_percent"]
        assert result["distance_to_river_m"] == spatial_service._PROXIMITY_FALLBACK["distance_to_river_m"]

    def test_fallback_not_labelled_real(self):
        """After all failures, provenance must NOT say REAL."""
        import httpx
        with patch("src.etl.spatial_service._make_client") as mock_client_cls:
            ctx = mock_client_cls.return_value.__enter__.return_value
            ctx.get.side_effect  = httpx.TimeoutException("timeout")
            ctx.post.side_effect = httpx.TimeoutException("timeout")

            result = get_static_spatial_metrics(26.9124, 75.7873)

        for key, prov in result["_provenance"].items():
            assert prov["status"] != SourceStatus.REAL, (
                f"Provenance for '{key}' must not be REAL after fallback"
            )

    def test_weathering_index_is_none_when_unavailable(self):
        """weathering_index must be None (not 0.0 or some default) when UNAVAILABLE."""
        with patch("src.etl.spatial_service.get_soil_properties") as ms, \
             patch("src.etl.spatial_service.get_proximity_metrics") as mp:

            prov = FactorProvenance("X", SourceStatus.FALLBACK, True, "NONE")
            ms.return_value = ({"clay_percent": 25.0, "hydraulic_capacity": 15.0, "soil_depth": None}, prov)
            mp.return_value = ({"distance_to_river_m": None, "distance_to_road_m": None}, prov)

            result = get_static_spatial_metrics(11.6854, 76.1320)

        # weathering_index must be None (not an arbitrary numeric default)
        assert result["weathering_index"] is None


# ===========================================================================
# G. MODEL SHAPE SAFETY — CRITICAL REGRESSION
# ===========================================================================

@pytest.mark.skip(reason="Model upgraded to 16 features via preprocessor")
class TestModelShapeSafety:
    """
    CRITICAL: The active RandomForest model must always receive exactly 4 features.
    This test catches any accidental insertion of spatial factors into X.
    """

    def test_ml_input_vector_is_exactly_4_features(self):
        """
        Simulate the X-construction logic from risk.py and assert shape.
        No spatial factors must appear in X.
        """
        terrain  = {"slope_degrees": 5.2,   "elevation_m": 1200.0}
        rainfall = {"rainfall_3day": 32.0, "rainfall_15day": 85.0}

        X = [[
            terrain["slope_degrees"],
            terrain["elevation_m"],
            rainfall["rainfall_3day"],
            rainfall["rainfall_15day"],
        ]]

        assert len(X[0]) == 4, (
            f"ML input vector MUST be exactly 4 features; got {len(X[0])}. "
            "Do NOT add spatial factors to X."
        )

    def test_spatial_factors_not_in_ml_vector(self):
        """
        Explicitly verify that none of the FC-3 spatial factor keys are passed
        to predict_proba via the feature vector.
        """
        forbidden_keys = [
            "clay_percent", "hydraulic_capacity", "soil_depth",
            "lithology_class", "weathering_index",
            "distance_to_river_m", "distance_to_road_m",
        ]
        terrain  = {"slope_degrees": 15.0, "elevation_m": 3000.0}
        rainfall = {"rainfall_3day": 55.0,  "rainfall_15day": 140.0}

        X = [[
            terrain["slope_degrees"],
            terrain["elevation_m"],
            rainfall["rainfall_3day"],
            rainfall["rainfall_15day"],
        ]]

        # Spatial factors must be absent
        x_flat = X[0]
        assert len(x_flat) == 4

        # Double-check no extra factors leaked in
        for key in forbidden_keys:
            assert key not in terrain
            assert key not in rainfall

    def test_predict_proba_input_dimension(self):
        """Load the actual model and verify it accepts exactly 4 features."""
        import pickle
        import os
        import numpy as np

        model_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "src", "models", "landslide_model.pkl"
        )
        if not os.path.exists(model_path):
            pytest.skip("landslide_model.pkl not found — run src/models/train.py first.")

        with open(model_path, "rb") as f:
            model = pickle.load(f)

        X = np.array([[5.0, 1200.0, 30.0, 80.0]])   # valid 4-feature vector
        assert X.shape[1] == 4

        proba = model.predict_proba(X)
        assert proba.shape == (1, 2), f"Expected (1,2) output, got {proba.shape}"


# ===========================================================================
# StaticSpatialMetrics Unit Tests
# ===========================================================================

class TestStaticSpatialMetrics:
    def test_to_api_dict_contains_all_fields(self):
        m = StaticSpatialMetrics(
            clay_percent=22.0, hydraulic_capacity=18.0, soil_depth=95.0,
            lithology_class="Sedimentary", weathering_index=None,
            distance_to_river_m=320.0, distance_to_road_m=180.0,
        )
        d = m.to_api_dict()
        assert d["clay_percent"]        == 22.0
        assert d["weathering_index"]    is None
        assert d["distance_to_road_m"]  == 180.0

    def test_overall_quality_all_real(self):
        m = StaticSpatialMetrics()
        m.set_provenance("soil",      FactorProvenance("A", SourceStatus.REAL,     False, "REST"))
        m.set_provenance("lithology", FactorProvenance("B", SourceStatus.REAL,     False, "RASTER"))
        m.set_provenance("proximity", FactorProvenance("C", SourceStatus.REAL,     False, "REST"))
        assert m.overall_quality() == SourceStatus.REAL

    def test_overall_quality_mixed(self):
        m = StaticSpatialMetrics()
        m.set_provenance("soil",      FactorProvenance("A", SourceStatus.REAL,     False, "REST"))
        m.set_provenance("lithology", FactorProvenance("B", SourceStatus.FALLBACK, True,  "NONE"))
        assert m.overall_quality() == "PARTIAL"

    def test_overall_quality_all_fallback(self):
        m = StaticSpatialMetrics()
        m.set_provenance("soil",      FactorProvenance("A", SourceStatus.FALLBACK, True, "NONE"))
        m.set_provenance("lithology", FactorProvenance("B", SourceStatus.FALLBACK, True, "NONE"))
        assert m.overall_quality() == SourceStatus.FALLBACK
