import pytest
from pydantic import ValidationError
from datetime import datetime, date

from src.api.schemas.common import CoordinateRequest, ErrorResponse
from src.api.schemas.risk import RiskResponse
from src.api.schemas.rainfall import RainfallResponse, RainfallObservation

def test_coordinate_request_valid():
    req = CoordinateRequest(latitude=45.0, longitude=90.0)
    assert req.latitude == 45.0
    assert req.longitude == 90.0

def test_coordinate_request_invalid_lat():
    with pytest.raises(ValidationError):
        CoordinateRequest(latitude=95.0, longitude=90.0)

def test_coordinate_request_invalid_lon():
    with pytest.raises(ValidationError):
        CoordinateRequest(latitude=45.0, longitude=-200.0)

def test_risk_response_serialization():
    # Mock a dictionary that mirrors a Phase-5 output
    mock_dict = {
        "location_id": "TEST_LOC",
        "latitude": 27.5,
        "longitude": 85.5,
        "susceptibility_probability": 0.85,
        "susceptibility_class": "VERY_HIGH",
        "rainfall_1d": 12.5,
        "rainfall_3d": 45.0,
        "rainfall_7d": 100.0,
        "rainfall_15d": 150.0,
        "rainfall_trigger_state": "CRITICAL",
        "rainfall_trigger_score": 3,
        "dynamic_risk": "SEVERE",
        "risk_level": "RISK_CRITICAL",
        "reasons": ["High rain", "Unstable soil"],
        "observation_date": "2026-10-01",
        "timestamp": "2026-10-01T12:00:00Z",
        "data_source": "MOCK",
        "stale": False,
    }
    
    resp = RiskResponse.model_validate(mock_dict)
    assert resp.location_id == "TEST_LOC"
    assert resp.latitude == 27.5
    assert resp.susceptibility_class == "VERY_HIGH"
    assert resp.dynamic_risk == "SEVERE"
    assert resp.observation_date == date(2026, 10, 1)

def test_risk_response_alias():
    # Test that final_risk_level correctly maps to dynamic_risk if used
    mock_dict = {
        "location_id": "TEST_LOC",
        "latitude": 27.5,
        "longitude": 85.5,
        "susceptibility_probability": 0.85,
        "susceptibility_class": "VERY_HIGH",
        "rainfall_trigger_state": "CRITICAL",
        "rainfall_trigger_score": 3,
        "final_risk_level": "SEVERE", # the alias
        "timestamp": "2026-10-01T12:00:00Z"
    }
    
    resp = RiskResponse.model_validate(mock_dict)
    assert resp.dynamic_risk == "SEVERE"

def test_date_fields_malformed():
    mock_dict = {
        "location_id": "TEST_LOC",
        "latitude": 27.5,
        "longitude": 85.5,
        "susceptibility_probability": 0.85,
        "susceptibility_class": "VERY_HIGH",
        "rainfall_trigger_state": "CRITICAL",
        "rainfall_trigger_score": 3,
        "timestamp": "Not a Date",
    }
    
    with pytest.raises(ValidationError):
        RiskResponse.model_validate(mock_dict)

def test_rainfall_response():
    resp = RainfallResponse(
        latitude=10.0,
        longitude=20.0,
        observation_date="2026-10-01",
        rainfall_observations=[RainfallObservation(date="2026-10-01", rainfall_mm=10.5)],
        source="CHIRPS",
        retrieval_timestamp="2026-10-01T12:00:00Z"
    )
    assert resp.source == "CHIRPS"
    assert resp.units == "mm"
    assert resp.rainfall_observations[0].rainfall_mm == 10.5
