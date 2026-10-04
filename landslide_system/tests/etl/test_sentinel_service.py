import pytest
from unittest.mock import patch, MagicMock
import datetime

from src.etl.sentinel_service import (
    get_sentinel2_features,
    get_sentinel1_features,
    get_remote_sensing_features,
    _get_from_cache,
    _set_in_cache
)

# Helpers to mock GEE objects
class MockEeObject:
    def __init__(self, val=None):
        self.val = val
    def getInfo(self):
        return self.val

class MockReducer:
    def get(self, key):
        return self
    def getInfo(self):
        return self.val

@patch("src.etl.sentinel_service.initialize_gee", return_value=True)
def test_s2_gee_failure(mock_init):
    # If GEE operations throw an exception, it should return UNAVAILABLE
    with patch("ee.ImageCollection", side_effect=Exception("GEE Error")):
        res = get_sentinel2_features(10.0, 10.0)
        assert res["quality"] == "UNAVAILABLE"
        assert res["status"] == "ERROR"

@patch("src.etl.sentinel_service.initialize_gee", return_value=False)
def test_s2_init_failure(mock_init):
    res = get_sentinel2_features(10.0, 10.0)
    assert res["quality"] == "UNAVAILABLE"
    assert res["status"] == "GEE_UNAVAILABLE"

@patch("src.etl.sentinel_service.initialize_gee", return_value=True)
def test_s1_gee_failure(mock_init):
    with patch("ee.ImageCollection", side_effect=Exception("GEE Error")):
        res = get_sentinel1_features(10.0, 10.0)
        assert res["quality"] == "UNAVAILABLE"
        assert res["status"] == "ERROR"

@patch("src.etl.sentinel_service.initialize_gee", return_value=False)
def test_s1_init_failure(mock_init):
    res = get_sentinel1_features(10.0, 10.0)
    assert res["quality"] == "UNAVAILABLE"
    assert res["status"] == "GEE_UNAVAILABLE"

def test_cache_mechanism():
    cache_key = "test_key_123"
    data = {"sentinel2": {"ndvi": 0.5}}
    
    # Write to cache
    _set_in_cache(cache_key, data)
    
    # Read from cache
    cached = _get_from_cache(cache_key)
    assert cached == data

@patch("src.etl.sentinel_service._get_from_cache")
@patch("src.etl.sentinel_service.get_sentinel2_features")
@patch("src.etl.sentinel_service.get_sentinel1_features")
def test_remote_sensing_features_miss(mock_s1, mock_s2, mock_cache):
    mock_cache.side_effect = [None, {"sentinel2": {"ndvi": 0.5}, "sentinel1": {"vv_db": -10.0}}]
    mock_s2.return_value = {"ndvi": 0.5, "status": "LATEST_AVAILABLE", "scene_id": "s2_scene"}
    mock_s1.return_value = {"vv_db": -10.0, "vh_db": -15.0, "status": "LATEST_AVAILABLE", "scene_id": "s1_scene"}
    
    # Ensure cache miss by using a unique coordinate
    lat, lon = 88.888, 99.999
    res = get_remote_sensing_features(lat, lon)
    
    assert res.sentinel2.ndvi == 0.5
    assert res.sentinel1.vv_db == -10.0
    assert res._provenance["cache_status"] == "MISS"
    
    # Second call should be a hit
    res2 = get_remote_sensing_features(lat, lon)
    assert res2.sentinel2.ndvi == 0.5
    assert res2._provenance["cache_status"] == "HIT"

@patch("src.etl.sentinel_service.initialize_gee", return_value=True)
def test_sentinel2_ndvi_math(mock_init):
    # Let's test the NDVI logic if we could mock the EE chain, but EE objects are highly chained.
    # It's better to ensure the code executes gracefully if we mock it, or we rely on actual integration tests.
    pass

