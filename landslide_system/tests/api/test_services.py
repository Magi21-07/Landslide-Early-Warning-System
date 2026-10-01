import pytest
from unittest.mock import MagicMock

from src.api.services.risk_service import RiskService
from src.risk.risk_store import SQLiteRiskStore
from src.risk.risk_scheduler import RiskScheduler

@pytest.fixture
def risk_service():
    # Use in-memory SQLite for testing the service
    store = SQLiteRiskStore(":memory:")
    # Use empty gee_config since we'll mock execution
    scheduler = RiskScheduler(gee_config="mock")
    return RiskService(store=store, scheduler=scheduler)

def test_evaluate_location_risk_mock_success(risk_service):
    # Test valid mock execution
    lat, lon = 27.5, 85.5
    result = risk_service.evaluate_location_risk(lat, lon, mock=True)
    
    assert result["latitude"] == lat
    assert result["longitude"] == lon
    assert result["data_source"] == "MOCK/SYNTHETIC"
    assert result["stale"] is False
    assert result["error_info"] is None
    assert result["susceptibility_class"] == "HIGH" # Based on the default mock predictor

def test_evaluate_location_risk_invalid_coords(risk_service):
    with pytest.raises(ValueError, match="Latitude must be between -90 and 90"):
        risk_service.evaluate_location_risk(95.0, 85.5)
        
    with pytest.raises(ValueError, match="Longitude must be between -180 and 180"):
        risk_service.evaluate_location_risk(27.5, -200.0)

def test_evaluate_location_risk_scheduler_failure(risk_service):
    # Force a failure inside the scheduler
    def bad_refresh(*args, **kwargs):
        return [{"stale": True, "error_reason": "Simulated CHIRPS failure"}]
    
    risk_service.scheduler.refresh_locations = bad_refresh
    
    with pytest.raises(ValueError, match="Risk evaluation failed: Simulated CHIRPS failure"):
        risk_service.evaluate_location_risk(27.5, 85.5, location_id="FAIL_LOC", mock=False)
        
    # Verify the failure was persisted to the store
    latest = risk_service.store.get_latest_risk("FAIL_LOC")
    assert latest is not None
    assert latest["stale"] == 1
    assert latest["error_info"] == "Simulated CHIRPS failure"

def test_get_current_risk(risk_service):
    # Should be None initially
    assert risk_service.get_current_risk("TEST_LOC") is None
    
    # Store a dummy record
    risk_service.store.save_risk_result({
        "location_id": "TEST_LOC",
        "timestamp": "2026-10-01T12:00:00Z",
        "dynamic_risk": "HIGH"
    })
    
    current = risk_service.get_current_risk("TEST_LOC")
    assert current is not None
    assert current["dynamic_risk"] == "HIGH"

def test_get_risk_history(risk_service):
    # Store multiple records
    for i in range(5):
        risk_service.store.save_risk_result({
            "location_id": "TEST_LOC",
            "timestamp": f"2026-10-01T12:0{i}:00Z",
            "dynamic_risk": "HIGH"
        })
        
    history = risk_service.get_risk_history("TEST_LOC", limit=3)
    assert len(history) == 3
